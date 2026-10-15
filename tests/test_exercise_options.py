"""IB.exerciseOptions passes every field the request has."""

from __future__ import annotations

from unittest.mock import MagicMock

import ib_async as ibi


def test_exercise_options_passes_the_optional_fields():
    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.isConnected.return_value = False
    ib.client.getReqId.return_value = 5
    option = ibi.Option("SPY", "20261218", 600, "C", "SMART")
    ib.exerciseOptions(
        option,
        1,
        2,
        "DU1",
        0,
        manualOrderTime="20261218 15:30:00 US/Eastern",
        customerAccount="CUST1",
        professionalCustomer=True,
    )
    ib.client.exerciseOptions.assert_called_once_with(
        5,
        option,
        1,
        2,
        "DU1",
        0,
        manualOrderTime="20261218 15:30:00 US/Eastern",
        customerAccount="CUST1",
        professionalCustomer=True,
    )
