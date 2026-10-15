"""Utilities."""

import asyncio
import contextlib
import datetime as dt
import logging
import math
import os
import signal
import sys
import time
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Iterable,
    Iterator,
    Sequence,
)
from dataclasses import fields, is_dataclass
from decimal import Decimal
from importlib import import_module
from typing import (
    TYPE_CHECKING,
    Any,
    Final,
    TypeAlias,
)
from zoneinfo import ZoneInfo

import nest_asyncio
from eventkit import Event
from eventkit.util import get_event_loop as _threadEventLoop

if TYPE_CHECKING:
    import polars as pl

globalErrorEvent: Event = Event()
"""
Event to emit global exceptions.
"""

EPOCH: Final = dt.datetime(1970, 1, 1, tzinfo=dt.UTC)
UNSET_INTEGER: Final = 2**31 - 1
UNSET_DOUBLE: Final = sys.float_info.max
# IBKR's reference client uses ``UNSET_LONG`` for ``optional int64`` proto
# fields (e.g. ``Order.permId``) and ``UNSET_DECIMAL`` for stringly-encoded
# Decimal wire fields (e.g. ``Order.totalQuantity``). Mirroring the
# constants here lets the proto send-side reject these sentinels with the
# same gate IBKR uses, avoiding the server-side default-fill that turns
# proto3-absent fields back into the magic sentinel value.
UNSET_LONG: Final = 2**63 - 1
UNSET_DECIMAL: Final = Decimal(2**127 - 1)

Time_t: TypeAlias = dt.time | dt.datetime


def df(objs: Iterable[Any], labels: Sequence[str] | None = None) -> "pl.DataFrame":
    """
    Create a polars DataFrame with one row per object. The objects are of
    one kind: dataclasses (such as ``BarData``), namedtuples, dicts,
    attribute records (``FlexReport`` rows) or plain tuples (columns
    ``column_0``, ``column_1``, ...).

    Values keep their types: ``Decimal`` and ``datetime`` (with its time
    zone) become polars ``Decimal`` and ``Datetime`` columns, ``None``
    becomes null, and an ib_async object such as a ``Contract`` is stored
    as itself. With no objects the result has no rows.

    Requires polars: ``pip install "ib_async[polars]"``. polars runs on
    CPython only; on PyPy, :func:`pandasDf` builds a pandas DataFrame.

    Args:
      labels: If supplied, keep only these columns, in this order.
    """
    # polars is an optional dependency, imported only when used.
    try:
        import polars as pl  # noqa: PLC0415
    except ImportError as e:
        raise ImportError(
            'util.df() requires polars: pip install "ib_async[polars]". '
            "polars runs on CPython only; on PyPy use util.pandasDf()."
        ) from e

    columns, data = _table(objs)
    if not data:
        return pl.DataFrame(schema=list(labels or ()))
    frame = pl.DataFrame(
        [
            # strict=False: a column mixing ints and floats (FlexReport
            # numbers) becomes Float64 instead of failing
            pl.Series(name, values, strict=False)
            if _polarsNative(values)
            else pl.Series(name, values, dtype=pl.Object)
            for name, values in zip(
                columns,
                (list(column) for column in zip(*data, strict=True)),
                strict=True,
            )
        ]
    )
    return frame.select(labels) if labels else frame


def pandasDf(objs: Iterable[Any], labels: Sequence[str] | None = None) -> Any:
    """
    Same as :func:`df`, but returns a ``pandas.DataFrame``, for where polars
    is not available (PyPy). Values are stored as they are (``Decimal`` in
    object columns). pandas is not a dependency of ib_async: install it
    yourself.

    Args:
      labels: If supplied, keep only these columns, in this order.
    """
    # pandas is an optional dependency, imported only when used.
    import pandas as pd  # noqa: PLC0415

    columns, data = _table(objs)
    if not data:
        return pd.DataFrame(columns=list(labels or ()))
    frame = pd.DataFrame.from_records(data, columns=columns)
    return frame[list(labels)] if labels else frame


def _table(objs: Iterable[Any]) -> tuple[list[str], list[tuple[Any, ...]]]:
    """Column names and one tuple of values per object, for :func:`df`."""
    rows = list(objs)
    if not rows:
        return [], []
    first = rows[0]
    if is_dataclass(first):
        return [field.name for field in fields(first)], [
            dataclassAsTuple(o) for o in rows
        ]
    if isinstance(first, tuple):
        columns = list(getattr(first, "_fields", ())) or [
            f"column_{i}" for i in range(len(first))
        ]
        return columns, rows
    records = rows if isinstance(first, dict) else [vars(o) for o in rows]
    # every key of every record, in first-seen order; a missing one is null
    columns = list(dict.fromkeys(key for record in records for key in record))
    return columns, [tuple(record.get(c) for c in columns) for record in records]


# Values polars stores in a column of their own type; anything else
# (a Contract, a list of TagValues) is kept as the Python object.
_POLARS_SCALARS: Final = (
    bool,
    int,
    float,
    str,
    bytes,
    Decimal,
    dt.date,
    dt.time,
    dt.timedelta,
)


def _polarsNative(values: list[Any]) -> bool:
    return all(v is None or isinstance(v, _POLARS_SCALARS) for v in values)


def dataclassAsDict(obj) -> dict:
    """
    Return dataclass values as ``dict``.
    This is a non-recursive variant of ``dataclasses.asdict``.
    """
    if not is_dataclass(obj):
        raise TypeError(f"Object {obj} is not a dataclass")

    return {field.name: getattr(obj, field.name) for field in fields(obj)}


def dataclassAsTuple(obj) -> tuple[Any, ...]:
    """
    Return dataclass values as ``tuple``.
    This is a non-recursive variant of ``dataclasses.astuple``.
    """
    if not is_dataclass(obj):
        raise TypeError(f"Object {obj} is not a dataclass")

    return tuple(getattr(obj, field.name) for field in fields(obj))


def dataclassNonDefaults(obj) -> dict[str, Any]:
    """
    For a ``dataclass`` instance get the fields that are different from the
    default values and return as ``dict``.
    """
    if not is_dataclass(obj):
        raise TypeError(f"Object {obj} is not a dataclass")

    values = [getattr(obj, field.name) for field in fields(obj)]

    return {
        field.name: value
        for field, value in zip(fields(obj), values, strict=True)
        if value is not None
        and value != field.default
        and not isNan(value)
        and not (
            (isinstance(value, list) and value == [])
            or (isinstance(value, dict) and value == {})
        )
    }


# ONE display-repr policy for every order-plane object lives below:
# ``DISPLAY_KEEP_ZERO_FIELDS`` + ``DISPLAY_BOILERPLATE_STRINGS`` +
# ``dataclassDisplayFields`` + ``dataclassDisplayValue`` +
# ``dataclassDisplayPairs``, consumed by ``dataclassRepr`` and by the
# hand-written ``__repr__`` of ``Order`` / ``Contract`` / ``Forex``. It is
# a DISPLAY policy only: ``dataclassAsDict`` / ``dataclassAsTuple`` /
# ``dataclassUpdate`` / ``dataclassNonDefaults`` keep their own semantics
# for the callers that round-trip data rather than show it.

# Fields where a ZERO value is information, not absence, so display keeps
# it. Two families:
#   * identity — ``orderId`` 0 is TWS's own manual-order id, and a 0
#     ``permId`` / ``parentId`` / ``clientId`` / ``conId`` / ``reqId`` is a
#     real record key the reader needs in order to match a log line
#     against a broker callback;
#   * quantity — a 0 ``filled`` / ``remaining`` / ``totalQuantity`` /
#     ``shares`` / ``cumQty`` is a definite answer ("nothing filled"), not
#     an unset field.
# Every OTHER numeric field that is zero says nothing a reader can use, so
# it is dropped (a 0 price, a 0 offset, a 0 percentage, a 0 count).
DISPLAY_KEEP_ZERO_FIELDS: Final[frozenset[str]] = frozenset(
    {
        "orderId",
        "permId",
        "parentId",
        "clientId",
        "conId",
        "reqId",
        "filled",
        "remaining",
        "totalQuantity",
        "shares",
        "cumQty",
    }
)

# String values IBKR sends to mean "not applicable". They are not empty, so
# the empty-string rule cannot catch them, and they are not the dataclass
# default, so the default rule cannot either — yet every one of them is
# boilerplate that carries no information about the order.
#   * ``'None'`` — ``Order.adjustedOrderType`` on an ``openOrder`` decode
#     (``decoder.py`` ``o.adjustedOrderType``): IBKR writes the literal
#     four-character string ``None`` when the order has no adjusted-stop
#     companion.
#   * ``'Not an insider or substantial shareholder'`` —
#     ``Order.shareholder`` (``decoder.py`` ``o.shareholder``): the
#     regulatory disclosure IBKR stamps on every non-insider order, i.e.
#     on effectively every order.
#   * ``'?'`` — TWS's unknown-string placeholder on an ``openOrder``
#     snapshot. ``Wrapper.openOrder`` already strips it when building
#     ``Trade.serverOrder``; display drops it wherever else it survives.
DISPLAY_BOILERPLATE_STRINGS: Final[frozenset[str]] = frozenset(
    {
        "None",
        "Not an insider or substantial shareholder",
        "?",
    }
)


def _carriesDisplayInformation(name: str, value: Any, default: Any) -> bool:
    """Whether one field's value tells a reader something.

    The single predicate behind :func:`dataclassDisplayFields`; see the
    constants above for the two named exception sets.
    """

    # Unset, at its declared default, or NaN: nothing was said.
    # (A field declared with ``default_factory`` has ``default`` set to the
    # ``MISSING`` sentinel, which never equals a value, so such fields fall
    # through to the emptiness rules below.)
    if value is None or value == default or isNan(value):
        return False

    # Empty container / empty string: something was said, but it is blank.
    if isinstance(value, list | dict | str) and not value:
        return False

    if isinstance(value, str):
        return value not in DISPLAY_BOILERPLATE_STRINGS

    # Numeric zero is absence for everything but the identity and quantity
    # fields named above. ``bool`` is an ``int`` subclass, and ``False == 0``,
    # so flags are excluded here — a flag that differs from its default is
    # always information.
    if isinstance(value, Decimal | float | int) and not isinstance(value, bool):
        return bool(value) or name in DISPLAY_KEEP_ZERO_FIELDS

    return True


def dataclassDisplayFields(obj) -> dict[str, Any]:
    """
    For a ``dataclass`` instance get the fields worth SHOWING a human, in
    declaration order, and return as ``dict``.

    A field is kept only when it carries information: unset (``None``),
    at its declared default, ``NaN``, an empty list / dict / string, an
    IBKR "not applicable" string sentinel
    (:data:`DISPLAY_BOILERPLATE_STRINGS`) and numeric zero outside the
    identity / quantity fields (:data:`DISPLAY_KEEP_ZERO_FIELDS`) are all
    dropped.

    This is the one policy every order-plane repr uses, so a log line of a
    ``Trade``, an ``Order``, an ``OrderStatus``, an ``Execution``, a
    ``Fill``, a ``CommissionReport`` or a ``Contract`` shows the same
    shape: only what the broker actually said.
    """
    if not is_dataclass(obj):
        raise TypeError(f"Object {obj} is not a dataclass")

    return {
        field.name: value
        for field, value in ((field, getattr(obj, field.name)) for field in fields(obj))
        if _carriesDisplayInformation(field.name, value, field.default)
    }


def dataclassDisplayValue(value: Any) -> str:
    """Render one field value for display.

    ``Decimal`` prints as its plain numeric string (``29403.25``, ``1``)
    rather than ``Decimal('29403.25')`` — the wrapper is noise in a log
    line, and every quantity and price on the order plane is a
    ``Decimal``. Everything else prints through ``repr``, so a nested
    dataclass renders through its OWN culled repr.
    """

    if isinstance(value, Decimal):
        return str(value)

    return repr(value)


def dataclassDisplayPairs(attrs: dict[str, Any]) -> str:
    """Render display fields as the ``name=value, name=value`` repr body."""

    return ", ".join(f"{k}={dataclassDisplayValue(v)}" for k, v in attrs.items())


def dataclassUpdate(obj, *srcObjs, **kwargs) -> object:
    """
    Update fields of the given ``dataclass`` object from zero or more
    ``dataclass`` source objects and/or from keyword arguments.
    """
    if not is_dataclass(obj):
        raise TypeError(f"Object {obj} is not a dataclass")

    for srcObj in srcObjs:
        obj.__dict__.update(dataclassAsDict(srcObj))  # type: ignore[union-attr]

    obj.__dict__.update(**kwargs)  # type: ignore[union-attr]
    return obj


def dataclassRepr(obj) -> str:
    """
    Provide a culled representation of the given ``dataclass`` instance,
    showing only the fields that carry information under
    :func:`dataclassDisplayFields`.
    """
    clsName = obj.__class__.__qualname__
    return f"{clsName}({dataclassDisplayPairs(dataclassDisplayFields(obj))})"


def isnamedtupleinstance(x):
    """From https://stackoverflow.com/a/2166841/6067848"""
    t = type(x)
    b = t.__bases__
    if len(b) != 1 or not isinstance(x, tuple):
        return False

    f = getattr(t, "_fields", None)
    if not isinstance(f, tuple):
        return False

    return all(isinstance(n, str) for n in f)


def tree(obj):
    """
    Convert object to a tree of lists, dicts and simple values.
    The result can be serialized to JSON.
    """
    if isinstance(obj, bool | int | float | str | bytes):
        return obj

    if isinstance(obj, dt.date | dt.time):
        return obj.isoformat()

    if isinstance(obj, dict):
        return {k: tree(v) for k, v in obj.items()}

    if isnamedtupleinstance(obj):
        return {f: tree(getattr(obj, f)) for f in obj._fields}

    if isinstance(obj, list | tuple | set):
        return [tree(i) for i in obj]

    if is_dataclass(obj):
        return {obj.__class__.__qualname__: tree(dataclassNonDefaults(obj))}

    return str(obj)


def _ohlcRows(bars) -> list[tuple[Any, Any, Any, Any]]:
    """
    ``(open, high, low, close)`` per bar, from a polars DataFrame (from
    :func:`df`), a pandas DataFrame (from :func:`pandasDf`) or bar objects
    (``BarData``, ``RealTimeBar``).
    """
    if hasattr(bars, "select"):  # a polars DataFrame
        return bars.select("open", "high", "low", "close").rows()
    if hasattr(bars, "itertuples"):  # a pandas DataFrame
        ohlc = bars[["open", "high", "low", "close"]]
        return list(ohlc.itertuples(index=False, name=None))
    if bars and hasattr(bars[0], "open_"):
        return [(b.open_, b.high, b.low, b.close) for b in bars]
    return [(b.open, b.high, b.low, b.close) for b in bars]


def barplot(bars, title="", upColor="blue", downColor="red"):
    """
    Create candlestick plot for the given bars. The bars can be given as
    a DataFrame (from :func:`df` or :func:`pandasDf`) or as a list of bar
    objects.
    """
    # matplotlib is an optional dependency, imported only when used.
    import matplotlib.pyplot as plt  # noqa: PLC0415
    from matplotlib.lines import Line2D  # noqa: PLC0415
    from matplotlib.patches import Rectangle  # noqa: PLC0415

    ohlcTups = _ohlcRows(bars)

    fig, ax = plt.subplots()
    ax.set_title(title)
    ax.grid(True)
    fig.set_size_inches(10, 6)
    for n, (open_, high, low, close) in enumerate(ohlcTups):
        if close >= open_:
            color = upColor
            bodyHi, bodyLo = close, open_
        else:
            color = downColor
            bodyHi, bodyLo = open_, close
        line = Line2D(xdata=(n, n), ydata=(low, bodyLo), color=color, linewidth=1)
        ax.add_line(line)
        line = Line2D(xdata=(n, n), ydata=(high, bodyHi), color=color, linewidth=1)
        ax.add_line(line)
        rect = Rectangle(
            xy=(n - 0.3, bodyLo),
            width=0.6,
            height=bodyHi - bodyLo,
            edgecolor=color,
            facecolor=color,
            alpha=0.4,
            antialiased=True,
        )
        ax.add_patch(rect)

    ax.autoscale_view()
    return fig


def allowCtrlC():
    """Allow Control-C to end program."""
    signal.signal(signal.SIGINT, signal.SIG_DFL)


# Every ib_async module logs under this namespace (``ib_async.client``,
# ``ib_async.wrapper``, ...). Attaching handlers here — never to the root
# logger — keeps the library from capturing an application's unrelated log
# records while still catching all of ib_async's own output.
_LOGGER_NAME = "ib_async"

# Default line format shared by :func:`logToFile` and :func:`logToConsole`.
_LOG_FORMAT = "%(asctime)s %(name)s %(levelname)s %(message)s"


def _existingHandler(match) -> bool:
    """True if a handler satisfying ``match`` is already attached to the
    ib_async logger or to the root logger.

    Root is included because ib_async records propagate up to it: a handler
    on either logger already covers our output, so adding another would
    double-write. This is what makes repeat :func:`logToFile` /
    :func:`logToConsole` calls idempotent.
    """
    ibLogger = logging.getLogger(_LOGGER_NAME)
    rootLogger = logging.getLogger()
    return any(match(h) for h in (*ibLogger.handlers, *rootLogger.handlers))


def _attachHandler(handler, level, fmt) -> None:
    """Attach ``handler`` to the ib_async logger at ``level``.

    Handlers land on the ``ib_async`` logger rather than the root logger so
    only the library's own records are captured. Propagation is left
    enabled, so an application that configures the root logger still
    receives ib_async records too.
    """
    logger = logging.getLogger(_LOGGER_NAME)
    logger.setLevel(level)
    handler.setFormatter(logging.Formatter(fmt or _LOG_FORMAT))
    logger.addHandler(handler)


def logToFile(path, level=logging.INFO, fmt=None):
    """Log ib_async records to ``path``.

    The file handler is attached to the ``ib_async`` logger, not the root
    logger, so only the library's own records are written — an
    application's other logs are not teed into the file. Idempotent: a
    repeat call for the same path does not stack a second handler.

    Args:
        path: Destination log file.
        level: Level for the ``ib_async`` logger (default ``INFO``).
        fmt: Optional ``logging`` format string; defaults to the shared
            ib_async format.
    """
    # Normalized exactly as logging.FileHandler normalizes baseFilename
    # (Path.resolve() would also follow symlinks and never match).
    target = os.path.abspath(path)  # noqa: PTH100
    if _existingHandler(
        lambda h: type(h) is logging.FileHandler and h.baseFilename == target
    ):
        logging.getLogger(_LOGGER_NAME).setLevel(level)
        return
    _attachHandler(logging.FileHandler(path), level, fmt)


def logToConsole(level=logging.INFO, fmt=None):
    """Log ib_async records to the console (stderr).

    The stream handler is attached to the ``ib_async`` logger, not the root
    logger, so only the library's own records are printed. Idempotent, and
    a no-op (handler-wise) when a stderr handler already exists on the
    ``ib_async`` logger or on root — records propagate up, so a second one
    would double-print.

    Args:
        level: Level for the ``ib_async`` logger (default ``INFO``).
        fmt: Optional ``logging`` format string; defaults to the shared
            ib_async format.
    """
    if _existingHandler(
        lambda h: type(h) is logging.StreamHandler and h.stream is sys.stderr
    ):
        logging.getLogger(_LOGGER_NAME).setLevel(level)
        return
    _attachHandler(logging.StreamHandler(), level, fmt)


def isNan(x: object) -> bool:
    """Not-a-number test for any value: True for float and Decimal NaN,
    False for everything else (never raises, unlike ``math.isnan``)."""
    return x != x  # noqa: PLR0124 - NaN is the only value unequal to itself


def formatSI(n: float) -> str:
    """Format the integer or float n to 3 significant digits + SI prefix."""
    s = ""
    if n < 0:
        n = -n
        s += "-"

    if isinstance(n, int) and n < 1000:
        s = str(n) + " "
    elif n < 1e-22:
        s = "0.00 "
    else:
        if n >= 9.99e26:
            raise ValueError(f"{n} is too large for an SI prefix")
        log = math.floor(math.log10(n))
        i, j = divmod(log, 3)
        for _try in range(2):
            templ = f"%.{2 - j}f"
            val = templ % (n * 10 ** (-3 * i))
            if val != "1000":
                break
            i += 1
            j = 0
        s += val + " "
        if i != 0:
            s += "yzafpnum kMGTPEZY"[i + 8]

    return s


class timeit:
    """Context manager for timing."""

    def __init__(self, title="Run"):
        self.title = title

    def __enter__(self):
        self.t0 = time.time()

    def __exit__(self, *_args):
        print(self.title + " took " + formatSI(time.time() - self.t0) + "s")


def run(*awaitables: Awaitable, timeout: float | None = None):
    """
    By default run the event loop forever.

    When awaitables (like Tasks, Futures or coroutines) are given then
    run the event loop until each has completed and return their results.

    An optional timeout (in seconds) can be given that will raise
    asyncio.TimeoutError if the awaitables are not ready within the
    timeout period.
    """
    loop = getLoop()
    if not awaitables:
        if loop.is_running():
            return

        loop.run_forever()
        result = None
        all_tasks = asyncio.all_tasks(loop)

        if all_tasks:
            # cancel pending tasks
            f = asyncio.gather(*all_tasks)
            f.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                loop.run_until_complete(f)
    else:
        future = awaitables[0] if len(awaitables) == 1 else asyncio.gather(*awaitables)

        if timeout:
            future = asyncio.wait_for(future, timeout)
        # Pass loop explicitly to avoid deprecation warnings in Python 3.10+
        task = asyncio.ensure_future(future, loop=loop)

        # The global error raised while *this* run was active, if any; the
        # event's last value may be from an earlier, unrelated run.
        raised: list[BaseException] = []

        def onError(error):
            raised.append(error)
            task.cancel()

        globalErrorEvent.connect(onError)
        try:
            result = loop.run_until_complete(task)
        except asyncio.CancelledError as e:
            if not raised:
                raise
            raise raised[0] from e
        finally:
            globalErrorEvent.disconnect(onError)

    return result


def _fillDate(time: Time_t) -> dt.datetime:
    # use today if date is absent
    if isinstance(time, dt.time):
        t = dt.datetime.combine(dt.date.today(), time)
    else:
        t = time
    return t


def schedule(time: Time_t, callback: Callable, *args):
    """
    Schedule the callback to be run at the given time with
    the given arguments.
    This will return the Event Handle.

    Args:
        time: Time to run callback. If given as :py:class:`datetime.time`
            then use today as date.
        callback: Callable scheduled to run.
        args: Arguments for to call callback with.
    """
    t = _fillDate(time)
    now = dt.datetime.now(t.tzinfo)
    delay = (t - now).total_seconds()
    loop = getLoop()
    return loop.call_later(delay, callback, *args)


def sleep(secs: float = 0.02) -> bool:
    """
    Wait for the given amount of seconds while everything still keeps
    processing in the background. Never use time.sleep().

    Args:
        secs (float): Time in seconds to wait.
    """
    run(asyncio.sleep(secs))
    return True


def timeRange(start: Time_t, end: Time_t, step: float) -> Iterator[dt.datetime]:
    """
    Iterator that waits periodically until certain time points are
    reached while yielding those time points.

    Args:
        start: Start time, can be specified as datetime.datetime,
            or as datetime.time in which case today is used as the date
        end: End time, can be specified as datetime.datetime,
            or as datetime.time in which case today is used as the date
        step (float): The number of seconds of each period
    """
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")
    delta = dt.timedelta(seconds=step)
    t = _fillDate(start)
    tz = dt.UTC if t.tzinfo else None
    now = dt.datetime.now(tz)
    while t < now:
        t += delta

    while t <= _fillDate(end):
        waitUntil(t)
        yield t
        t += delta


def waitUntil(t: Time_t) -> bool:
    """
    Wait until the given time t is reached.

    Args:
        t: The time t can be specified as datetime.datetime,
            or as datetime.time in which case today is used as the date.
    """
    now = dt.datetime.now(t.tzinfo)
    secs = (_fillDate(t) - now).total_seconds()
    run(asyncio.sleep(secs))
    return True


async def timeRangeAsync(
    start: Time_t, end: Time_t, step: float
) -> AsyncIterator[dt.datetime]:
    """Async version of :meth:`timeRange`."""
    if step <= 0:
        raise ValueError(f"step must be positive, got {step}")

    delta = dt.timedelta(seconds=step)
    t = _fillDate(start)
    tz = dt.UTC if t.tzinfo else None
    now = dt.datetime.now(tz)
    while t < now:
        t += delta

    while t <= _fillDate(end):
        await waitUntilAsync(t)
        yield t
        t += delta


async def waitUntilAsync(t: Time_t) -> bool:
    """Async version of :meth:`waitUntil`."""
    now = dt.datetime.now(t.tzinfo)
    secs = (_fillDate(t) - now).total_seconds()
    await asyncio.sleep(secs)

    return True


def patchAsyncio():
    """Patch asyncio to allow nested event loops."""
    nest_asyncio.apply()


def getLoop() -> asyncio.AbstractEventLoop:
    """
    Get the event loop for the calling thread.

    In order of preference:

    1. the running loop;
    2. the loop set for this thread with ``asyncio.set_event_loop``, so an
       application's own loop is always the one used;
    3. otherwise a new loop, which is set for this thread.

    A closed loop is replaced the same way as a missing one, and the loop
    is never cached across calls. No deprecated asyncio API is used and no
    DeprecationWarning is emitted on any supported Python version.

    This is eventkit's rule for the loop of a thread, shared so ib_async
    and eventkit always agree on it. In a coroutine,
    ``asyncio.get_running_loop()`` returns the same loop more cheaply.
    """
    return _threadEventLoop()


def startLoop():
    """Use nested asyncio event loop for Jupyter notebooks."""
    patchAsyncio()


def useQt(qtLib: str = "PyQt5", period: float = 0.01):
    """
    Run combined Qt5/asyncio event loop.

    Args:
        qtLib: Name of Qt library to use:

          * PyQt5
          * PyQt6
          * PySide2
          * PySide6
        period: Period in seconds to poll Qt.
    """

    def qt_step():
        loop.call_later(period, qt_step)
        if not stack:
            qloop = qc.QEventLoop()
            timer = qc.QTimer()
            timer.timeout.connect(qloop.quit)
            stack.append((qloop, timer))
        qloop, timer = stack.pop()
        timer.start(0)
        qloop.exec() if qtLib == "PyQt6" else qloop.exec_()
        timer.stop()
        stack.append((qloop, timer))
        qApp.processEvents()  # type: ignore[name-defined]

    if qtLib not in {"PyQt5", "PyQt6", "PySide2", "PySide6"}:
        raise RuntimeError(f"Unknown Qt library: {qtLib}")
    qc = import_module(qtLib + ".QtCore")
    qw = import_module(qtLib + ".QtWidgets")
    global qApp
    qApp = (  # type: ignore[name-defined]
        qw.QApplication.instance() or qw.QApplication(sys.argv)
    )
    loop = getLoop()
    stack: list = []
    qt_step()


def formatIBDatetime(t: dt.date | dt.datetime | str | None) -> str:
    """Format date or datetime to string that IB uses."""
    if not t:
        s = ""
    elif isinstance(t, dt.datetime):
        # convert to UTC timezone
        t = t.astimezone(tz=dt.UTC)
        s = t.strftime("%Y%m%d %H:%M:%S UTC")
    elif isinstance(t, dt.date):
        t = dt.datetime(t.year, t.month, t.day, 23, 59, 59).astimezone(tz=dt.UTC)
        s = t.strftime("%Y%m%d %H:%M:%S UTC")
    else:
        s = t

    return s


# ``formatDate=3`` values carry no year, so the month/day/time half is
# parsed against a leap year and re-stamped once the year is known; 2000
# keeps 02/29 parseable.
_SHORT_DATETIME_YEAR: Final = 2000


def isIBShortDatetime(s: str) -> bool:
    """Return True when ``s`` is an IB ``formatDate=3`` timestamp.

    ``reqHistoricalData(formatDate=3)`` ships bar timestamps as
    ``MMdd HH:MM:SS <tz>`` -- the year is simply absent from the wire, so
    such a value cannot become a ``datetime`` on its own. Callers detect
    it with this predicate and resolve a whole ascending run at once with
    :func:`parseIBShortDatetimes`, or hand the year to
    :func:`parseIBDatetime`.
    """
    return (
        len(s) != 8
        and not s.isdigit()
        and s.count(" ") >= 2
        and "  " not in s
        and len(s.split(" ", 1)[0]) == 4
    )


def _splitIBShortDatetime(s: str) -> tuple[dt.datetime, ZoneInfo]:
    """Split ``MMdd HH:MM:SS <tz>`` into a year-less stamp and its zone."""
    s0, s1, s2 = s.split(" ", 2)
    naive = dt.datetime.strptime(f"{_SHORT_DATETIME_YEAR}{s0}{s1}", "%Y%m%d%H:%M:%S")
    return naive, ZoneInfo(s2)


def _stampIBYear(naive: dt.datetime, tz: ZoneInfo, year: int) -> dt.datetime | None:
    """Move ``naive`` to ``year`` in ``tz``, or None when that date does
    not exist (02/29 outside a leap year)."""
    try:
        return naive.replace(year=year, tzinfo=tz)
    except ValueError:
        return None


def _nearestIBYear(
    part: tuple[dt.datetime, ZoneInfo], anchor: dt.datetime
) -> dt.datetime:
    """Stamp ``part`` with the year that lands it closest to ``anchor``."""
    naive, tz = part
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=tz)

    best: dt.datetime | None = None
    for year in range(anchor.year - 2, anchor.year + 3):
        candidate = _stampIBYear(naive, tz, year)
        if candidate is None:
            continue
        if best is None or abs(candidate - anchor) < abs(best - anchor):
            best = candidate

    if best is None:
        raise ValueError(f"Cannot place IB short datetime near {anchor!r}")

    return best


def _stepIBYear(
    part: tuple[dt.datetime, ZoneInfo], neighbour: dt.datetime, ascending: bool
) -> dt.datetime:
    """Stamp ``part`` with the nearest year that keeps the run monotonic:
    at or after ``neighbour`` when ascending, at or before it otherwise."""
    naive, tz = part
    step = 1 if ascending else -1
    for offset in range(8):
        candidate = _stampIBYear(naive, tz, neighbour.year + step * offset)
        if candidate is None:
            continue
        if (candidate >= neighbour) if ascending else (candidate <= neighbour):
            return candidate

    raise ValueError(f"Cannot order IB short datetime against {neighbour!r}")


def parseIBShortDatetimes(
    values: list[str],
    *,
    start: dt.datetime | None = None,
    end: dt.datetime | None = None,
) -> list[dt.datetime]:
    """Resolve an ascending run of IB ``formatDate=3`` timestamps.

    A lone ``formatDate=3`` value is ambiguous because the year never
    reaches the wire, but a *run* is not: IB emits historical bars in
    ascending order, so anchoring one edge fixes every element. ``start``
    anchors the first value and the run is walked forwards, rolling the
    year over whenever ``MMdd`` wraps past new year; otherwise ``end``
    (defaulting to now) anchors the last value and the run is walked
    backwards.

    An anchor only has to sit within six months of the edge it anchors,
    which the response bounds IB reports for a historical request always
    do.
    """
    parts = [_splitIBShortDatetime(v) for v in values]
    if not parts:
        return []

    if start is not None:
        out = [_nearestIBYear(parts[0], start)]
        for part in parts[1:]:
            out.append(_stepIBYear(part, out[-1], ascending=True))
        return out

    if end is None:
        end = dt.datetime.now(parts[-1][1])

    out = [_nearestIBYear(parts[-1], end)]
    for part in reversed(parts[:-1]):
        out.append(_stepIBYear(part, out[-1], ascending=False))
    out.reverse()
    return out


def parseIBDatetime(s: str, *, year: int | None = None) -> dt.date | dt.datetime:
    """Parse string in IB date or datetime format to datetime.

    ``year`` supplies the year for an IB ``formatDate=3`` value
    (``MMdd HH:MM:SS <tz>``), which carries none of its own; such a value
    raises without it. :func:`parseIBShortDatetimes` recovers the year
    from a whole response instead.
    """
    if len(s) == 8:
        # YYYYmmdd
        y = int(s[0:4])
        m = int(s[4:6])
        d = int(s[6:8])
        t = dt.date(y, m, d)
    elif s.isdigit():
        t = dt.datetime.fromtimestamp(int(s), dt.UTC)
    elif s.count(" ") >= 2 and "  " not in s:
        # 20221125 10:00:00 Europe/Amsterdam
        s0, s1, s2 = s.split(" ", 2)
        if len(s0) == 4:
            # 1125 10:00:00 Europe/Amsterdam -- formatDate=3, no year.
            if year is None:
                raise ValueError(
                    f"IB formatDate=3 timestamp {s!r} carries no year; pass"
                    " year=... or resolve the response with"
                    " parseIBShortDatetimes()"
                )
            naive, tz = _splitIBShortDatetime(s)
            stamped = _stampIBYear(naive, tz, year)
            if stamped is None:
                raise ValueError(f"IB datetime {s!r} does not exist in {year}")
            t = stamped
        else:
            t = dt.datetime.strptime(s0 + s1, "%Y%m%d%H:%M:%S")
            t = t.replace(tzinfo=ZoneInfo(s2))
    else:
        # YYYYmmdd  HH:MM:SS
        # or
        # YYYY-mm-dd HH:MM:SS.0
        ss = s.replace(" ", "").replace("-", "")[:16]
        t = dt.datetime.strptime(ss, "%Y%m%d%H:%M:%S")

    return t
