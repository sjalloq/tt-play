# Makefile — Tenstorrent Blackhole p150a bringup
# ---------------------------------------------------------------------------
# Layer 1: kernel-mode driver (tt-kmd), installed from source via DKMS.
#
# DKMS is used (rather than a plain `make && insmod`) so the module is
# automatically rebuilt against every future kernel — exactly how the nvidia
# driver on this box already works. The driver source is pinned to a release
# tag for reproducibility; override with e.g. `make install TTKMD_VERSION=2.9.0-rc1`.
#
#   make install     # clone -> checkout -> dkms add -> dkms install -> modprobe
#   make verify      # dkms status + /dev node + dmesg
#   make uninstall   # unload module + deregister from DKMS
#   make clean       # also delete the cloned source tree
#   make help        # list all targets
# ---------------------------------------------------------------------------

# ---- Configuration --------------------------------------------------------
TTKMD_VERSION ?= 2.8.0
TTKMD_TAG     := ttkmd-$(TTKMD_VERSION)
TTKMD_REPO    := https://github.com/tenstorrent/tt-kmd.git
SRC_DIR       := $(CURDIR)/src/tt-kmd
DKMS_NAME     := tenstorrent
DKMS_ID       := $(DKMS_NAME)/$(TTKMD_VERSION)
KVER          := $(shell uname -r)

.DEFAULT_GOAL := help
.PHONY: help check-deps clone checkout dkms-add dkms-install load install \
        verify status uninstall clean \
        hugepages hugepages-verify hugepages-uninstall \
        docs-build docs-serve

# ---- Meta -----------------------------------------------------------------
help:
	@printf 'Tenstorrent tt-kmd bringup (version %s, kernel %s)\n\n' '$(TTKMD_VERSION)' '$(KVER)'
	@printf '  make install      Full driver install: clone -> DKMS build -> modprobe -> verify\n'
	@printf '  make check-deps   Verify git / dkms / gcc / kernel headers are present\n'
	@printf '  make clone        Clone tt-kmd into $(SRC_DIR)\n'
	@printf '  make checkout     Check out tag $(TTKMD_TAG)\n'
	@printf '  make dkms-add     Register the source tree with DKMS\n'
	@printf '  make dkms-install Compile + install the module for kernel %s\n' '$(KVER)'
	@printf '  make load         modprobe tenstorrent\n'
	@printf '  make verify       Show DKMS status, /dev/tenstorrent, and dmesg\n'
	@printf '  make uninstall    Unload + deregister the module (source tree kept)\n'
	@printf '  make clean        uninstall + delete the cloned source tree\n'
	@printf '\n  Hugepages (4x1GB per Blackhole, NUMA-aware, via systemd):\n'
	@printf '  make hugepages          Install + enable the reservation service and 1G mount\n'
	@printf '  make hugepages-verify   Show reserved 1GB pages, mount, and service state\n'
	@printf '  make hugepages-uninstall Disable units, remove files, release pages\n'
	@printf '\n  Docs:\n'
	@printf '  make docs-build         Build the Sphinx HTML (uv sync --group docs + make html)\n'
	@printf '  make docs-serve         Build (if needed) + serve over the LAN (port %s)\n' '$(DOCS_PORT)'

# ---- Prerequisites --------------------------------------------------------
check-deps:
	@echo '==> Checking build prerequisites'
	@command -v git  >/dev/null || { echo 'MISSING: git';  exit 1; }
	@command -v dkms >/dev/null || { echo 'MISSING: dkms (pacman -S dkms)'; exit 1; }
	@command -v gcc  >/dev/null || { echo 'MISSING: gcc';  exit 1; }
	@test -d /lib/modules/$(KVER)/build || { \
		echo 'MISSING: kernel headers for $(KVER) (pacman -S linux-headers)'; exit 1; }
	@echo 'OK: git, dkms, gcc, and headers for $(KVER) are present'

# ---- Source ---------------------------------------------------------------
clone:
	@if [ -d $(SRC_DIR)/.git ]; then \
		echo '==> Source already present at $(SRC_DIR)'; \
	else \
		echo '==> Cloning tt-kmd into $(SRC_DIR)'; \
		git clone $(TTKMD_REPO) $(SRC_DIR); \
	fi

checkout: clone
	@echo '==> Checking out $(TTKMD_TAG)'
	@cd $(SRC_DIR) && git fetch --tags --quiet && git checkout --quiet $(TTKMD_TAG)
	@cd $(SRC_DIR) && printf '    at: ' && git describe --tags

# ---- DKMS -----------------------------------------------------------------
dkms-add: checkout
	@if dkms status $(DKMS_ID) 2>/dev/null | grep -q .; then \
		echo '==> $(DKMS_ID) already registered with DKMS'; \
	else \
		echo '==> dkms add (registers /usr/src/$(DKMS_NAME)-$(TTKMD_VERSION))'; \
		cd $(SRC_DIR) && sudo dkms add .; \
	fi

dkms-install: dkms-add
	@if dkms status $(DKMS_ID) 2>/dev/null | grep -q 'installed'; then \
		echo '==> $(DKMS_ID) already built + installed for current kernel'; \
	else \
		echo '==> dkms install (compiling against $(KVER))'; \
		sudo dkms install $(DKMS_ID); \
	fi

# ---- Load + verify --------------------------------------------------------
load: dkms-install
	@echo '==> modprobe tenstorrent'
	@sudo modprobe tenstorrent
	@lsmod | grep -q '^tenstorrent' \
		&& echo 'OK: tenstorrent module loaded' \
		|| { echo 'FAIL: module did not load — check: sudo dmesg | grep tenstorrent'; exit 1; }

install: check-deps load verify
	@echo ''
	@echo '==> tt-kmd $(TTKMD_VERSION) install complete.'

verify status:
	@echo '==> DKMS status'
	@dkms status | grep $(DKMS_NAME) || echo '   (tenstorrent not registered with DKMS)'
	@echo '==> Device node'
	@ls -l /dev/tenstorrent/ 2>/dev/null || echo '   (/dev/tenstorrent missing — module not loaded?)'
	@echo '==> Kernel log (last 15 tenstorrent lines)'
	@sudo dmesg | grep -i tenstorrent | tail -n 15 || true

# ---- Hugepages ------------------------------------------------------------
# Replicates Tenstorrent's tt-system-tools .deb on Arch: a oneshot service that
# reserves 4x1GB hugepages per Blackhole on the device's NUMA node (run early at
# boot AND now), plus a hugetlbfs mount at /dev/hugepages-1G. Files are vendored
# verbatim under hugepages/. The mount unit's real name is the systemd-escaped
# path, computed here so we don't store an awkward filename in git.
HUGE_DIR    := $(CURDIR)/hugepages
HUGE_SCRIPT := /opt/tenstorrent/bin/hugepages-setup.sh
HUGE_SVC    := tenstorrent-hugepages.service
HUGE_MOUNT  := $(shell systemd-escape --suffix=mount --path /dev/hugepages-1G)
HUGE_NR1G   := /sys/kernel/mm/hugepages/hugepages-1048576kB/nr_hugepages

hugepages:
	@echo '==> Installing reservation script -> $(HUGE_SCRIPT)'
	sudo install -Dm755 $(HUGE_DIR)/hugepages-setup.sh $(HUGE_SCRIPT)
	@echo '==> Installing systemd units'
	sudo install -Dm644 $(HUGE_DIR)/tenstorrent-hugepages.service /etc/systemd/system/$(HUGE_SVC)
	sudo install -Dm644 $(HUGE_DIR)/hugepages-1G.mount '/etc/systemd/system/$(HUGE_MOUNT)'
	sudo systemctl daemon-reload
	@echo '==> Enabling + starting (reserves now and on every boot)'
	sudo systemctl enable --now $(HUGE_SVC)
	sudo systemctl enable --now '$(HUGE_MOUNT)'
	@$(MAKE) --no-print-directory hugepages-verify

hugepages-verify:
	@printf '==> 1GB hugepages reserved (global): %s\n' "$$(cat $(HUGE_NR1G) 2>/dev/null)"
	@for f in /sys/devices/system/node/node*/hugepages/hugepages-1048576kB/nr_hugepages; do \
		printf '    %s = %s\n' "$$f" "$$(cat $$f 2>/dev/null)"; done
	@findmnt /dev/hugepages-1G >/dev/null 2>&1 \
		&& echo '==> Mounted: /dev/hugepages-1G (hugetlbfs, pagesize=1G)' \
		|| echo '==> NOT mounted: /dev/hugepages-1G'
	@printf '==> Service enabled=%s last-result=%s\n' \
		"$$(systemctl is-enabled $(HUGE_SVC) 2>/dev/null || echo no)" \
		"$$(systemctl show -p Result --value $(HUGE_SVC) 2>/dev/null)"

hugepages-uninstall:
	-sudo systemctl disable --now '$(HUGE_MOUNT)'
	-sudo systemctl disable --now $(HUGE_SVC)
	-sudo rm -f /etc/systemd/system/$(HUGE_SVC) '/etc/systemd/system/$(HUGE_MOUNT)' $(HUGE_SCRIPT)
	sudo systemctl daemon-reload
	-echo 0 | sudo tee $(HUGE_NR1G) >/dev/null
	@echo 'Hugepages teardown complete (released 1GB pool).'

# ---- Docs -----------------------------------------------------------------
# Build the Sphinx HTML, then serve it over the LAN with Python's stdlib
# http.server. docs-serve depends on docs-build, so a plain `make docs-serve`
# always serves a fresh build. The build mirrors the flow documented in
# pyproject.toml: sync the `docs` dependency group, then drive docs/Makefile.
#
# docs-serve runs in the foreground (Ctrl-C to stop) and binds all interfaces
# so other hosts can reach it; if ufw is active, open the port for the LAN:
#   sudo ufw allow from 10.0.0.0/24 to any port $(DOCS_PORT) proto tcp
# Override port/bind: make docs-serve DOCS_PORT=9000 DOCS_BIND=127.0.0.1
DOCS_SRC  := $(CURDIR)/docs
DOCS_DIR  := $(DOCS_SRC)/build/html
DOCS_PORT ?= 8000
DOCS_BIND ?= 0.0.0.0

docs-build:
	@echo '==> Syncing docs toolchain (uv sync --group docs)'
	uv sync --group docs
	@echo '==> Building HTML (make -C docs html)'
	uv run $(MAKE) -C $(DOCS_SRC) html

docs-serve: docs-build
	@test -f $(DOCS_DIR)/index.html || { \
		echo 'No built docs at $(DOCS_DIR) — docs-build did not produce HTML.'; exit 1; }
	@printf '==> Serving %s on %s:%s\n' '$(DOCS_DIR)' '$(DOCS_BIND)' '$(DOCS_PORT)'
	@printf '    http://%s:%s/   (Ctrl-C to stop)\n' "$$(hostname -I | awk '{print $$1}')" '$(DOCS_PORT)'
	@cd $(DOCS_DIR) && python3 -m http.server $(DOCS_PORT) --bind $(DOCS_BIND)

# ---- Teardown -------------------------------------------------------------
uninstall:
	@echo '==> Unloading + deregistering $(DKMS_ID)'
	-@sudo modprobe -r tenstorrent
	-@sudo dkms remove $(DKMS_ID) --all
	@echo 'Done. Source tree kept at $(SRC_DIR) (run "make clean" to delete it).'

clean: uninstall
	@echo '==> Removing $(SRC_DIR)'
	@rm -rf $(SRC_DIR)
