"""Shared settings for the property-based tests.

``IB_ASYNC_PROPERTY_SCALE`` multiplies every property test's example
count. The default of 1 keeps the suite fast. Use
``IB_ASYNC_PROPERTY_SCALE=20 make test-report`` for a deep run before a
release.
"""

from __future__ import annotations

import os

from hypothesis import Phase, settings

SCALE = int(os.environ.get("IB_ASYNC_PROPERTY_SCALE", "1"))

# The explain phase is off. Its tracing makes long state machine runs much
# slower, and a failing example is readable without it.
PHASES = (Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink)


def examples(count: int, **kwargs: object) -> settings:
    """Settings for ``count`` examples at scale 1, with no deadline."""
    return settings(max_examples=count * SCALE, deadline=None, phases=PHASES, **kwargs)
