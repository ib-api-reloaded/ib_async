"""FlexReport only fetches over http(s) and rejects malformed responses."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from ib_async.flexreport import FLEXREPORT_URL, FlexError, FlexReport


def _response(xml: str) -> MagicMock:
    resp = MagicMock()
    resp.read.return_value = xml.encode()
    return resp


def test_default_url_is_accepted(monkeypatch):
    monkeypatch.delenv("IB_FLEXREPORT_URL", raising=False)
    assert FlexReport().get_url() == FLEXREPORT_URL


@pytest.mark.parametrize(
    "url",
    ["file://localhost/etc/passwd", "ftp://example.com/x", "not a url", "https://"],
)
def test_configured_url_must_be_http_with_a_host(monkeypatch, url):
    monkeypatch.setenv("IB_FLEXREPORT_URL", url)
    with pytest.raises(FlexError, match="IB_FLEXREPORT_URL"):
        FlexReport().get_url()


def test_server_supplied_statement_url_must_be_http(monkeypatch):
    monkeypatch.delenv("IB_FLEXREPORT_URL", raising=False)
    first = _response(
        "<FlexStatementResponse><Status>Success</Status>"
        "<ReferenceCode>123</ReferenceCode><Url>file:///etc/passwd</Url>"
        "</FlexStatementResponse>"
    )
    with (
        patch("ib_async.flexreport.urlopen", return_value=first) as opened,
        pytest.raises(FlexError, match="Flex response Url"),
    ):
        FlexReport().download("token", "query")
    assert opened.call_count == 1  # the file:// URL is never opened


def test_success_response_without_reference_code_is_an_error(monkeypatch):
    monkeypatch.delenv("IB_FLEXREPORT_URL", raising=False)
    first = _response(
        "<FlexStatementResponse><Status>Success</Status>"
        "<Url>https://example.com/get</Url></FlexStatementResponse>"
    )
    with (
        patch("ib_async.flexreport.urlopen", return_value=first),
        pytest.raises(FlexError, match="ReferenceCode"),
    ):
        FlexReport().download("token", "query")
