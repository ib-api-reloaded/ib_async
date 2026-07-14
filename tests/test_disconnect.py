from types import SimpleNamespace

import ib_async as ibi


def test_disconnect_emits_disconnected_event_once(monkeypatch):
    ib = ibi.IB()
    disconnect_count = 0

    def on_disconnect():
        nonlocal disconnect_count
        disconnect_count += 1

    def fake_disconnect():
        ib.client.apiEnd.emit()

    monkeypatch.setattr(ib.client, "isConnected", lambda: True)
    monkeypatch.setattr(
        ib.client,
        "connectionStats",
        lambda: SimpleNamespace(
            numBytesSent=0,
            numMsgSent=0,
            numBytesRecv=0,
            numMsgRecv=0,
            duration=0,
        ),
    )
    monkeypatch.setattr(ib.client, "disconnect", fake_disconnect)

    ib.disconnectedEvent += on_disconnect
    ib.disconnect()

    assert disconnect_count == 1
