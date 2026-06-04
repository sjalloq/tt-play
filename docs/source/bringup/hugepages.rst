Layer 2 — Hugepages
===================

The Blackhole uses **1 GB hugepages** as the host↔device DMA aperture.
**4×1 GB per card** are reserved on the card's NUMA node. The files under
``hugepages/`` replicate Tenstorrent's ``tt-system-tools`` package (absent on
Arch) and are installed by the ``Makefile``.

Files
-----

``hugepages/hugepages-setup.sh``
   Reservation script. Matches Tenstorrent devices on the PCIe bus (VID
   ``1e52``, Blackhole PID ``b140``), resolves each card's NUMA node, and
   writes the page count to ``…/hugepages-1048576kB/nr_hugepages`` for that
   node. Installed to ``/opt/tenstorrent/bin/hugepages-setup.sh``.

``hugepages/tenstorrent-hugepages.service``
   Oneshot systemd service that runs the script early at boot
   (``Before=sysinit.target``), making the reservation persist across reboots.

``hugepages/hugepages-1G.mount``
   ``hugetlbfs`` mount unit exposing the 1 GB pages at ``/dev/hugepages-1G``
   (mode 0777, ``pagesize=1G``) — the path the containers bind-mount.

Commands
--------

.. code-block:: console

   $ make hugepages            # install script + units, daemon-reload, enable --now
   $ make hugepages-verify     # show reserved pages, mount, service state
   $ make hugepages-uninstall  # disable units, remove files, release the pool

The mount unit's on-disk name is the systemd-escaped path
(``dev-hugepages\x2d1G.mount``); the ``Makefile`` computes it with
``systemd-escape``.

Expected state
--------------

.. code-block:: console

   $ grep -i hugetlb /proc/meminfo
   Hugetlb:         4194304 kB

   $ findmnt /dev/hugepages-1G
   TARGET            SOURCE    FSTYPE    OPTIONS
   /dev/hugepages-1G hugetlbfs hugetlbfs rw,...,pagesize=1024M

   $ systemctl is-enabled tenstorrent-hugepages.service
   enabled

``HugePages_Total`` in ``/proc/meminfo`` tracks the default 2 MB page size and
reads ``0``. The 1 GB reservation is the ``Hugetlb`` total (4 GiB = 4×1 GB) and
the per-node ``hugepages-1048576kB/nr_hugepages`` counters, which read ``4`` on
node 0.
