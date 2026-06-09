Layer 4 — Firmware
==================

Installed bundle: **19.10.0** (flashed from tt-system-firmware over the shipped
18.10.0). Installed versus required versions are in
:doc:`../reference/current-state`. The procedure below reflashes to the latest
published bundle.

Firmware sources
----------------

Firmware bundles are published in two Tenstorrent repos. Flash from
**tt-system-firmware**:

.. list-table::
   :header-rows: 1
   :widths: 26 16 58

   * - Repo
     - Status
     - Use
   * - `tt-system-firmware <https://github.com/tenstorrent/tt-system-firmware/releases>`_
     - current
     - Flash from here. Active release stream.
   * - `tt-firmware <https://github.com/tenstorrent/tt-firmware/releases>`_
     - archived
     - Read-only, superseded (last release 19.6.0). Do not use.

Each release tag attaches a universal ``fw_pack-<ver>.fwbundle`` (all boards)
plus per-board assets (e.g. ``p150a.fwbundle``). ``tt-flash`` selects the entry
matching the detected board, so the universal pack is the simplest choice.

Check for releases with ``gh`` or the web UI:

.. code-block:: console

   $ gh release list --repo tenstorrent/tt-system-firmware
   $ gh release view v19.10.0 --repo tenstorrent/tt-system-firmware \
       --json assets --jq '.assets[].name'

Releases page: https://github.com/tenstorrent/tt-system-firmware/releases

Procedure
---------

#. Activate the venv so ``tt-flash`` / ``tt-smi`` are on ``PATH``:

   .. code-block:: console

      $ source sourceme

#. Download the bundle (19.10.0 shown):

   .. code-block:: console

      $ curl -LO https://github.com/tenstorrent/tt-system-firmware/releases/download/v19.10.0/fw_pack-19.10.0.fwbundle

#. Check what is currently on the card before writing:

   .. code-block:: console

      $ tt-flash verify        # reports running/flashed bundle

#. Flash. ``tt-flash`` takes the bundle as a positional argument and only writes
   when the bundle version is newer than the ROM:

   .. code-block:: console

      $ tt-flash flash fw_pack-19.10.0.fwbundle

   Add ``--force`` to reflash an equal/older bundle; ``--no-reset`` skips the
   built-in reset.
#. Let the built-in reset finish. ``tt-flash`` runs a ``Stage: RESET`` PCIe link
   reset and waits up to 60 s for the ASIC to return.
#. **Cold power-cycle** if the card does not re-enumerate. On Blackhole a "no
   devices detected" state after flashing typically clears only with a full
   power-off, not a warm reboot.
#. Verify:

   .. code-block:: console

      $ tt-flash verify
      $ tt-smi -s        # confirm fw_bundle_version is now 19.10.0.0

Expected output
---------------

A successful flash over an 18.10.0 ROM:

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

This card was flashed 18.10.0 → 19.10.0; ``tt-smi -s`` now reports
``fw_bundle_version 19.10.0.0``.
