# Configuration file for the Sphinx documentation builder.
#
# For the full list of built-in configuration values, see the documentation:
# https://www.sphinx-doc.org/en/master/usage/configuration.html

# -- Project information -----------------------------------------------------

project = "Tenstorrent P150a Bringup"
author = "Shareef Jalloq"
copyright = "2026, Shareef Jalloq"

# The project is a rolling learning/dev log rather than a versioned release,
# so the version strings just track the hardware/stack we're documenting.
version = "0.1"
release = "0.1"

# -- General configuration ---------------------------------------------------

extensions = [
    "sphinx.ext.todo",              # ..todo:: notes for unfinished bringup steps
    "sphinx.ext.duration",          # report slow files at build time
    "sphinx.ext.autosectionlabel",  # :ref: any section by its title
    "sphinx_rtd_size",              # allow RTD theme width scaling
]

# Prefix autosectionlabel targets with the document path so identically named
# sections in different files don't collide.
autosectionlabel_prefix_document = True

# Render ..todo:: directives (handy while the bringup is in progress).
todo_include_todos = True

templates_path = ["_templates"]
exclude_patterns = []

# -- Options for HTML output -------------------------------------------------

html_theme = "sphinx_rtd_theme"
html_static_path = ["_static"]
html_title = "Tenstorrent P150a Bringup"

html_theme_options = {
    "collapse_navigation": False,
    "navigation_depth": 3,
    "titles_only": False,
}

sphinx_rtd_size_width = "85%"
