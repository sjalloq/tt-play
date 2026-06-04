Layer 5 — Metalium container
============================

The compute runtime (**TT-NN / tt-metal**, *Metalium*) runs as a Docker
container rather than a from-source build, which avoids the libstdc++/libc++
toolchain mismatch of building ``tt-metal`` on Arch.

Wrapper scripts
---------------

Three ``docker run`` wrappers under ``util/`` are committed to the repo.
``sourceme`` exports ``TT_ROOT`` and a ``TT_*_IMAGE`` ref for each, and prepends
``util/`` to ``PATH``, so after ``source sourceme`` they run as bare commands.
Each maps in the device (``/dev/tenstorrent``) and the 1 GB hugepages mount
(``/dev/hugepages-1G``), runs ``--privileged`` on the host network, mounts the
project root at ``/work``, and drops into ``/bin/bash``.

* ``util/tt-metalium`` — slim base image, enough for **TT-NN**
  (``…-release-amd64:latest-rc``, ~4.3 GB). Workdir ``/work``.
* ``util/tt-metalium-models`` — full Metalium build with prebuilt model demos
  (``…-release-models-amd64``, ~12.7 GB). Demo source is baked into the image,
  so it keeps the image's own workdir and still mounts the repo at ``/work``.
* ``util/tt-forge`` — tt-forge / tt-xla image, PyTorch + JAX/XLA front end
  (``ghcr.io/tenstorrent/tt-xla-slim:latest``). Adds the 2 MB hugepage fs and
  ``/lib/modules`` mounts that Forge requires.

The Metalium images are pulled on this machine; the Forge image pulls on first
``tt-forge`` run. Override an image ref by exporting ``TT_METALIUM_IMAGE`` /
``TT_METALIUM_MODELS_IMAGE`` / ``TT_FORGE_IMAGE`` before sourcing.

Running
-------

.. code-block:: console

   $ source sourceme        # activates the venv, puts util/ on PATH
   $ tt-metalium            # bash shell inside the slim container

Inside the container the device and hugepages are visible and ``ttnn`` is
importable. See :doc:`../verification` for the TT-NN smoke test.

Demos
-----

Model demos live in the ``tt-metalium-models`` image under ``models/demos/`` and
run with ``pytest`` (the image bakes the tt-metal source at ``/tt-metal``, so
``ttnn`` and ``TT_METAL_HOME`` are preset with no venv). The wrapper mounts a
project-local ``.cache/`` at the container's ``/root/.cache``, so HuggingFace
weights and compiled Blackhole kernels persist across runs. On a single p150a use
the single-device variants only — not the ``_dp`` (two-device) ones.

smoke_add.py
~~~~~~~~~~~~

A torch-free TT-NN elementwise-add — the minimal proof the Tensix cores compute
and round-trip a result. Documented as the smoke test in :doc:`../verification`.

SentenceBERT
~~~~~~~~~~~~

``bert-base-turkish-cased-mean-nli-stsb-tr``: a BERT-base sentence-embedding
model for semantic textual similarity (semantic search, clustering, dedup). The
only Blackhole-tuned demo baked into the image — a full transformer encoder on
the Tensix cores at batch 8, bf16 activations / bf8 weights. The correctness test
matches the Torch reference at PCC ≈ 0.995:

.. code-block:: console

   $ tt-metalium-models
   # pytest --disable-warnings models/demos/blackhole/sentence_bert/tests/pcc/test_ttnn_sentencebert_model.py::test_ttnn_sentence_bert_model

.. code-block:: text

   SentenceBERT - batch_size=8, PCC=0.9946599145809459, act_dtype:DataType.BFLOAT16, weight_dtype:DataType.BFLOAT8_B
   1 passed

The interactive and performant entrypoints (``demo/demo.py``,
``demo/interactive_demo.py``, ``tests/perf/``) route through the Trace+2CQ
runner, which aborts on a non-deterministic input-buffer address in the
``latest-rc`` image — the model forward pass runs and validates first, so the
fault is in the demo harness, not the stack.

.. todo::

   Trace+2CQ SentenceBERT demos abort at ``performant_runner.py:133`` (input
   buffer-address assert) on the ``…-release-models-amd64:latest-rc`` image.
   Retry on a pinned stable image tag (``TT_METALIUM_MODELS_IMAGE``) or report
   upstream.
