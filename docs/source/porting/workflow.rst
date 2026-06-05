Porting workflow
================

The end-to-end path to get a model that tt-metal does **not** yet implement
running on the p150a. The work happens in **tt-metal's** ``tt_transformers``
library (``models/tt_transformers/`` in the tt-metal tree, baked into the
``tt-metalium-...-models`` container at ``/tt-metal``).

Key concepts
------------

.. list-table::
   :header-rows: 1
   :widths: 22 78

   * - Term
     - Meaning
   * - **tt_transformers**
     - tt-metal's generic, config-driven decoder-LLM library. One set of TTNN
       building blocks (attention, MLP, RMSNorm, RoPE, LM head) assembled from
       a model's Hugging Face ``config.json``. Many models "just work" when
       their architecture matches an already-implemented pattern.
   * - **Reference model**
     - The Hugging Face (PyTorch) implementation, run on CPU. It is the source
       of truth: the port is correct when its output matches the reference.
   * - **PCC**
     - *Pearson correlation coefficient* between the TT tensor and the
       reference tensor. The standard tt-metal accuracy gate; per-module and
       end-to-end PCC must clear a threshold (typically ``>= 0.99``).
   * - **Host vs device**
     - Weights live in the card's GDDR6; ops run on the Tensix cores. The host
       (this workstation) loads weights, drives the run, and holds the
       reference. Hugepages (:doc:`/bringup/hugepages`) back the host/device
       transfers.
   * - **model_config.py**
     - ``tt_transformers/tt/model_config.py`` — the registry. Maps a base model
       name to HF repo, per-device prefill chunk sizes, head dims, and which
       code paths a model uses. First place to look for "is X supported".

Steps
-----

1. **Scope the architecture.** Find the model on Hugging Face and read its
   ``modular_*.py`` in ``transformers`` — these express a model as an explicit
   diff from a parent class, so they show exactly what changed. Pull
   ``config.json`` (often readable even when the weights are gated) and record
   sizes and feature flags (number of layers, heads, ``head_dim``, sliding vs
   global attention, MoE, etc.). The goal: identify the **delta** versus a
   model tt_transformers already supports.

2. **Check existing support.** ``grep`` ``model_config.py`` and the
   ``reference_outputs/`` directory for the family. A close relative that is
   already implemented (e.g. a previous generation) is the starting point — you
   port the delta, not the whole model.

3. **Get a reference loader.** Confirm the installed ``transformers`` knows the
   model's ``model_type``. Brand-new models often need a **newer transformers**
   than tt-metal pins — run the reference in a throwaway environment with it
   upgraded, not by bumping the whole tt-metal stack. Produce **golden
   outputs** (logits / per-layer activations) on CPU for a fixed prompt.

4. **Map the weights.** Ensure checkpoint keys load into the TT model
   (``tt/load_checkpoints.py`` handles remapping). Gated weights need an HF
   token; an ungated community mirror can unblock early bring-up.

5. **Implement / adapt the model.** In ``tt_transformers/tt/`` — reuse existing
   ``attention.py`` / ``mlp.py`` / ``rope.py`` / norm components where the
   architecture matches, and add only the new behaviour. Register the model in
   ``model_config.py``.

6. **Validate with PCC.** Compare TT output to the golden reference — start
   per-module (one attention block, one MLP), then a single decoder layer, then
   the full model. Chase the first module whose PCC drops; that localises the
   bug.

7. **Bring-up demo.** Run ``models/tt_transformers/demo/simple_text_demo.py``
   against the weights to get real generation on the card.

8. **Serve.** Wire the model into the vLLM fork
   (``tt_transformers/tt/generator_vllm.py``) so ``tt-llm-server`` exposes it on
   an OpenAI endpoint, then point ``pi-p150a`` at it
   (:doc:`/bringup/agentic-harness`).

Single-p150 constraints
-----------------------

* **Memory.** 32 GB GDDR6. A bf16 model needs ``~2 GB per billion params`` for
  weights; the remainder holds the KV cache and activations. This caps model
  size and usable context on one card.
* **Device names.** tt_transformers uses ``p100`` / ``p150`` for single
  Blackhole cards; multi-card configs are ``p150x4`` / ``p150x8`` etc. Many
  models are only validated multi-card.
