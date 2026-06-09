gemma4:12b
==========

Work log for bringing up **Gemma 4 12B** (``google/gemma-4-12B-it``) on a single
p150a and serving it to ``pi-p150a``.

:Target: ``google/gemma-4-12B-it`` (instruct) — text generation
:Status: ✅ Working. ``google/gemma-4-12B-it`` runs coherently on ``blackhole-1x1``
   (instruct, with its chat template) at ~17.9 tok/s/user (bfp4 MLP, bfp8 attention);
   TT port also verified against golden (base weights, bf16: PCC 0.996, identical
   top-5 tokens). Garbage output was a missing ``chat_template.jinja`` in the model
   dir — fixed. vLLM serving on a single p150a also works (decode tracing on, full
   speed) after a warmup trace-binding fix; the Pi coding agent is blocked on a
   missing gemma4 tool-call parser. See `Serving via vLLM`_.
:Approach: build ``models/demos/gemma4`` (branch ``gemma4-opt``) in an Ubuntu
   22.04 container; run on the single card

What this is
------------

Gemma 4 is implemented in the fork at ``models/demos/gemma4/`` — a standalone
TT-NN demo (attention, MoE, RoPE, RMSNorm, vLLM bridge, unit tests). Branch
``arg/gemma4_optimizations`` (local ``gemma4-opt``) adds the **12B** variant as
configuration (``configs/gemma-4-12B-it/config.json`` + a
``precision_overrides.json`` entry). A local change also wires ``bfp4``
(``ttnn.bfloat4_b``) into the demo's precision map (``tt/precision.py``,
``tt/shared_mlp.py``) so the MLP can run at 4-bit block float. The work is a
build plus single-card Blackhole bring-up.

The 12B model
-------------

``config.json`` reports the simplest variant — dense, no MoE / per-layer-inputs /
KV-sharing:

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Config
     - Value (12B)
     - Consequence
   * - ``enable_moe_block``
     - ``False``
     - dense MLP path
   * - ``hidden_size_per_layer_input``
     - ``0``
     - no per-layer-input embeddings
   * - ``num_kv_shared_layers``
     - ``0``
     - normal KV cache
   * - layers / hidden / heads
     - 48 / 3840 / 16 (8 KV)
     - GQA
   * - ``layer_types``
     - 40 sliding + 8 full
     - hybrid local/global attention
   * - weights
     - ~24 GB bf16
     - fits 32 GB GDDR6 (single-card home; won't fit a 12 GB Wormhole card)

Build
-----

Native Arch builds are out (toolchain mismatch); the build runs in an Ubuntu
22.04 container matching upstream, driven by ``util/tt-build``. Image
``tt-metal-build:22.04`` (``docker/Dockerfile.tt-build``) =
``Dockerfile.basic-dev`` (clang-20, SFPI, uv/py3.10) + the **full**
``install_dependencies.sh`` (CMake 4.0.2) + ``file``/``lsb-release`` + git
``safe.directory``. Build artifacts (``build_Release/``, ``python_env/``) persist
in the submodule tree.

.. code-block:: console

   $ tt-build image     # build tt-metal-dev + tt-metal-build (once)
   $ tt-build all       # build_metal.sh --enable-ccache + create_venv.sh

``tt-build`` mounts the **whole** repo at ``/work`` so the submodule's relative
``.git`` gitlink resolves and tt-metal's git-derived version works.

Build notes (handled by the image and ``tt-build``; relevant when reproducing by
hand):

* CMake ≥ ``3.24`` is required. Ubuntu 22.04 ships 3.22.1; the full
  ``install_dependencies.sh`` installs 4.0.2, whereas
  ``Dockerfile.basic-dev``'s ``--sfpi`` path does not.
* The whole repo mounts at ``/work`` with ``git safe.directory`` set, so the
  submodule's relative ``.git`` gitlink resolves and the git-derived project
  version is non-empty.
* ``build_Release/`` must be removed before changing the mount path; a stale
  ``CMakeCache.txt`` pins the previous source directory.

Run
---

``tt-build`` passes the card through (``--device=/dev/tenstorrent``, hugepages,
``--privileged``) whenever ``/dev/tenstorrent`` is present, so the build
container both compiles and runs on-card.

The 12B is **not** runnable from a bare HF id. The released checkpoint is the
``gemma4_unified`` multimodal model that transformers 5.5.0 cannot load, and the
in-repo ``configs/gemma-4-12B-it/`` holds only ``config.json``. Assemble a
complete model directory from the (ungated) ``google/gemma-4-12B-it`` —
tokenizer + safetensors — and overlay the in-repo text-only ``config.json``:

.. code-block:: text

   $ mkdir -p .cache/models/gemma-4-12B-it
   $ util/tt-build run 'python_env/bin/python - <<PY
   from huggingface_hub import hf_hub_download
   dst = "/work/.cache/models/gemma-4-12B-it"
   for f in ["tokenizer.json", "tokenizer_config.json", "generation_config.json",
             "chat_template.jinja", "model.safetensors"]:
       hf_hub_download("google/gemma-4-12B-it", f, local_dir=dst)
   PY'
   $ cp third_party/tt-metal/models/demos/gemma4/configs/gemma-4-12B-it/config.json \
        .cache/models/gemma-4-12B-it/config.json

.. important::

   ``chat_template.jinja`` is **required**. It is a separate repo file (the chat
   format is *not* in ``tokenizer_config.json``). Without it the demo feeds raw
   text to the instruct model and output degenerates. The 12B uses a non-standard
   ``<|turn>…<turn|>`` / ``<|channel>thought…<channel|>`` format — rely on the
   shipped template, do not hand-write one.

The weights are one ~24 GB ``model.safetensors``. Point ``HF_MODEL`` at the
assembled directory (``/work/...`` inside the container) and run the demo:

.. code-block:: console

   $ util/tt-build run 'source python_env/bin/activate && cd /work/third_party/tt-metal && \
       HF_MODEL=/work/.cache/models/gemma-4-12B-it HF_HUB_OFFLINE=1 \
       python -m pytest models/demos/gemma4/demo/text_demo.py::test_demo -k "1x1 and prefill_128" -s'

``test_demo`` only asserts that tokens were produced — inspect the printed
output for correctness. ``test_demo_single_layer`` is a faster, pipeline-only
smoke test (1 layer, no accuracy signal).

Expected state (single p150a, ``1x1``, fw 19.10.0):

.. list-table::
   :widths: 50 50

   * - Weight precision
     - MLP ``bfp4`` (``shared_mlp``), attention ``bfp8`` (``precision_overrides.json``)
   * - Decode throughput
     - ~17.9 tok/s/user (56 ms/token)
   * - Time to first token
     - ~93 ms
   * - Prefill / decode compile
     - ~20 s / ~15 s (cold)
   * - Output quality
     - coherent, instruction-following (greedy)

Serving via vLLM
----------------

``google/gemma-4-12B-it`` serves through the tenstorrent/vllm TT plugin on a single
p150a with **decode tracing enabled** (full speed). The OpenAI-compatible server runs
from the local tt-metal build via ``util/tt-llm-server`` local mode:

.. code-block:: console

   $ TT_LLM_LOCAL=1 util/tt-llm-server up -w      # serve local build at :8001 (open auth)
   $ util/tt-llm-server status                     # health + served id (gemma-4-12B-it)
   $ util/tt-llm-server down                        # stop

A chat completion returns coherent output (``"Paris"`` for the capital of France),
``trace_mode`` default (``all``), ~17.9 tok/s/user.

**The fix.** Served generation was multilingual garbage from the first token while offline
parity was PCC 1.0. Root cause: ``Gemma4ForCausalLM`` did not override
``warmup_model_decode``, so the decode trace was captured during warmup *before* the
per-layer page-table buffers (``_persistent_per_layer_page_tables``) existed — they were
created lazily on the first request. The trace bound the legacy single-page-table path;
the per-layer buffers were then allocated after the trace went live, and the reused trace
made the hybrid full-attention layers address the wrong KV cache. The fix
(``models/demos/gemma4/tt/generator_vllm.py``) overrides ``warmup_model_decode`` to
pre-allocate the per-layer buffers and bind ``_active_page_tables_per_layer`` before trace
capture — tracing stays on, no speed loss. The hybrid kv-cache-groups / HMA tensor-sharing
layout for the 12B's asymmetric KV heads (8 sliding vs 1 global) was investigated and
**ruled out** as the cause.

.. note::

   Diagnosis trail and the ruled-out hypotheses are in ``vllm-12b-serving-bug.md`` and
   ``HYPOTHESIS.md`` (same directory). ``trace_mode: "none"`` (``--additional-config
   '{"tt": {"trace_mode": "none"}}'``) is a coherent but slow fallback that needs no fix.

**Pi coding agent — blocked.** The model serves and ``util/pi-p150a`` connects, but Pi does
not yet run as a full coding agent:

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Gap
     - Detail
   * - Tool-calling
     - Pi sends a ``tools`` array; the server has no tool-call parser for gemma4, so
       requests return ``HTTP 400`` (``"auto" tool choice requires --tool-call-parser``).
       gemma4 emits ``<|tool_call>call:name{...}``; vLLM's only gemma parser
       (``functiongemma``) expects ``<start_function_call>`` — no built-in parser matches.
   * - Context
     - ``--max-model-len 4096`` (24 GB weights leave little KV headroom on 32 GB GDDR6);
       the Pi provider advertises 65536. Large agent turns exceed 4096.

Next steps
~~~~~~~~~~

* Write a gemma4 vLLM ``ToolParser`` for the ``<|tool_call>call:name{...}`` / ``<|tool>``
  format, register it, and serve with ``--enable-auto-tool-choice --tool-call-parser
  <gemma4>``; wire it into ``util/tt-llm-server`` local mode. Unblocks Pi tool-calling.
* Upstream the ``warmup_model_decode`` fix to the tt-metal fork; re-validate E2B /
  26B-A4B / 31B served with tracing (they share the same warmup path).
* Raise the served context above 4096 if KV headroom allows (precision / batch trade-offs),
  or have the Pi provider advertise the real 4096 window.

Precision
---------

Weight precision is set per module in
``models/demos/gemma4/precision_overrides.json`` (keyed by model-dir basename and
mesh shape). Allowed values: ``bf16``, ``bfp8``, ``bfp4``, ``fp32``; modules
without an override use the model-wide default (``bf16``). The 12B MLP dominates
the per-token weight read (~8.5 B params, ~70 % of weights), so its precision is
the main decode lever.

Last-token logit accuracy vs the HF golden (base weights, prompt
``"The Tenstorrent Blackhole accelerator is"``; harness
``tests/unit/test_golden_pcc.py``, ``GEMMA_PREC=bf16|bfp8|bfp4``):

.. list-table::
   :header-rows: 1
   :widths: 30 18 12 40

   * - Precision (MLP / attn)
     - last-token PCC
     - top-1
     - top-5
   * - ``bf16`` / ``bf16``
     - 0.996
     - ✓
     - exact order
   * - ``bfp8`` / ``bfp8``
     - 0.997
     - ✓
     - exact order
   * - ``bfp4`` / ``bfp8`` (current)
     - 0.972
     - ✓
     - same set, reordered

``bfp4`` MLP costs ~0.024 PCC and reorders the top-5 tail but preserves the greedy
argmax — greedy output is unaffected; sampled decoding feels the reordered tail.
Decode rises ~16.5 → ~17.9 tok/s/user and per-token MLP DRAM read drops ~9.0 →
~4.8 GB. Flip ``shared_mlp`` back to ``bfp8`` to restore the 0.997 config; cached
weights for both precisions coexist, so switching is instant.

Log
---

**2026-06-05**

* HF reference forward (CPU, transformers 5.10.2) ✓ — ``gemma4_unified`` loads,
  golden logits saved to ``src/gemma4-spike/ref_logits.pt``. Confirmed the 12B is
  dense (no MoE / PLE / KV-share).

**2026-06-06**

* Added ``sjalloq/tt-metal`` as a submodule (``third_party/tt-metal``); the fork
  already implements ``models/demos/gemma4``. Branch ``arg/gemma4_optimizations``
  carries the **12B config** (commit ``8707f63``, config-only).
* Built tt-metal from ``gemma4-opt`` in the 22.04 container (``build_metal.sh`` +
  ``create_venv.sh``); ``import ttnn`` OK. Flashed firmware to bundle **19.10.0**
  and added device passthrough to ``util/tt-build`` so the build container runs
  on-card. (``create_venv.sh`` re-pins ``transformers`` to 4.53.0 — re-apply
  ``models/demos/gemma4/requirements.txt`` after any venv rebuild.)
* Port verified independently: ran base ``unsloth/gemma-4-12b`` through the TT
  model on ``blackhole-1x1`` — last-token **PCC 0.996** vs golden
  ``ref_logits.pt``, identical top-5 tokens (``[496, 5402, 506, 614, 5284]``).
* Root-caused the instruct garbage to a missing ``chat_template.jinja``: the demo
  only chat-templates ``if tokenizer.chat_template``, else feeds raw text to the
  instruct model (loops like ``"Charlie Charlie…"``). The 12B uses a non-standard
  ``<|turn>`` / ``<|channel>thought…`` format — use the shipped template, never
  hand-roll one.
* With the template in the model dir, ``test_demo[blackhole-prefill_128-1x1]`` on
  ``google/gemma-4-12B-it`` generates coherent instruction-following output at
  ~13–16 tok/s/user. **12B bring-up functional.** Cached: transformers 5.10.2
  source at ``.cache/tf5102``; base model at ``.cache/models/gemma-4-12b-base``.
* Wired ``bfp4`` into the demo precision map and set the 12B MLP to ``bfp4`` (attn
  stays ``bfp8``): decode ~16.5 → ~17.9 tok/s/user, last-token PCC 0.997 → 0.972
  (greedy argmax preserved). Added ``tests/unit/test_golden_pcc.py`` to measure
  per-precision PCC against the golden. See `Precision`_.

**2026-06-08**

* Brought the 12B up under ``vllm serve`` (tenstorrent/vllm ``5eb61e8`` + TT plugin, local
  python_env). Served output was garbage while offline parity stayed PCC 1.0. Ruled out the
  kv-cache-groups / page-table layout and HMA tensor-sharing (8-vs-1 KV heads) by real-unifier
  diff and on-device tests. Isolated the cause to the decode-trace path (``trace_mode:"none"``
  serves coherently; ``decode_only`` does not), then to lazy allocation of the per-layer
  page-table buffers *after* the warmup trace capture. Fixed with a ``warmup_model_decode``
  override that pre-allocates them; full traced serving is coherent. See `Serving via vLLM`_.
* Verified the served model end to end through ``util/tt-llm-server`` (local mode) — a chat
  completion returns "Paris". ``util/pi-p150a`` connects but Pi 400s because gemma4 has no
  vLLM tool-call parser; recorded as the next step.

References
----------

* Branch ``arg/gemma4_optimizations`` → local ``gemma4-opt``; demo
  ``models/demos/gemma4/`` (entry ``demo/text_demo.py``)
* HF: ``google/gemma-4-12B-it`` · ungated mirror ``unsloth/gemma-4-12b``
* Spike artifacts: ``src/gemma4-spike/`` (gitignored)
* Build image: ``tt-metal-build:22.04``
