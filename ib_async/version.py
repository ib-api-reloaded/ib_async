"""Version info."""

from importlib.metadata import version

__version__ = version("ib_async")

# historically, ib_insync has provided __version_info__ as a 3-tuple of integers,
# so we shouldn't use non-integer version components like "1.3b1" etc or else
# anybody consuming __version_info__ may receive values outside of ranges they expect.
__version_info__ = tuple([int(x) for x in __version__.split(".")])
