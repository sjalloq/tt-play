Current state
=============

Authoritative current state of the stack — the single source for live versions,
firmware, link state, and install status. Update **this page** when any of them
change; other pages cross-reference it rather than restating values.

Stack
-----

.. list-table::
   :header-rows: 1
   :widths: 30 18 52

   * - Layer
     - Status
     - Detail
   * - tt-kmd (driver)
     - installed
     - 2.8.0 via DKMS; ``/dev/tenstorrent/0`` present
   * - Hugepages
     - configured
     - 4×1 GB on node 0; mounted at ``/dev/hugepages-1G``; enabled at boot
   * - tt-smi / tt-flash
     - installed
     - 5.2.0 / 3.8.0 in the ``uv`` venv (Python 3.12.13)
   * - Firmware
     - flashed
     - bundle 19.10.0
   * - Metalium containers
     - pulled
     - slim (~4.3 GB) + models (~12.7 GB); wrappers in ``util/``
   * - tt-forge container
     - not pulled
     - pulls on first ``tt-forge`` run
   * - TT-NN smoke test
     - passing
     - ``demos/smoke_add.py`` → ``RESULT: PASS`` (:doc:`../verification`)

Versions
--------

Installed versus the baseline required by the Gemma 4 / tt-metal Blackhole build
(branch ``arg/gemma4_optimizations``, ``INSTALLING.md``). All components meet or
exceed the build baseline.

.. list-table::
   :header-rows: 1
   :widths: 24 40 36

   * - Component
     - Installed
     - Required (BH build)
   * - OS / kernel
     - Arch Linux, ``7.0.3-arch1-2``, x86-64
     - Ubuntu 22.04 (build container)
   * - Python
     - 3.12.13 (venv)
     - 3.10 (build container)
   * - tt-kmd
     - 2.8.0
     - v2.5.0 or above ✓
   * - tt-smi
     - 5.2.0
     - v3.0.38 or above ✓
   * - tt-flash
     - 3.8.0
     - 3.8.0 ✓
   * - pyluwen
     - 0.8.5
     - —
   * - tt-umd
     - 0.9.5
     - —
   * - Firmware bundle
     - 19.10.0
     - 19.2.0 or above ✓ (:doc:`../bringup/firmware`)

Device
------

.. list-table::
   :widths: 35 65

   * - Card
     - Blackhole p150a
   * - PCIe address
     - ``0000:0b:00.0`` (``1e52:b140``)
   * - PCIe link
     - Gen4 x8 (Gen5 x16 capable — old hardware; no money for RAM)
   * - Board ID
     - ``0x403`` / ``0x3192a04d``

Evidence
--------

Captured on host ``jalapeno``.

.. code-block:: console

   $ dkms status
   nvidia/580.159.03, 7.0.3-arch1-2, x86_64: installed
   tenstorrent/2.8.0, 7.0.3-arch1-2, x86_64: installed

   $ ls /dev/tenstorrent/
   0  by-id

   $ grep -i hugetlb /proc/meminfo
   Hugetlb:         4194304 kB

   $ docker images | grep tenstorrent
   .../tt-metalium-ubuntu-22.04-release-amd64:latest-rc          4.33GB
   .../tt-metalium-ubuntu-22.04-release-models-amd64:latest-rc   12.7GB
