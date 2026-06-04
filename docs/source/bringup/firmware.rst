Layer 4 — Firmware
==================

Firmware is **not flashed** by anything in this repo. The card runs the shipped
bundle **18.10.0** (``FLASH_BUNDLE_VERSION 0x120a0000``), which is sufficient
for the driver to enumerate it and for ``tt-smi`` to read full telemetry.
``tt-flash`` 3.8.0 is installed in the venv for when an update is needed.

Flashing is a manual step. The driver, firmware, and SMI versions must be
mutually compatible.

Procedure
---------

#. Check the compatibility matrix for the target ``tt-metal`` release and match
   driver + firmware + SMI to it (do not rely on illustrative version examples
   in the docs).
#. ``tt-flash`` the new bundle.
#. **Full power-cycle** afterward, not a warm reboot. On Blackhole p100/p150 a
   "no devices detected" message right after flashing usually clears only with
   a cold boot.
#. Re-run ``tt-smi`` to confirm the new bundle version.

.. todo::

   Flash firmware once a target ``tt-metal`` release is chosen and its
   driver/firmware/SMI matrix confirmed. Record before/after bundle versions
   here.
