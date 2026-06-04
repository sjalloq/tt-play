# Minimal makefile for Sphinx documentation
# ---------------------------------------------------------------------------
# Source lives in source/, output goes to build/ (separate trees).
#   make -C docs html      # build HTML into docs/build/html
#   make -C docs clean      # remove docs/build
#   make -C docs help       # list all Sphinx builders
#
# The toolchain (sphinx + sphinx-rtd-theme) is in the `docs` dependency group:
#   uv sync --group docs
# ---------------------------------------------------------------------------

# You can set these variables from the command line, and also from the
# environment for the first two.
SPHINXOPTS    ?=
SPHINXBUILD   ?= sphinx-build
SOURCEDIR     = source
BUILDDIR      = build

# Put it first so that "make" without argument is like "make help".
help:
	@$(SPHINXBUILD) -M help "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)

.PHONY: help Makefile

# Catch-all target: route all unknown targets to Sphinx using the new
# "make mode" option.  $(O) is meant as a shortcut for $(SPHINXOPTS).
%: Makefile
	@$(SPHINXBUILD) -M $@ "$(SOURCEDIR)" "$(BUILDDIR)" $(SPHINXOPTS) $(O)
