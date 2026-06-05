Layer 4 — Firmware
==================

Firmware is **not flashed** by anything in this repo. The card runs the shipped
bundle **18.10.0** (``FLASH_BUNDLE_VERSION 0x120a0000``), which is sufficient
for the driver to enumerate it and for ``tt-smi`` to read full telemetry.
``tt-flash`` 3.8.0 is installed in the venv for when an update is needed.

Flashing is a deliberate manual step. It is not run automatically and the
driver, firmware, and SMI versions must be mutually compatible.

Where firmware comes from
-------------------------

Firmware bundles moved repositories. The old ``tenstorrent/tt-firmware`` repo
was **archived 2026-02-25** and is read-only. Current releases live in
`tt-system-firmware <https://github.com/tenstorrent/tt-system-firmware/releases>`_.

.. list-table::
   :header-rows: 1
   :widths: 30 25 45

   * - Item
     - Value
     - Notes
   * - Latest stable bundle
     - 19.10.0 (2026-06-01)
     - ``fw_pack-19.10.0.fwbundle`` (universal, all boards)
   * - Board-specific asset
     - ``p150a.fwbundle``
     - smaller, p150a only — either bundle works
   * - Installed on card
     - 18.10.0
     - ``cm_fw`` 0.19.0.0; not yet updated

Each release tag attaches a universal ``fw_pack-<ver>.fwbundle`` plus
per-board ``*.fwbundle`` assets. ``tt-flash`` picks the entry matching the
detected board, so the universal pack is the simplest choice.

.. warning::

   **Core-count reduction.** Bundle **19.5.0 and later** reduce the p150 Tensix
   grid from 140 to 120 cores to match cards shipping from January 2026
   (Tenstorrent quotes ~1–2 % workload impact). Flashing 19.x onto this card is
   a one-way change to 120 cores. Staying on 18.10.0 keeps 140 cores. Decide
   before flashing.

Procedure
---------

#. Pick a target bundle. If a specific ``tt-metal`` release is the goal, match
   driver + firmware + SMI to that release's compatibility matrix rather than to
   the illustrative versions in any docs.
#. Download the bundle into the repo (or anywhere on disk):

   .. code-block:: console

      $ curl -LO https://github.com/tenstorrent/tt-system-firmware/releases/download/v19.10.0/fw_pack-19.10.0.fwbundle

#. Flash it. ``tt-flash`` takes the bundle as a positional argument and only
   writes when the bundle version is newer than the ROM:

   .. code-block:: console

      $ tt-flash fw_pack-19.10.0.fwbundle

   ``tt-flash flash <bundle>`` is the equivalent explicit form. Add ``--force``
   to reflash an equal/older bundle.
#. Let the built-in reset finish. ``tt-flash`` runs a ``Stage: RESET`` PCIe link
   reset and waits up to 60 s for the ASIC to return. ``--no-reset`` skips it.
#. **Cold power-cycle** if the card does not re-enumerate. On Blackhole a "no
   devices detected" state after flashing typically clears only with a full
   power-off, not a warm reboot.
#. Verify:

   .. code-block:: console

      $ tt-flash verify
      $ tt-smi -s        # confirm fw_bundle_version is now 19.10.0.0

Expected output
---------------

Illustrative run from the ``tt-flash`` README (upstream), flashing over an
18.10.0 ROM — the same starting bundle as this card:

.. code-block:: text

   Stage: SETUP
   Stage: DETECT
   Stage: FLASH
           Sub Stage: VERIFY
                   Verifying fw-package can be flashed: complete
                   Verifying Blackhole[0] can be flashed
           Stage: FLASH
                   Sub Stage FLASH Step 1: Blackhole[0]
                           ROM version is: (18, 10, 0, 0).
                           FW bundle version > ROM version. ROM will now be updated.
                   Sub Stage FLASH Step 2: Blackhole[0] {p150a}
                           Writing new firmware... SUCCESS
                           Verifying flashed firmware... SUCCESS
   Stage: RESET
    Starting PCI link reset on BH devices at PCI indices: 0
    Waiting for up to 60 seconds for asic to come back after reset
    Finishing PCI link reset on BH devices at PCI indices: 0
   FLASH SUCCESS

.. todo::

   Capture the real before/after ``tt-smi`` bundle versions here once this card
   is actually flashed, and update :doc:`../reference/current-state`.
