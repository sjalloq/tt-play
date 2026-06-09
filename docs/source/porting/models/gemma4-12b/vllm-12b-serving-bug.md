# Gemma4-12B: correct offline, garbage when served via vLLM (single P150)

## TL;DR

`google/gemma-4-12B-it` (the text-only, config-only 12B variant) runs **correctly**
through the TT-NN model and the vLLM bridge **offline** — full-model parity tests are
**PCC 1.0** vs golden for prefill, decode, and traced decode on `blackhole-1x1`. But when
the same model is **served** through `vllm serve` (tenstorrent/vllm TT plugin) on a single
P150, generation is **garbage** (multilingual token salad) from the first token, greedy,
on both `/v1/completions` and `/v1/chat/completions`.

**FIXED (2026-06-08).** Root cause: ``Gemma4ForCausalLM`` did not override ``warmup_model_decode``,
so the decode trace was captured during warmup **before** the per-layer page-table buffers
(``_persistent_per_layer_page_tables``) existed — they were created lazily on the first request.
The trace bound the **legacy single-page_table** path and the 48 per-layer buffers were allocated
*after* the trace went live (``allocator.cpp:110``); the reused trace then made hybrid
full-attention layers address the wrong KV → garbage from token 1. The layout / HMA / 8-vs-1
kv-head hypotheses were all tested and **ruled out**. **Fix** (local, keeps tracing/speed): a
``Gemma4ForCausalLM.warmup_model_decode`` override that pre-allocates the per-layer buffers + binds
``_active_page_tables_per_layer`` **before** trace capture (``tt/generator_vllm.py``). Validated on
the live serve with full tracing (``trace_mode:"all"``): both endpoints return "…**Paris**." at full
speed. See `Experiments (2026-06-08)`_ below.

## Environment / pinned pair

| Component | Value |
|---|---|
| Model | `google/gemma-4-12B-it`, text-only config (`models/demos/gemma4/configs/gemma-4-12B-it/config.json` overlaid). Dense, no PLE, no KV-sharing. **Config-only variant — not in any CI matrix.** |
| Device | single **P150** (Blackhole), `MESH_DEVICE=P150`, `blackhole-1x1` |
| tt-metal | `arg/gemma4_optimizations` (local `gemma4-opt`), `v0.72.0-dev20260602` + gemma4 commits (`f7d0161`) |
| vLLM | `tenstorrent/vllm` **`5eb61e8`** — "plugin: hybrid Gemma4 wiring — block_table padding + model registration (#390)" (2026-06-02) |
| vLLM (NOT used) | dev HEAD `3334377` (#409 "Declare device sampling in model") **removed** the `non_greedy_decoding_on_device` arg our tt-metal still requires → `warmup_model_prefill() missing 1 required positional argument`. `5eb61e8` is the parent and matches. |
| Serving args | `--max-num-seqs 1 --max-model-len 4096 --block-size 64 --no-enable-prefix-caching`, host sampling (`sample_on_device_mode=None`) |

## Symptom

```
POST /v1/completions  prompt="The capital of France is"
  → tokens [2, 818, 5279, 529, 7001, 563]   (verified correct: <bos> + 5 ids, no template)
  → "  a canonical droit deedUF converted defiもう combinations highs"   (garbage)

POST /v1/chat/completions (gemma chat template, correct <bos>+<|turn> markers)
  → "Aोला lauभिold scholarly=%+.以 السماء maze abstain ..."   (garbage)
```

Greedy (`temperature=0`), garbage from token 1, independent of prompt length.

## Ruled out (with evidence)

- **Chat template / markers** — raw `/v1/completions` (no template) is also garbage.
- **Missing BOS** — found+fixed a real bug (model dir `tokenizer.json` post-processor lacked the
  `<bos>` SpecialToken, so `add_special_tokens=True` didn't prepend it; gemma → garbage without
  `<bos>`). Patched the post-processor; raw now tokenizes `[2, ...]`. **Still garbage** → BOS was
  a real bug but not the cause.
- **On-device sampling** — `sample_on_device_mode` defaults to `None` (host sampling), so the
  device-sampling path is not exercised.
- **Model / bridge forward** — `models/demos/gemma4/tests/unit/test_vllm_parity.py` on
  `HF_MODEL=<12B>` / `MESH_DEVICE=P150`, `-k 1x1`:
  - `test_full_model_parity_uniform_vs_vllm` → **PCC 1.0**
  - `test_full_model_parity_decode_uniform_vs_vllm` (4 & 8 steps) → **PCC 1.0**
  - `test_full_model_parity_decode_trace` (±PLI) → **PCC 1.0**

## Experiments (2026-06-08)

The layout hypothesis was tested end-to-end against the **real** vLLM (clone `src/vllm` @
`5eb61e8`; functions run/transcribed verbatim) and on the **P150**. Result: the layout
diverges from the harness model exactly as suspected, **but the model handles the divergence
correctly** — so the layout is *not* the garbage cause. Artifacts:
`models/demos/gemma4/tests/unit/test_real_unifier_parity.py` (real-unifier diff, strict-xfail),
`test_vllm_parity.py::test_two_sliding_layers_share_one_buffer_decode` (device),
`demos/gemma4/layout_experiment.py` (torch-free layout proof).

**Confirmed layout facts:**

- Real vLLM builds **6 kv_cache_groups / 8 HMA tensors** for the 12B (5 sliding sub-groups of 8
  + 1 full group of 8), not the harness's 2 groups / 40 tensors. The pipeline is
  `unify_kv_cache_spec_page_size()` **then** `_get_kv_cache_groups_uniform_page_size()`.
- The 12B **inverts which spec the unifier doubles**: full → `block_size 256` (width 16),
  sliding stays `64` (width 64). E2B doubles *sliding* (→128) and full stays 64. The bridge's
  *legacy* page-table sizing (`_get_prefill_user_page_table` / `_mock_tokens`) assumes layer 0
  (sliding) holds the max block_size — a latent gap for the 12B, captured by the xfail test.

**Ruled out (with evidence) — the layout is handled:**

- **HMA num_kv_heads clash (8-vs-1).** Each physical buffer is shared by sliding (`8,64,256`)
  and full (`1,256,512`) layers. `attention/operations.py:effective_block_size` inverts the
  kv-head factor (`8·64·256/(1·512)=256`) — its docstring says it was added for **26B-A4B
  (8/2)** and **31B (16/4)**, which serve correctly. The offline harness allocates the *exact*
  clash buffer and gets **PCC 1.0**.
- **Per-layer page-table width.** The plugin (`model_runner.py`) pads every per-group block
  table to `cdiv(max_model_len, cache_config.block_size)` and each layer's cache carries its
  own `block_size` in `shape[2]`; the per-layer routing is self-consistent.
- **Multi-sliding shared-buffer addressing.** Device test: two sliding layers sharing one
  buffer with disjoint block IDs → **PCC 0.996 / 0.998**. Correct.

**Confirmed (device, 2026-06-08).** Serving with ``trace_mode:"none"`` is coherent on both
endpoints (`/v1/completions` → "…**Paris**.", `/v1/chat/completions` → "The capital of France is
Paris."); ``trace_mode:"decode_only"`` (eager prefill, traced decode) is still garbage — isolating
the fault to the **decode trace**. Instrumenting the live serve then localized it precisely
(ordered log): the decode trace is captured during warmup **before** ``_persistent_per_layer_page_tables``
exist (they are allocated lazily on the first request), so it binds the legacy single-page_table
path; the 48 per-layer buffers are then allocated after the trace is live (``allocator.cpp:110``),
and the reused trace makes hybrid full-attention layers address the wrong KV. (Repro:
``demos/gemma4/serve_trace_none.sh <none|decode_only|all>``.)

This is **not** the kv_cache-ownership / trace-memory class (#45763 / #46202): ``kv_cache`` is
stable across steps (vLLM passes the same ``runner.kv_caches``), and the ``allocator.cpp:110``
warning still fires after the fix while output is correct.

**Root cause + fix.** ``Gemma4ForCausalLM`` did not override ``warmup_model_decode``. The fix adds
that override to pre-allocate the per-layer page-table buffers and bind
``_active_page_tables_per_layer`` **before** ``super().warmup_model_decode`` captures the trace
(``models/demos/gemma4/tt/generator_vllm.py``). Validated: an instrumented ``trace_mode:"all"``
re-run shows the per-layer allocation now precedes trace capture, and both endpoints return
"…Paris." at full traced speed (~17.9 tok/s/user). A follow-up to the merged bridge **#44265**;
complementary to **#45789** (different bug). Full localization log: ``HYPOTHESIS.md`` (same dir).

## Minimal repro

1. Build tt-metal `gemma4-opt`; install tenstorrent/vllm `5eb61e8` + `plugins/vllm-tt-plugin[runtime]`
   into the tt-metal `python_env`; re-apply `models/demos/gemma4/requirements.txt` (transformers 5.5.0).
2. Assemble the 12B model dir (HF tokenizer/safetensors + in-repo text-only `config.json` +
   `chat_template.jinja`; patch `tokenizer.json` post-processor to prepend `<bos>`).
3. `MESH_DEVICE=P150 VLLM_PLUGINS=tt,tt_model_registry vllm serve <dir> --max-num-seqs 1
   --max-model-len 4096 --block-size 64 --no-enable-prefix-caching` → garbage.
4. Offline parity (`test_vllm_parity.py -k 1x1`, `HF_MODEL=<dir>`) → PCC 1.0.

## Questions / asks for the TT team

1. Has gemma4 ever been **served through vLLM** with **asymmetric sliding-vs-global KV-head
   counts** (e.g. the 12B), or only the CI variants (E2B 1×1, 26B-A4B / 31B on T3K)?
2. Is `test_layout_matches_unifier_for_gemma4_e2b` expected to generalize to the 12B's 8-vs-1
   KV-head layout, and is there a known gap in the kv-cache-groups unification / `Gemma4VllmLayout`
   for that case?
3. Any known issue with `block_size`/page-table construction or HMA tensor sharing when sliding
   and global layers have different `num_key_value_heads`?
4. Is the single-P150 (1×1) hybrid kv-cache path exercised anywhere for gemma4, or only multi-device?

## Related upstream work (parallel — found via GitHub search 2026-06-07)

**Investigated — same area, but NOT the cause** (see Experiments: kv_cache is stable; the
``allocator.cpp:110`` aliasing is benign here):
- **Issue #45763 "[models][vLLM] Unclear kv_cache ownership"** (label `bug`, OPEN). "As soon as we
  capture traces, it is invalid to change it." Same *context* (agentic bring-up, traces) but a
  different mechanism — our bug is the warmup binding the legacy page-table path, not a kv_cache
  swap. Worth a note that the 12B garbage was a distinct cause; the systematic fix wouldn't catch it.
- **PR #45789 "[Bug fix] enforce Gemma4 vLLM KV cache ownership"** (OPEN, branch
  `peter941221-45763-kv-cache-ownership`). A *guard* that raises on a kv_cache identity swap; would
  not have fixed this (no swap occurs). Complementary, not the fix.

**Adjacent active work:**
- Issue **#44946 "[Gemma4] Paged KV-cache audit"** + branch `cleonidouTT/gemma4-paged-kv-cache-audit`
  — auditing `page_block_size` (64 unvalidated) and batched-decode K/V layout; adds `test_paged_kv_cache.py`;
  commit "fix batched decode attention for 31B on 1×4 (sliding + global)".
- PR **#46247 "Fix Gemma4 accuracy issues found by AutoFix"** (branch `gemma4-autofix-topk-fixes`)
  — shared-KV layer construction + exact-GELU/BF16 numerics; on **E2B**, residual top-1/top-2 swaps
  only (numerical drift, "no remaining verified semantic bug") — likely NOT our total-garbage issue.
- Branch `yieldthought/gemma4-instruct-vllm-optimization` — "Add Gemma4 vLLM paged attention adapter",
  "Fix Gemma4 instruct prompt fallback", mixed-precision profiles.
- Branch `alnah005/gemma4_acc_debug` — "added separate sliding and global attention classes".
- Merged context: **#44265 "gemma4: vLLM bridge for hybrid kv-cache-groups + kv-share aliasing"**
  (the bridge we run), **#45945 "declare supports_sample_on_device=True"**.

## Resolution / upstreaming

Fixed locally in ``models/demos/gemma4/tt/generator_vllm.py`` (the ``warmup_model_decode`` override
described under `Experiments (2026-06-08)`_); full traced serving is coherent. The fix is
gemma4-local — a follow-up to the merged bridge **#44265** (@handrewsTT) — and does **not** depend
on the kv_cache-ownership work (#45763 / #45789) or sampling (#46202).

- **Feed it back** as a new tt-metal issue + PR (request review @handrewsTT), plus a short comment
  on #45763 that the single-P150 12B agentic-serving garbage was a distinct cause (warmup trace
  binding), now fixed.
- **Caveats for reviewers:** no offline regression test reproduces it (the ``warmup_then_inference``
  unit test re-captures the trace, so it passes either way); validate the sibling variants
  (E2B / 26B-A4B / 31B) share this warmup path and don't regress; the residual ``allocator.cpp:110``
  warning is benign.
- The layout questions (Q1–Q4 above) are **answered**: the unifier/HMA layout is correct for the
  12B — do not pursue a layout fix.

**Separate follow-ups (not this fix).** Pi/agentic tool-calling needs the upstream
``vllm/tool_parsers/gemma4_tool_parser.py`` (registered ``gemma4``, format
``<|tool_call>call:name{...}``), which is absent from the pinned ``5eb61e8`` fork — vendor it plus
the open ``<|"|>`` / streaming fixes (vllm-project/vllm #44532, #44877, #43037, …) and serve with
``--enable-auto-tool-choice --tool-call-parser gemma4``. Served context is capped at 4096 on the
single-P150 12B.
