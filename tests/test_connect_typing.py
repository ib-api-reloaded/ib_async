"""connect and connectAsync are annotated as returning the IB itself."""

from typing import Self, get_type_hints

import ib_async as ibi


def test_connect_returns_self():
    assert get_type_hints(ibi.IB.connect)["return"] is Self
    assert get_type_hints(ibi.IB.connectAsync)["return"] is Self
