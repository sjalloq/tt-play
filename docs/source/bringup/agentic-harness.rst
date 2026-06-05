Layer 6 — Agentic harness (Pi + local LLM)
==========================================

Run the `Pi <https://pi.dev>`_ coding agent against an LLM served locally on the
p150. Pi is bring-your-own-key and speaks the OpenAI HTTP API; the model backend
is the **tt-inference-server vLLM** (tt-metal integration fork) image, which
exposes an OpenAI-compatible endpoint on ``:8000``.

.. code-block:: text

   Pi (Node CLI, host)  ──OpenAI /v1──▶  vLLM (Docker, tt-metal fork)  ──▶  p150

Model support
-------------

A **single p150** runs ``Llama-3.1-8B-Instruct`` only (status: experimental).
Larger coding models (Qwen3-32B, Llama-3.3-70B) require ``p150x4``/``p150x8``.

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Parameter
     - Value (single p150)
   * - Model
     - ``Llama-3.1-8B-Instruct`` (use Instruct, not the base weights)
   * - Image
     - ``ghcr.io/tenstorrent/tt-inference-server/vllm-tt-metal-src-release-ubuntu-22.04-amd64:0.10.0-55fd115-aa4ae1e``
   * - tt-metal / vLLM commit
     - ``55fd115`` / ``aa4ae1e``
   * - Max context
     - 65536
   * - Max batch
     - 32

Files
-----

* ``util/tt-llm-server`` — ``docker run`` wrapper for the vLLM server on the
  p150. Publishes ``:8000``, mounts ``/dev/tenstorrent`` and
  ``/dev/hugepages-1G``, and caches weights + compiled kernels in the named
  volume ``tt_llm_cache_<model>``. ``sourceme`` exports ``TT_LLM_IMAGE``.
* ``pi/tt-p150a-provider.ts`` — Pi extension registering the ``tt-p150a``
  provider (``api: openai-completions``, ``baseUrl http://localhost:8000/v1``).
  Discovers the served model id from ``/v1/models`` at startup, falling back to
  the static ``Llama-3.1-8B-Instruct`` entry when the server is down.
* ``util/pi-p150a`` — launches ``pi`` with that extension and provider selected.

Commands
--------

.. code-block:: console

   $ export HF_TOKEN=hf_...           # accept the Llama-3.1 license on HF first
   $ tt-llm-server                    # boots vLLM; first run pulls weights + JITs kernels
   $ curl -s localhost:8000/health    # wait for 200 before connecting Pi
   $ pi-p150a                         # Pi, wired to the local model

Auth is **off by default** (no ``JWT_SECRET``), so any non-empty client key
works. To enforce Bearer auth, start the server with ``JWT_SECRET`` set and
export the matching token as ``TT_LLM_API_KEY`` for Pi; the token is
``HS256(JWT_SECRET, {"team_id": "tenstorrent", "token_id": "debug-test"})``.

Expected state
--------------

.. todo::

   Capture ``/health`` 200, ``/v1/models``, and a first Pi exchange once the
   server has been booted against firmware bundle 18.10.0. The image pins
   tt-metal ``55fd115``; if it requires a newer bundle than the shipped
   18.10.0, the firmware flash in :doc:`firmware` becomes a prerequisite.
