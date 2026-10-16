"""Access to account statement webservice."""

from __future__ import annotations

import logging
import os
import time
import xml.etree.ElementTree as et
from contextlib import suppress
from pathlib import Path
from typing import Final
from urllib.parse import urlparse
from urllib.request import urlopen

from ib_async import util
from ib_async.objects import DynamicObject

_logger = logging.getLogger("ib_async.flexreport")

FLEXREPORT_URL: Final = (
    "https://ndcdyn.interactivebrokers.com/AccountManagement/"
    "FlexWebService/SendRequest?"
)
"""
https://www.interactivebrokers.com/campus/ibkr-api-page/flex-web-service/#flex-generate-report
"""


class FlexError(Exception):
    pass


_WEB_SCHEMES: Final = frozenset({"http", "https"})


def _webUrl(url: str | None, source: str) -> str:
    """Return ``url`` if it is an http(s) URL with a host; otherwise raise
    FlexError. Keeps ``urlopen`` from reading other schemes such as
    ``file://`` from a configured or server-supplied URL."""
    try:
        parsed = urlparse(url or "")
    except ValueError:
        parsed = None
    if parsed is None or parsed.scheme not in _WEB_SCHEMES or not parsed.netloc:
        raise FlexError(f"{source} is not an http(s) URL: {url!r}")
    return url or ""


def _requiredText(root: et.Element, tag: str) -> str:
    """Text of the response's ``tag`` element, or FlexError if missing."""
    elem = root.find(tag)
    if elem is None or not elem.text:
        raise FlexError(f"Flex response has no {tag}")
    return elem.text


class FlexReport:
    """
    To obtain a token:

    * Login to web portal
    * Go to Settings
    * Click on "Configure Flex Web Service"
    * Generate token
    """

    data: bytes
    root: et.Element

    def __init__(self, token=None, queryId=None, path=None):
        """
        Download a report by giving a valid ``token`` and ``queryId``,
        or load from file by giving a valid ``path``.

        To overwrite default URL, set env variable ``IB_FLEXREPORT_URL``.
        """
        if token and queryId:
            self.download(token, queryId)
        elif path:
            self.load(path)

    def topics(self):
        """Get the set of topics that can be extracted from this report."""
        return {node.tag for node in self.root.iter() if node.attrib}

    def extract(self, topic: str, parseNumbers: bool = True) -> list[DynamicObject]:
        """
        Extract items of given topic and return as list of objects.

        The topic is a string like TradeConfirm, ChangeInDividendAccrual,
        Order, etc.
        """
        cls = type(topic, (DynamicObject,), {})
        results = [cls(**node.attrib) for node in self.root.iter(topic)]
        if parseNumbers:
            for obj in results:
                d = obj.__dict__
                for k, v in d.items():
                    with suppress(ValueError):
                        d[k] = float(v)
                        d[k] = int(v)
        return results

    def df(self, topic: str, parseNumbers=True):
        """Same as extract but return the result as a polars DataFrame
        (requires polars: ``pip install "ib_async[polars]"``)."""
        return util.df(self.extract(topic, parseNumbers))

    def get_url(self):
        """Generate flexreport URL."""
        return _webUrl(
            os.getenv("IB_FLEXREPORT_URL", FLEXREPORT_URL),
            "IB_FLEXREPORT_URL",
        )

    def download(self, token, queryId):
        """Download report for the given ``token`` and ``queryId``."""
        base_url = self.get_url()
        query = f"t={token}&q={queryId}&v=3"
        url = base_url + query

        resp = urlopen(url)
        data = resp.read()

        root = et.fromstring(data)
        elem = root.find("Status")
        if elem is not None and elem.text == "Success":
            code = _requiredText(root, "ReferenceCode")
            baseUrl = _webUrl(_requiredText(root, "Url"), "Flex response Url")
            _logger.info("Statement is being prepared...")
        else:
            elem = root.find("ErrorCode")
            errorCode = elem.text if elem is not None else ""
            elem = root.find("ErrorMessage")
            errorMsg = elem.text if elem is not None else ""
            raise FlexError(f"{errorCode}: {errorMsg}")

        while True:
            time.sleep(1)
            url = f"{baseUrl}?q={code}&t={token}&v=3"
            resp = urlopen(url)
            self.data = resp.read()
            self.root = et.fromstring(self.data)
            if self.root[0].tag == "code":
                msg = self.root[0].text
                if msg and msg.startswith("Statement generation in progress"):
                    _logger.info("still working...")
                    continue
                else:
                    raise FlexError(msg)
            break
        _logger.info("Statement retrieved.")

    def load(self, path):
        """Load report from XML file. Raises FlexError if the file is not
        valid XML."""
        self.data = Path(path).read_bytes()
        try:
            self.root = et.fromstring(self.data)
        except et.ParseError as e:
            raise FlexError(f"{path} is not a Flex report: {e}") from e

    def save(self, path):
        """Save report to XML file."""
        Path(path).write_bytes(self.data)


if __name__ == "__main__":
    util.logToConsole()
    report = FlexReport("945692423458902392892687", "272555")
    print(report.topics())
    trades = report.extract("Trade")
    print(trades)
