Troubleshooting
===============

``Failed to set initial power state: -22``
-------------------------------------------

On module load (and on each ``tt-smi`` read) the kernel log shows:

.. code-block:: text

   tenstorrent tenstorrent!0: Failed to set initial power state: -22

``-22`` is ``-EINVAL``. The card still enumerates: the device node appears,
``tt-smi`` reads full telemetry, and DKMS reports the module installed. Treated
as benign; likely related to the unflashed firmware or the PCIe link state.

.. todo::

   Check whether ``Failed to set initial power state: -22`` clears after a
   firmware flash (:doc:`../bringup/firmware`) or relates to the Gen2 x8 PCIe
   downgrade.

Card not detected
-----------------

* **BIOS:** PCIe AER Reporting Mechanism must be **OS First** (see
  :doc:`../hardware`) — most common cause.
* **Driver loaded:** ``lsmod | grep tenstorrent`` and
  ``sudo dmesg | grep -i tenstorrent``.
* **Cold power-cycle:** on Blackhole p100/p150, "no devices detected" —
  especially right after a firmware flash — often clears only with a full
  power-cycle, not a warm reboot.
* **Fan:** the blower header must be connected; an overheating card misbehaves.

PCIe link trains at Gen2 x8
---------------------------

The p150a is Gen5 x16 capable but trains at Gen2 x8 on this workstation, capped
by the upstream bridge ``00:03.2`` (~16× link-bandwidth loss). Re-check with
``lspci`` after any BIOS update or re-seat. It limits host↔device throughput;
it does not stop the card working.

uv cannot resolve tt-umd
------------------------

``uv sync`` failing to resolve ``tt-umd`` indicates the wrong interpreter: it
ships wheels for cp310–cp313 only — no cp314, no sdist. Use Python 3.10–3.12
(default 3.12):

.. code-block:: console

   $ source sourceme --clean --python 3.12

Upstream tt-installer reboots mid-run
-------------------------------------

The upstream ``tt-installer`` defaults to ``reboot-option=ask``, which in
non-interactive mode resolves to "reboot". Pass ``--reboot-option never`` when
running it directly.
