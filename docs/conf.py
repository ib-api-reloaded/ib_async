extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.napoleon",
    "sphinx_autodoc_typehints",
    "sphinx.ext.extlinks",
    "sphinx.ext.intersphinx",
    "myst_parser",
]

templates_path = ["_templates"]
source_suffix = {
    ".rst": "restructuredtext",
    ".txt": "markdown",
    ".md": "markdown",
}
suppress_warnings = ["myst.xref_missing", "myst.iref_ambiguous"]
master_doc = "index"
project = "ib_async"
html_show_copyright = False
author = "Originally Ewald de Wit; Currently Matt Stancliff"

__version__ = ""
exec(open("../ib_async/version.py").read())
version = ".".join(__version__.split(".")[:2])
release = __version__

language = "en"
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]
pygments_style = "sphinx"
todo_include_todos = False
html_theme = "sphinx_rtd_theme"
html_theme_options = {
    "canonical_url": "https://ib-api-reloaded.github.io/ib_async",
    "logo_only": False,
    "display_version": True,
    "prev_next_buttons_location": "bottom",
    "style_external_links": False,
    # Toc options
    "collapse_navigation": True,
    "sticky_navigation": True,
    "navigation_depth": 4,
    "includehidden": True,
    "titles_only": False,
}

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "eventkit": ("https://eventkit.readthedocs.io/en/latest", None),
}

github_url = "https://github.com/ib-api-reloaded/ib_async"

extlinks = {
    "issue": ("https://github.com/ib-api-reloaded/ib_async/issues/%s", "issue %s"),
    "pull": ("https://github.com/ib-api-reloaded/ib_async/pull/%s", "pull %s"),
}

autoclass_content = "both"
autodoc_member_order = "bysource"
autodoc_default_options = {"members": True, "undoc-members": True}


def onDocstring(app, what, name, obj, options, lines):
    if not lines:
        return
    if lines[0].startswith("Alias for field number"):
        # strip useless namedtuple number fields
        del lines[:]


def setup(app):
    (app.connect("autodoc-process-docstring", onDocstring),)
