from __future__ import annotations

# How tests get event loops, and the check that no test drops a failure.
pytest_plugins = ["tests._loops"]
