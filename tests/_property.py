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

# Example budgets at scale 1. Property tests use PROPERTY_EXAMPLES. State
# machines use MACHINE_EXAMPLES and MACHINE_STEPS. These numbers set the
# running time of the suite.
PROPERTY_EXAMPLES = 200
MACHINE_EXAMPLES = 100
MACHINE_STEPS = 40

# The explain phase is off. Its tracing makes long state machine runs much
# slower. A failing example is readable without it.
PHASES = (Phase.explicit, Phase.reuse, Phase.generate, Phase.target, Phase.shrink)


def examples(count: int = PROPERTY_EXAMPLES, **kwargs: int) -> settings:
    """Return settings for a property test.

    The test runs ``count`` examples at scale 1 and has no deadline.
    """
    return settings(max_examples=count * SCALE, deadline=None, phases=PHASES, **kwargs)


def machine(**kwargs: int) -> settings:
    """Return settings for a state machine.

    At scale 1 the machine does MACHINE_EXAMPLES runs of MACHINE_STEPS
    steps each. It has no deadline.
    """
    return examples(MACHINE_EXAMPLES, stateful_step_count=MACHINE_STEPS, **kwargs)
