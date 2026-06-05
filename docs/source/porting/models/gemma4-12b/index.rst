gemma4:12b
==========

Work log for porting **Gemma 4 12B** (``google/gemma-4-12B-it``) to run on a
single p150a under ``tt_transformers`` and serve through the vLLM fork.

:Target: ``google/gemma-4-12B-it`` (instruct) — text generation to back
   ``pi-p150a``
:Status: 🛠️ bring-up in progress — reference forward ✓ (golden logits
   captured); device port next
:Approach: loading spike first (run weights through the existing Gemma 3 path,
   capture the first break, then port the delta)

Summary of the gap
------------------

Gemma 4 is **not** in tt-metal (neither the pinned release image nor ``main``);
only Gemma 3 (1b/4b/27b) and medgemma are implemented. So this is a genuine
port, not a config change. Two concrete blockers found up front:

* tt-metal pins ``transformers == 4.53.0``, which knows ``gemma``, ``gemma2``,
  ``gemma3``, ``gemma3n`` — **not** ``gemma4_unified``. The reference loader
  needs a newer transformers (5.x; latest is ``5.10.2``).
* No TTNN implementation of the Gemma 4 attention/norm changes exists.

The 12B model
-------------

``config.json`` is readable on the gated Google repo (only the weights are
gated). The 12B reports ``model_type: gemma4_unified`` /
``Gemma4UnifiedForConditionalGeneration``, and sits at the **simple end** of the
Gemma 4 feature space:

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - Config
     - Value (12B)
     - Consequence
   * - ``enable_moe_block``
     - ``False``
     - dense — skip the MoE router/experts path entirely
   * - ``num_kv_shared_layers``
     - ``0``
     - no cross-layer KV sharing — normal cache
   * - ``hidden_size_per_layer_input``
     - ``0``
     - no Gemma3n per-layer-inputs machinery
   * - ``num_hidden_layers``
     - 48
     -
   * - ``hidden_size``
     - 3840
     -
   * - ``num_attention_heads`` / ``num_key_value_heads``
     - 16 / 8
     - GQA
   * - ``layer_types``
     - 40 ``sliding_attention`` + 8 ``full_attention``
     - hybrid local/global (Gemma 3 already does this)
   * - ``vocab_size``
     - 262144
     -

In transformers, ``Gemma4UnifiedTextDecoderLayer`` subclasses
``Gemma2DecoderLayer`` (a plain dense layer) and uses
``Gemma4UnifiedTextAttention(Gemma4TextAttention)`` — so the 12B is a
**dense Gemma2/3-style decoder with Gemma 4's new attention**.

Architecture delta (vs Gemma 3, already in tt-metal)
----------------------------------------------------

What actually has to be ported on top of the existing Gemma 3 implementation:

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Change
     - Detail
   * - **V-norm**
     - Gemma 4 adds an RMSNorm on ``value`` states (``with_scale=False``)
       alongside the existing q/k-norm. New op in the attention block.
   * - **Per-layer-type attention geometry**
     - 40 sliding layers: ``head_dim`` 256, 8 KV heads, ``sliding_window``
       1024. 8 global layers: ``head_dim`` **512**, **1** KV head, and
       ``attention_k_eq_v=True`` so **V = K** (no ``v_proj``). Two distinct
       shapes within one model; the K=V global trick is new.
   * - ``scaling = 1.0``
     - QK-norm replaces the attention scalar (Gemma 3 used
       ``query_pre_attn_scalar``).
   * - **layer_scalar**
     - per-layer learned scalar multiply on the residual stream. Trivial
       elementwise.
   * - **RMSNorm flavour**
     - ``Gemma4RMSNorm`` derives from ``Gemma3nRMSNorm``; confirm the exact
       form (scale, epsilon placement) matches for PCC.

Feasibility
-----------

bf16 weights ``~24 GB`` fit the 32 GB GDDR6 with ``~8 GB`` left for KV cache and
activations. GQA plus the 1024-token sliding window on 40 of 48 layers keeps the
KV cache small. Workable, but context will be limited on one card.

Open items
----------

* **Device port blocker:** tt-metal pins ``transformers == 4.53.0``, which
  cannot even parse the ``gemma4_unified`` config — so the tt_transformers path
  can't load the model as-is. Decide between bumping tt-metal's transformers to
  5.x (risk: API drift across other reference paths) vs. defining the
  ``gemma4_unified`` config/reference inside tt_transformers directly.
* Diff ``Gemma3nRMSNorm`` vs the tt-metal Gemma 3 RMSNorm.
* Decide how to register two attention geometries per model in
  ``model_config.py`` (Gemma 3 assumes uniform head dims).
* Instruct weights (``-it``) are gated — needs HF token + Gemma-4 license for
  the served model; the ungated ``unsloth/gemma-4-12b`` base mirror is used for
  the spike.

Log
---

**2026-06-05**

* Established Gemma 4 absent from tt-metal (``main`` and release image);
  transformers 4.53.0 lacks ``gemma4_unified``.
* Pulled ``config.json`` for the 12B — confirmed dense, no MoE / KV-share /
  per-layer-inputs.
* Read ``modular_gemma4.py`` / ``modular_gemma4_unified.py`` — extracted the
  architecture delta above.
* Found ``unsloth/gemma-4-12b`` is ungated (``gated: False``) with weights —
  unblocks the spike without the Google license.
* Staged ``src/gemma4-spike/ref_forward.py`` (CPU reference forward + golden
  logits). Downloaded the 23 GB ``unsloth/gemma-4-12b`` snapshot into the repo
  ``.cache``.
* **Reference forward ✓** — under transformers 5.10.2, ``gemma4_unified`` loads
  and ``AutoModelForCausalLM`` maps the multimodal checkpoint
  (``Gemma4UnifiedForConditionalGeneration``) for text-only use. Live config
  confirmed ``moe=False``, 48 layers, head_dim 256. Prompt *"The Tenstorrent
  Blackhole accelerator is"* → top tokens `` a`` / `` designed`` / `` the`` /
  `` built`` / `` optimized``. Golden logits saved to
  ``src/gemma4-spike/ref_logits.pt`` (262k vocab) for PCC.

  **Env gotchas (the reference must run *outside* the tt-metal env):**

  * Installing ``transformers==5.10.2`` over tt-metal's pinned ``4.53.0`` hit a
    resolver conflict; a ``-q ... | tail`` pipe hid the error and the run
    silently fell back to 4.53.0. Always surface pip output.
  * ``python -m venv --system-site-packages`` from the tt-metal image does
    **not** expose its torch — the image's interpreter is itself a venv
    (``/opt/venv``), and venv-from-venv only inherits the *base* interpreter.
  * Working recipe: a clean ``python:3.12-slim`` container with CPU torch
    (``--index-url https://download.pytorch.org/whl/cpu``) + ``transformers``
    + ``accelerate``, weights mounted from ``.cache`` with ``HF_HUB_OFFLINE=1``.

* **Device path breaks at config parse (first failure in the spike).** Pointing
  tt_transformers at the weights (``HF_MODEL=<snapshot>``) fails inside
  ``_set_hf_params`` → ``AutoConfig.from_pretrained`` with tt-metal's pinned
  ``transformers 4.53.0``::

     ValueError: The checkpoint you are trying to load has model type
     `gemma4_unified` but Transformers does not recognize this architecture.

  So the device port is gated on making tt-metal's environment understand
  ``gemma4_unified`` *before* any TTNN work. Spike complete — see Open items for
  the approach decision.

References
----------

* HF model: ``google/gemma-4-12B-it`` · ungated mirror ``unsloth/gemma-4-12b``
* transformers source: ``models/gemma4_unified/modular_gemma4_unified.py``
* Spike artifacts: ``src/gemma4-spike/`` (gitignored)
* tt-metal: ``models/tt_transformers/tt/model_config.py``,
  ``tt/attention.py``, ``demo/simple_text_demo.py``
