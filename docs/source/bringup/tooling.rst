Layer 3 — Userspace tools
=========================

Two Python tools run on top of the driver:

* **tt-smi** — system management and telemetry.
* **tt-flash** — firmware flashing (see :doc:`firmware`).

Both pull in **pyluwen** (Rust system-interface binding) and **tt-umd**
transitively.

The venv
--------

The tools live in a project-local venv managed by **uv**. Dependencies are
declared in ``pyproject.toml`` and locked in ``uv.lock``:

.. code-block:: toml

   dependencies = [
       "tt-flash>=3.8.0",   # >=3.6.0 required to avoid Blackhole board-ID loss
       "tt-smi>=5.2.0",
   ]

Activate by sourcing ``sourceme`` (it must be sourced, not executed, so the
venv activates in the current shell). It runs ``uv sync`` (creates ``.venv``,
resolves, locks, installs), activates the venv, and puts the ``util/``
container wrappers on ``PATH``:

.. code-block:: console

   $ source sourceme                  # create (if missing) or reuse .venv, then activate
   $ source sourceme --clean          # delete and recreate .venv from scratch
   $ source sourceme --python 3.10    # use a specific interpreter

.. important::

   The default interpreter is **3.12** — the newest Python with ``tt-umd``
   wheels (cp310–cp313) that is also within ``tt-metal``'s supported range
   (3.10–3.12). Python **3.14 does not work**: ``tt-umd`` ships no cp314 wheel
   and no sdist. ``uv`` auto-downloads a managed 3.12 if the system lacks one.

Versions
--------

.. list-table::
   :widths: 30 70

   * - Python
     - 3.12.13 (in ``.venv``)
   * - tt-smi
     - 5.2.0
   * - tt-flash
     - 3.8.0
   * - pyluwen
     - 0.8.5 *(transitive)*
   * - tt-umd
     - 0.9.5 *(transitive)*

See :doc:`../verification` for using ``tt-smi`` to confirm the card.
