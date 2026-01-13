import asyncio
from unittest.mock import Mock

import pytest

from ib_async import IB, Contract, ContractDetails
from ib_async.objects import ConnectionStats
from ib_async.protobuf.Contract_pb2 import Contract as ContractProto
from ib_async.protobuf.ContractDescription_pb2 import (
    ContractDescription as ContractDescriptionProto,
)
from ib_async.protobuf.SecDefOptParameter_pb2 import (
    SecDefOptParameter as SecDefOptParameterProto,
)
from ib_async.protobuf_converters.contract_converters import (
    createContractDescription,
    createOptionChain,
)


@pytest.mark.asyncio
async def test_reqContractDetailsAsync():
    """
    Test the end-to-end flow of reqContractDetailsAsync, including the eventkit stream handling.
    """
    ib = IB()
    ib.client.isConnected = Mock(return_value=True)  # type: ignore
    ib.client.serverVersion = Mock(return_value=201)  # type: ignore
    ib.client.getReqId = Mock(return_value=1)  # type: ignore
    ib.client.reqContractDetails = Mock()  # type: ignore
    ib.client.connectionStats = Mock(return_value=ConnectionStats(0, 0, 0, 0, 0, 0))  # type: ignore

    contract = Contract(symbol="AAPL", secType="STK", exchange="SMART", currency="USD")

    # Call the async method
    event = ib.reqContractDetailsAsync(contract)

    async def emitter():
        await asyncio.sleep(0.01)  # give consumer time to subscribe
        # Simulate the response from TWS
        cd1 = ContractDetails(contract=Contract(symbol="AAPL", conId=1))
        cd2 = ContractDetails(contract=Contract(symbol="AAPL", conId=2))

        ib.wrapper.response_bus.emit(1, cd1)
        ib.wrapper.response_bus.emit(1, cd2)
        ib.wrapper.response_bus.emit(1, None)

    results, _ = await asyncio.gather(event, emitter())
    assert len(results) == 2
    assert results[0].contract.conId == 1  # type: ignore
    assert results[1].contract.conId == 2  # type: ignore

    # Check that the underlying client method was called
    ib.client.reqContractDetails.assert_called_once_with(1, contract)


@pytest.mark.asyncio
async def test_reqMatchingSymbolsAsync():
    """
    Test the end-to-end flow of reqMatchingSymbolsAsync, including eventkit stream handling.
    """
    ib = IB()
    ib.client.isConnected = Mock(return_value=True)  # type: ignore
    ib.client.serverVersion = Mock(return_value=201)  # type: ignore
    ib.client.getReqId = Mock(return_value=1)  # type: ignore
    ib.client.reqMatchingSymbols = Mock()  # type: ignore
    ib.client.connectionStats = Mock(return_value=ConnectionStats(0, 0, 0, 0, 0, 0))  # type: ignore

    pattern = "AAPL"

    # Call the async method
    event = ib.reqMatchingSymbolsAsync(pattern)

    async def emitter():
        await asyncio.sleep(0.01)  # give consumer time to subscribe
        # Simulate the response from TWS
        cd_proto1 = ContractDescriptionProto(
            contract=ContractProto(symbol="AAPL", conId=10)
        )
        cd_proto2 = ContractDescriptionProto(
            contract=ContractProto(symbol="AAPL", conId=20)
        )

        # The Decoder.symbolSamples method emits a list of ContractDescription objects
        contract_descriptions = [
            createContractDescription(cd_proto1),
            createContractDescription(cd_proto2),
        ]

        ib.wrapper.response_bus.emit(1, contract_descriptions)

    results, _ = await asyncio.gather(event, emitter())

    assert len(results) == 2
    assert results[0].contract.conId == 10  # type: ignore
    assert results[1].contract.conId == 20  # type: ignore

    # Check that the underlying client method was called
    ib.client.reqMatchingSymbols.assert_called_once_with(1, pattern)


@pytest.mark.asyncio
async def test_reqSecDefOptParamsAsync():
    """
    Test the end-to-end flow of reqSecDefOptParamsAsync, including eventkit stream handling.
    """
    ib = IB()
    ib.client.isConnected = Mock(return_value=True)  # type: ignore
    ib.client.serverVersion = Mock(return_value=201)  # type: ignore
    ib.client.getReqId = Mock(return_value=1)  # type: ignore
    ib.client.reqSecDefOptParams = Mock()  # type: ignore
    ib.client.connectionStats = Mock(  # type: ignore
        return_value=ConnectionStats(0, 0, 0, 0, 0, 0)
    )

    underlyingSymbol = "SPX"
    futFopExchange = "SMART"
    underlyingSecType = "IND"
    underlyingConId = 123

    # Call the async method
    event = ib.reqSecDefOptParamsAsync(
        underlyingSymbol, futFopExchange, underlyingSecType, underlyingConId
    )

    async def emitter():
        await asyncio.sleep(0.1)  # give consumer time to subscribe
        # Simulate the response from TWS
        sec_def_opt_parameter_proto1 = SecDefOptParameterProto(
            reqId=1,
            exchange="SMART",
            underlyingConId=123,
            tradingClass="SPX",
            multiplier="100",
            expirations=["202501", "202502"],
            strikes=[1000.0, 1100.0],
        )
        sec_def_opt_parameter_proto2 = SecDefOptParameterProto(
            reqId=1,
            exchange="SMART",
            underlyingConId=123,
            tradingClass="SPX",
            multiplier="100",
            expirations=["202503", "202504"],
            strikes=[1200.0, 1300.0],
        )

        option_chain1 = createOptionChain(sec_def_opt_parameter_proto1)
        option_chain2 = createOptionChain(sec_def_opt_parameter_proto2)

        ib.wrapper.response_bus.emit(1, option_chain1)
        ib.wrapper.response_bus.emit(1, option_chain2)
        ib.wrapper.response_bus.emit(1, None)

    results, _ = await asyncio.gather(event, emitter())

    assert len(results) == 2
    assert results[0].exchange == "SMART"
    assert results[0].expirations == ["202501", "202502"]
    assert results[1].expirations == ["202503", "202504"]

    # Check that the underlying client method was called
    ib.client.reqSecDefOptParams.assert_called_once_with(
        1, underlyingSymbol, futFopExchange, underlyingSecType, underlyingConId
    )
