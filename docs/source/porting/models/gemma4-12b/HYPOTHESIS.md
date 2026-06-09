# gemma4-12B vLLM serving garbage — current hypothesis (2026-06-08)

Handoff for an agent already familiar with this issue. Full context:
`vllm-12b-serving-bug.md` (same dir).

## Conclusion (FIXED 2026-06-08)

`google/gemma-4-12B-it` (text-only, single P150, 1×1) served **garbage via vLLM** while offline
parity was PCC 1.0. **Root cause found and fixed — full traced serving now coherent.**

**Root cause:** `Gemma4ForCausalLM` did not override `warmup_model_decode`, so the decode trace was
captured during warmup **before** `_persistent_per_layer_page_tables` existed (they were created
lazily on the first request). The trace therefore bound the **legacy single-page_table** path, and
the 48 per-layer buffers were then allocated *after* the trace was live (`allocator.cpp:110`). The
warmup trace is reused every step → hybrid full-attention layers addressed the wrong KV → garbage
from token 1. (The layout / HMA / kv-head-asymmetry hypotheses were all tested and **ruled out**.)

**Fix (local, keeps tracing/speed):** `Gemma4ForCausalLM.warmup_model_decode` override that
pre-allocates `_persistent_per_layer_page_tables` + sets `_active_page_tables_per_layer` **before**
`super().warmup_model_decode` captures the trace (`generator_vllm.py`). Validated on the live serve
with `trace_mode:"all"`: the per-layer alloc now precedes trace capture, and both endpoints return
"…**Paris**." at full traced speed. Not blocked on upstream; #45789/#46202/`mark_corruptible` not
needed for the 12B.

**Workaround (no longer needed, kept for reference):** `trace_mode:"none"` (coherent, slow) —
`demos/gemma4/serve_trace_none.sh`.

## Ruled out (with evidence)

1. **HMA num_kv_heads clash (sliding 8 vs full 1 sharing a buffer).** Reconciled by
   `models/demos/gemma4/tt/attention/operations.py:effective_block_size` (inverts the kv-head
   factor: `8·64·256/(1·512)=256`). Offline parity allocates the *exact* clash buffer → PCC 1.0.
   26B-A4B (8/2) and 31B (16/4) share the asymmetry and serve fine.
2. **Per-layer page-table width / block_size.** Plugin (`vllm-tt-plugin/model_runner.py`) pads
   every per-group block table to `cdiv(max_model_len, cache_config.block_size)`; each layer's
   cache carries its own `block_size` in `shape[2]`. Self-consistent.
3. **Multi-sliding shared-buffer addressing** (the one thing offline never exercises: real vLLM
   packs 5 sliding layers into one buffer with disjoint block IDs; harness gives them separate
   buffers). **Tested on P150:** two sliding layers sharing one buffer w/ disjoint block IDs →
   PCC **0.996 / 0.998**. Correct.

## Confirmed-but-benign

- Real vLLM = **6 groups / 8 HMA tensors** for the 12B (harness models 2 groups / 40). The 12B
  **inverts which spec the unifier doubles** (full→`block_size 256`/width 16; sliding stays
  64/width 64; E2B is the opposite). Real divergence, but handled by the model. The bridge's
  *legacy* page-table sizing (`_get_prefill_user_page_table` / `_mock_tokens`) assumes layer 0
  (sliding) holds the max block_size — latent gap, not the garbage cause.

## Confirmed mechanism + what's left

**Confirmed (see Conclusion):** the traced decode/prefill path is the bug; `trace_mode:"none"`
serves coherently. The trace captures KV-cache addresses / sampling state at warmup and replays
them frozen, so a later change underneath (kv_cache swap → #45763; sampling change → #46202)
produces stale reads → garbage. Offline never reproduces (one stable handle, never freezes a
trace against changing state).

## Localization log (2026-06-08, narrowing toward a fast fix)

Goal: fix the *traced* path (keep speed), so we need the exact stale tensor.

1. **kv_cache is NOT swapped per step.** vLLM passes the same stable `runner.kv_caches`
   every decode step (`async_decode.py:424`). So the naive #45763 "handle swap" isn't the live
   trigger; the stale state is frozen *into the trace at warmup* and read back wrong.
2. **Warmup DECODE-trace binding is CORRECT for the 12B — ruled out.**
   `test_full_model_parity_warmup_then_inference[...small,nopli,1x1]` (now parametrized to run the
   real 12B config truncated to one full-attention group: 8-vs-1 kv heads, a full layer at
   block_size 256) captures the decode trace via the live warmup path (`_mock_tokens`, zero
   inputs) then runs real inference → **PCC 0.9993–0.9997 over 4 steps. Passes.** The `_mock_tokens`
   warmup binding is fine.
3. ~~Narrowed to the TRACED PREFILL path.~~ **OVERTURNED by experiment (below).** (The reasoning
   was: that test does prefill eagerly + traces decode, so prefill-trace was untested. Plausible,
   but wrong — see step 4.)
4. **It's the DECODE trace + allocator aliasing (#45763) — confirmed on the real serve.**
   `trace_mode:"decode_only"` (decode **traced**, prefill **eager** — `trace: False` in the log)
   is **garbage**, identical multilingual salad to `trace_mode:"all"`. `trace_mode:"none"` is
   coherent. So eager prefill does NOT help; the **decode trace** is the bug. The mechanism is in
   the log: during prefill warmup *after* the decode trace is captured —
   `Metal | Allocating device buffers is unsafe due to the existence of an active trace. These
   buffers may be corrupted once a trace is executed. (allocator.cpp:110)`. This warning is
   ABSENT in the `none` run. So: decode-trace capture → later buffer allocations (prefill
   activations, per request) alias memory the trace touches on replay → corruption → garbage.
   The offline `warmup_then_inference` passes because its tiny 6-layer model doesn't allocate
   colliding buffers; the real 48-layer 12B does. This is exactly #45763.

5. **LEADING ROOT CAUSE (gemma4-local, fast-fixable): the live decode trace is captured on the
   LEGACY page_table path, not the per-layer hybrid path.** `Gemma4ForCausalLM` does **not**
   override `warmup_model_decode`; the inherited one captures the decode trace via `_mock_tokens`
   **without** setting `self._active_page_tables_per_layer`. With that stash `None`,
   `model.py:968/1157` falls back to legacy single-page_table behavior, so the trace binds the
   legacy `page_table` device tensor. At inference the bridge's `decode_forward` sets
   `_active_page_tables_per_layer` + `update_persistent_per_layer_page_tables(...)`, but those
   writes go to the **per-layer persistent buffers the trace never reads** — the trace is frozen on
   the legacy path. Hybrid **full**-attention layers therefore decode against the wrong (broadcast,
   block-64) page table → wrong KV blocks → garbage from token 1.

   - This is precisely what `test_full_model_parity_warmup_then_inference` *deliberately avoids*:
     it manually does `tt_model_vllm.update_persistent_per_layer_page_tables(warmup_pt)` +
     `tt_model_vllm._active_page_tables_per_layer = warmup_pt` **before** `warmup_model_decode`
     (with the comment: *"Without this the warmup trace would bind against the legacy page_table
     only, and at inference our update_persistent... writes wouldn't reach anything the trace
     reads"*). With that setup it **passes (PCC 0.999)**. Live serving never does it → garbage.
   - Reconciles everything: `decode_only`=garbage (decode trace on legacy path), `none`=coherent
     (eager decode goes through the bridge's `decode_forward`, which sets per-layer routing).
   - The `allocator.cpp:110` "buffers unsafe while a trace is active" warning is a related
     trace-safety smell but is likely secondary; the page-table *binding* path is the garbage cause.

   **UPDATE — legacy-binding NOT confirmed.** Ran `warmup_then_inference` with
   `GEMMA4_SKIP_WARMUP_PER_LAYER=1` (capture the decode trace *without* the per-layer pre-setup,
   i.e. the way live warmup does) → **still PCC 0.999, passes.** So removing the warmup routing
   setup does not garble the offline path; the legacy-binding theory is not the (sole) cause, and
   the offline harness does **not** reproduce the live failure even when mimicking live warmup.
   (Likely the offline test re-captures the trace in its Phase-3 decode rather than reusing the
   warmup trace, so it never exercises live's capture-then-reuse-under-allocation-pressure.)

**Honest status after 5.** Solid: **decode trace is the culprit** (`decode_only`=garbage,
`none`=coherent). The live mechanism signal is the `allocator.cpp:110` warning — *buffers allocated
while a trace is active may be corrupted* — i.e. **trace-memory-safety (#45763)**. Both offline
reproduction attempts (warmup binding; skip-routing) **passed**, so the 6-layer offline harness
does not trigger it; the failure needs the full 48-layer live serve (real allocation pressure +
trace reuse across many steps). The warmup is *designed* to avoid this (model_runner.py:2560-2609:
Phase-1 compile-all, Phase-2 capture) under two assumptions — (1) traced and non-traced paths use
the same ops, (2) prefill warmup covers all seq lengths. A 12B-specific violation of either would
allocate corruptible buffers during/after capture.

6. **CONFIRMED ROOT CAUSE (live instrumentation, 2026-06-08) — and it IS local.** Added
   `GEMMA4DBG` markers around the decode-trace capture and the `_persistent_per_layer_page_tables`
   allocation, ran `trace_mode:"all"`. Ordered log:
   ```
   decode-trace BEGIN capture model=0        (warmup)
   decode-trace END capture model=0          → trace now ACTIVE
   ... first real request: Prefilling User 1 up to 6 tokens ...
   allocator.cpp:110  unsafe allocation (active trace)
   ALLOC _persistent_per_layer_page_tables n=48   ← FIRST allocation, AFTER capture
   ```
   So the 48 per-layer page-table buffers are created **lazily on the first request, after the
   decode trace is captured.** At capture time they don't exist → the trace binds the legacy
   single-page_table path; afterward they're allocated while the trace is live (the
   `allocator.cpp:110` aliasing). The warmup trace is **reused** (no second capture), so every
   decode reads the legacy binding → hybrid full layers address the wrong KV → garbage from token 1.
   Both earlier theories (5 = legacy-binding, the allocator-aliasing) were two faces of this single
   cause. The offline test masks it by *re-capturing* the trace in Phase 3 after the buffers exist.

**THE FIX (local, fast — keeps tracing) — IMPLEMENTED + VALIDATED.** Pre-allocate
`_persistent_per_layer_page_tables` (and set `_active_page_tables_per_layer`) in a
`Gemma4ForCausalLM.warmup_model_decode` override, **before** `super().warmup_model_decode` captures
the trace (`generator_vllm.py`). Re-ran the instrumented `trace_mode:"all"` serve: the
`ALLOC _persistent_per_layer_page_tables n=48` marker now appears **before** `decode-trace BEGIN
capture` (was after), and both endpoints return "…**Paris**." at full traced speed. (A residual
`allocator.cpp:110` warning still prints for an unrelated prefill buffer but is benign — output is
correct.) Not blocked on upstream; #45789/`mark_corruptible` not required.

**Ship-now workaround stays:** `trace_mode:"none"` (coherent, slow).

**Workaround to ship today:** serve with `--additional-config '{"tt": {"trace_mode": "none"}}'`
(slow — disables trace replay; see `serve_trace_none.sh`).

## Artifacts

- `models/demos/gemma4/tests/unit/test_real_unifier_parity.py` — real-vLLM unifier diff;
  E2B passes, 12B strict-xfail (documents the layout inversion; scoped as *not* the cause).
- `models/demos/gemma4/tests/unit/test_vllm_parity.py::test_two_sliding_layers_share_one_buffer_decode`
  — the on-device multi-sliding sharing test (passes).
- `demos/gemma4/layout_experiment.py` — torch-free real-vs-harness layout proof.
- `demos/gemma4/serve_trace_none.sh` — the confirming experiment: serve 12B with
  `trace_mode:"none"` → coherent output. Also the ship-today workaround.

## Env

Docker only (Arch host). Run tests via:
`util/tt-build run 'source python_env/bin/activate && cd /work/third_party/tt-metal && HF_MODEL=/work/.cache/models/gemma-4-12B-it HF_HUB_OFFLINE=1 python -m pytest <path> -k 1x1 -q'`.
Pinned vLLM clone: `src/vllm` @ `5eb61e8`. vLLM installed in `python_env`: `3334377` (unifier
logic identical for this purpose).

## Additional pointers (session 2, 2026-06-08)

I agree with the conclusion — and the layout-ruled-out evidence (effective_block_size inversion,
26B/31B serving, on-device multi-sliding PCC) is decisive; it cleanly overturns the earlier
8-vs-1 "layout suspicion." A few things to add:

1. **Decisive cheap experiment — disable the decode trace (do this *before* pulling any branch).**
   The plugin's `trace_mode` defaults to `"all"` (`vllm-tt-plugin/.../worker.py:72-78`, read from
   `tt_config`); `trace_decode_mode = trace_mode in ["all","decode_only"]`. Serve with
   **`trace_mode: "none"`** via `vllm serve ... --additional-config '{"tt": {"trace_mode": "none"}}'`
   (equivalently `additional_config={"tt":{...}}`).
   - If output goes **coherent** (slow) → the trace path is confirmed end to end, with *no
     branch/rebuild needed* — and you have a usable-if-slow gemma4 server today.
   - It clears **both** #45763 (kv_cache-in-trace) **and** #46202 (sampling-in-trace) at once:
     no trace ⇒ neither bug can fire. Strictly more decisive than #45789's guard.
   - If **still garbage** → the hypothesis is incomplete; look beyond tracing (e.g. block recycling).

2. **#45789 confirms, it doesn't fix — and the maintainer deferred it.** PR #45789's
   `_remember_runtime_kv_cache_identity` *raises* on a cache-identity swap, so pulling it will most
   likely turn the garbage into an **assertion** (confirmation), not correct output. In the #45763
   thread, **tchedaTT (the issue author) explicitly deferred #45789** for a systematic cross-model
   fix — not yet a PR; it lives in branches `tcheda/trace-allocation-tracker` and
   `tcheda/{v3,v4}_device_structured` (the `mark_corruptible` trace-allocation tracker). Watch
   tchedaTT's PRs for the authoritative fix; expect it to also close #46202.

3. **Parallel suspect — #46202 "Gemma4 doesn't invalidate traces when sampling changes"**
   (tchedaTT, OPEN, type *Bad Outputs*, freq *always*): gemma4 traces sampling jointly with the
   decode forward, so a stale trace can produce bad tokens. Same trace-staleness class as #45763;
   may be co-occurring. The `trace_mode:"none"` test isolates trace-vs-everything-else for both.

4. **Ruled out — on-device sampling.** `sample_on_device_mode` defaults to `None` (host sampling;
   `platform.py:295`, set only via `tt_config`). The device-sampling path is *not* exercised —
   sampling is host-side greedy. Not the cause.

5. **Repro gotchas (don't lose time):**
   - **`vllm serve` requires `src/vllm` checked out at `5eb61e8`, not dev HEAD `3334377`.** #409
     (dev HEAD) removed the `non_greedy_decoding_on_device` arg this tt-metal's
     `warmup_model_prefill` still requires → serving dies at warmup with *"missing 1 required
     positional argument"*. The editable install imports from the working tree, so the `3334377`
     version string is stale-but-harmless **only while the checkout stays at `5eb61e8`** — do not
     `git checkout` the clone to dev HEAD. (Offline unifier tests don't hit this path.)
   - **The model dir's `tokenizer.json` was patched** to prepend `<bos>` in its post-processor
     (stock file's TemplateProcessing had none → raw tokenization missed BOS → gemma garbage,
     independent of this bug). `tokenizer.json.bak` kept. Separate *real* bug; raw `/v1/completions`
     is still garbage after the fix, which is itself evidence it is **not** the cause — don't
     re-chase it.
