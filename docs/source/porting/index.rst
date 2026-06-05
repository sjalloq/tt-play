Porting models
==============

How to bring a new model up on the Blackhole p150a so it runs under
**tt-metal** and serves through the vLLM fork (Layer 5/6 of the stack — see
:doc:`/bringup/agentic-harness`).

This section has two halves:

* **Generic** — the reusable workflow and concepts, independent of any one
  model. Start with :doc:`workflow`.
* **Model logs** — a per-model work log under :doc:`models/index`, recording
  what had to be fixed, written, or worked around for each port. These are
  deliberately kept as **logs** (chronological, specific), unlike the rest of
  the docs.

When a model is fully supported by tt-metal already, this is not a "port" —
just run it via ``tt-llm-server`` (:doc:`/bringup/agentic-harness`). Porting is
for models tt-metal does **not** yet implement.

.. toctree::
   :maxdepth: 2
   :caption: Generic

   workflow

.. toctree::
   :maxdepth: 2
   :caption: Model logs

   models/index
