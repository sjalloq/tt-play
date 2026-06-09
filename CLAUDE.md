# CLAUDE.md

Guidance for working in this repo.

## What this is

A setup and development environment for a **Tenstorrent Blackhole p150a** PCIe
accelerator on an Arch Linux workstation. The Tenstorrent stack is installed
manually in layers (Arch is not supported by the official `tt-installer`):

| Layer | Component                         | Installed by                                     |
|-------|-----------------------------------|--------------------------------------------------|
| 1     | `tt-kmd` kernel driver (DKMS)     | `make install`                                   |
| 2     | 4×1 GB hugepages (systemd)        | `make hugepages`                                 |
| 3     | `tt-smi` / `tt-flash` (uv venv)   | `source sourceme`                                |
| 4     | Firmware                          | manual `tt-flash` (not flashed; card at 18.10.0) |
| 5     | Metalium / TT-NN / Forge (Docker) | `util/tt-*` wrappers                             |

## Repo structure

```
Makefile        Layers 1+2: tt-kmd via DKMS, hugepages via systemd
sourceme        Layer 3: create/activate uv venv; puts util/ wrappers on PATH
pyproject.toml  Python deps (tt-flash, tt-smi) + dependency groups (dev, docs)
hugepages/      systemd units + reservation script (vendored)
util/           tt-metalium / tt-metalium-models / tt-forge docker run wrappers
demos/          TT-NN experiments (e.g. smoke_add.py), run inside the container
docs/           Sphinx documentation (source/ + build/)
```

## Conventions

- **Don't commit or push unless asked.** `main` is the working branch.
- **Python is pinned to 3.12.** `tt-umd` ships wheels for cp310–cp313 only (no cp314, no sdist). Never bump the `sourceme` default above 3.12.
- **The venv is uv-managed and lockless.** `source sourceme` runs `uv venv` + `uv pip install -e .`, resolving deps fresh from `pyproject.toml` — there is no `uv.lock`. Edit deps in `pyproject.toml`. Don't introduce `uv sync` (it would create a lock); install optional groups with `uv pip install --group <name>`.
- **`sourceme` must be sourced, not executed** — it activates the venv and exports `TT_ROOT` / `TT_*_IMAGE` in the caller's shell.
- **Makefile targets are idempotent** — they check `dkms status` / systemd state before acting. Safe to re-run.
- **Firmware is never touched automatically.** Flashing is a deliberate manual step (see `docs/source/bringup/firmware.rst`).
- `src/` (cloned tt-kmd source) and `docs/build/` are gitignored.
- **Don't ignore my requests.** If you think I'm mistaken, pause and ask a question, don't head off on a tangent.
- **Assume everything we are doing is targetted at a single P150a**. Don't suggest running locally on the host; don't tell me models aren't built for a single P150; 

## Writing docs

Docs live in `docs/source/` (reStructuredText, Sphinx, RTD theme). Build with:

```sh
uv pip install --group docs     # once, to install the toolchain into the venv
make -C docs html               # output in docs/build/html
make -C docs html SPHINXOPTS="-W --keep-going"   # warnings as errors (use before declaring done)
```

**Style — this is a concise engineering reference, not a log.**

- **State facts and procedures.** Present tense, declarative. "The card runs bundle 18.10.0", not "we decided to defer flashing because…".
- **No history, no running commentary, no rationale prose.** Drop "Why we did X" sections. If a *reason* is operationally necessary, state it in one clause, not a paragraph. If a past mistake is actionable, record only the action (e.g. "pass `--reboot-option never`"), not the story.
- **Minimise first person.** Avoid "we"/"our".
- **Prefer tables and command blocks** over paragraphs for specs, versions, and steps. Use `.. code-block:: console` for shell, `text` for log output. 
- **Page shape for a stack layer:** one-line description → `Commands` / `Files` → `Expected state` (real captured output). Keep it scannable.
- **Quote real, verified values** (versions, IDs, paths, addresses). When something is unverified or pending, mark it with `.. todo::` rather than inventing output.
- **Cross-reference** with `:doc:` rather than repeating content. Authoritative current values live in `reference/current-state.rst`.

When a fact changes (new driver/firmware/tool version, link state, what's installed), update `reference/current-state.rst` and any layer page that asserts the old value.
