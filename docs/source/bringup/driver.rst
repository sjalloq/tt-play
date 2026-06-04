Layer 1 — Kernel driver (tt-kmd)
================================

``tt-kmd`` exposes the card to userspace as ``/dev/tenstorrent``. It is built
from source via DKMS so the module rebuilds automatically on kernel updates.
The source is pinned to tag ``ttkmd-2.8.0``.

Commands
--------

.. code-block:: console

   $ make install      # clone → checkout tag → dkms add → dkms install → modprobe → verify
   $ make verify       # dkms status + /dev/tenstorrent + dmesg
   $ make uninstall    # unload + deregister from DKMS (keeps source tree)
   $ make clean        # uninstall + delete the cloned source tree
   $ make help         # list all targets

Override the version with ``make install TTKMD_VERSION=2.9.0-rc1``. Targets are
idempotent (each checks ``dkms status`` before acting), so ``make install`` is
safe to re-run.

Prerequisites
-------------

``make check-deps`` requires ``git``, ``dkms``, ``gcc``, and kernel headers for
the running kernel (``/lib/modules/$(uname -r)/build`` — the ``linux-headers``
package, or ``linux-lts-headers`` to match the kernel).

Expected state
--------------

.. code-block:: console

   $ dkms status
   tenstorrent/2.8.0, 7.0.3-arch1-2, x86_64: installed

   $ ls -l /dev/tenstorrent/
   crw-rw-rw- 1 root root 510, 0 ... 0
   drwxr-xr-x 2 root root ...      by-id

   $ modinfo tenstorrent | grep -E 'version|filename'
   filename:  /lib/modules/7.0.3-arch1-2/updates/dkms/tenstorrent.ko.zst
   version:   2.8.0

Kernel log on module load:

.. code-block:: text

   Loading Tenstorrent AI driver module v2.8.0.
   Found a Tenstorrent Blackhole device at bus 0000:0b.
   tenstorrent 0000:0b:00.0: enabling device (0000 -> 0002)

A ``Failed to set initial power state: -22`` line may also appear; the card
still enumerates. See :doc:`../reference/troubleshooting`.
