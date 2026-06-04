Current state
=============

Verified snapshot, captured 2026-06-04 on host ``jalapeno``.

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
     - not flashed
     - card at shipped bundle 18.10.0
   * - Metalium containers
     - pulled
     - slim (~4.3 GB) + models (~12.7 GB); wrappers in ``util/``
   * - tt-forge container
     - not pulled
     - pulls on first ``tt-forge`` run
   * - TT-NN smoke test
     - not run
     - ``demos/smoke_add.py`` ready

Versions
--------

.. list-table::
   :widths: 35 65

   * - OS / kernel
     - Arch Linux, ``7.0.3-arch1-2``, x86-64
   * - tt-kmd
     - 2.8.0
   * - tt-smi
     - 5.2.0
   * - tt-flash
     - 3.8.0
   * - pyluwen
     - 0.8.5
   * - tt-umd
     - 0.9.5
   * - Firmware bundle
     - 18.10.0 (``FLASH_BUNDLE_VERSION 0x120a0000``)

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
