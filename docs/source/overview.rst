Overview
========

The stack
---------

The Tenstorrent stack is installed in five layers. Each :doc:`bringup
<bringup/index>` page documents one.

.. list-table::
   :header-rows: 1
   :widths: 6 28 66

   * - Layer
     - Component
     - Function
   * - 1
     - :doc:`tt-kmd <bringup/driver>`
     - Kernel-mode driver. Exposes the card at ``/dev/tenstorrent``. Built
       from source via DKMS.
   * - 2
     - :doc:`Hugepages <bringup/hugepages>`
     - 4×1 GB hugepages on the card's NUMA node — the host↔device DMA
       aperture. Reserved at boot via systemd.
   * - 3
     - :doc:`Userspace tools <bringup/tooling>`
     - ``tt-smi`` (telemetry) and ``tt-flash`` (firmware), in a ``uv``-managed
       venv on Python 3.12.
   * - 4
     - :doc:`Firmware <bringup/firmware>`
     - On-card firmware bundle. Not flashed; card runs the shipped 18.10.0.
   * - 5
     - :doc:`Metalium <bringup/containers>`
     - Compute runtime (TT-NN / tt-metal). Run as a Docker container.

Getting started
---------------

Prerequisites: BIOS *PCIe AER Reporting Mechanism* set to **OS First**, the
card's blower fan connected, and kernel headers for the running kernel
installed (``linux-headers``). See :doc:`hardware`.

.. code-block:: console

   $ make install        # layer 1: build + load tt-kmd via DKMS
   $ make hugepages      # layer 2: reserve 4×1 GB hugepages, enable at boot
   $ source sourceme     # layer 3: create/activate venv, put util/ wrappers on PATH
   $ tt-smi              # verify: read card telemetry
   $ tt-metalium         # layer 5: shell into the Metalium container

``source sourceme`` provides ``tt-smi`` and ``tt-flash`` from the venv and the
``tt-metalium`` / ``tt-metalium-models`` / ``tt-forge`` container wrappers on
``PATH``. See :doc:`verification` to confirm the full stack.

Repository layout
-----------------

.. code-block:: text

   blackhole/
   ├── Makefile          # Layer 1 + 2: tt-kmd via DKMS, hugepages via systemd
   ├── sourceme          # Layer 3: create/activate the uv venv (tt-smi, tt-flash)
   ├── pyproject.toml    # Python deps (tt-flash, tt-smi) + docs toolchain
   ├── hugepages/        # systemd units + reservation script
   ├── demos/            # smoke_add.py — TT-NN elementwise-add smoke test
   ├── util/             # tt-metalium / tt-metalium-models / tt-forge container wrappers
   ├── docs/             # This documentation (Sphinx, source/ + build/)
   └── tt.guide.txt      # Planning notes
