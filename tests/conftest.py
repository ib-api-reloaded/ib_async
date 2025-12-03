import asyncio
from unittest.mock import Mock, patch

import pytest

import ib_async as ibi
from ib_async import IB


@pytest.fixture(scope="session")
def event_loop():
    loop = ibi.util.getLoop()
    yield loop
    loop.close()


@pytest.fixture(scope="session")
async def ib():
    ib = ibi.IB()
    await ib.connectAsync()
    yield ib
    ib.disconnect()

@pytest.fixture
def mock_ib():
    """Fixture for a mocked IB instance."""
    ib_instance = IB()
    ib_instance.client.isConnected = Mock(return_value=True)
    ib_instance.client.isReady = Mock(return_value=True)
    ib_instance.client.serverVersion = Mock(return_value=201)
    return ib_instance
