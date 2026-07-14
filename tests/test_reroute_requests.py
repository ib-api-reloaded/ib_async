import ib_async as ibi


def test_decoder_emits_reroute_mkt_data_req_event():
    ib = ibi.IB()
    reroutes = []

    def on_reroute(reqId: int, conId: int, exchange: str):
        reroutes.append((reqId, conId, exchange))

    ib.rerouteMktDataReqEvent += on_reroute

    ib.client.decoder.interpret(["91", "12", "345", "SMART"])

    assert reroutes == [(12, 345, "SMART")]


def test_decoder_emits_reroute_mkt_depth_req_event():
    ib = ibi.IB()
    reroutes = []

    def on_reroute(reqId: int, conId: int, exchange: str):
        reroutes.append((reqId, conId, exchange))

    ib.rerouteMktDepthReqEvent += on_reroute

    ib.client.decoder.interpret(["92", "22", "789", "ISLAND"])

    assert reroutes == [(22, 789, "ISLAND")]
