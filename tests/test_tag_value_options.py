"""TagValue option parameters: immutable defaults, any sequence accepted."""

from unittest.mock import MagicMock

import ib_async as ibi
from ib_async.client import _FORMAT_HANDLERS_EMPTY, _FORMAT_HANDLERS_KEEP
from ib_async.contract import TagValue

OPTIONS = [TagValue("a", "1"), TagValue("b", "2")]


def test_tuple_and_list_options_encode_identically():
    for handlers in (_FORMAT_HANDLERS_EMPTY, _FORMAT_HANDLERS_KEEP):
        assert handlers[tuple](tuple(OPTIONS)) == handlers[list](OPTIONS) == "a=1;b=2;"


def test_each_ib_gets_its_own_defaults():
    first, second = ibi.IB(), ibi.IB()
    assert first.wrapper.defaults is not second.wrapper.defaults


def test_options_reach_the_client_as_a_fresh_list():
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.getReqId.return_value = 7
    contract = ibi.Stock("SPY", "SMART", "USD")
    contract.conId = 756733

    given = tuple(OPTIONS)
    ib.reqMktData(contract, mktDataOptions=given)
    sent = ib.client.reqMktData.call_args.args[-1]
    assert sent == OPTIONS and isinstance(sent, list)

    ib.cancelMktData(contract)
    ib.reqMktData(contract)  # default: no options
    default = ib.client.reqMktData.call_args.args[-1]
    assert default == [] and isinstance(default, list)
    default.append(TagValue("x", "y"))  # a callee mutating its copy...
    ib.cancelMktData(contract)
    ib.reqMktData(contract)
    assert ib.client.reqMktData.call_args.args[-1] == []  # ...leaks nowhere
