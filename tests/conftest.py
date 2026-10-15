import pytest

import ib_async as ibi


@pytest.fixture(scope="session")
def event_loop():
    loop = ibi.util.getLoop()
    yield loop
    loop.close()
