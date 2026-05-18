``ib_async`` Changelog
======================

3.0
---

Version 3.0.0 (Unreleased)
^^^^^^^^^^^^^^^^^^^^^^^^^^

The v3.0 release lands the protobuf wire-protocol migration, shifts
financial numerics to ``Decimal | None`` end-to-end, and closes the
IBKR-parity gap against the reference client at TWS / Gateway server
version 225. The full upgrade guide with examples lives at
``docs/migration/v3.md``.

**The most likely-to-hit changes**

* Financial numeric fields are now ``Decimal | None`` (was ``float``).
* ``commission`` is now ``commissionAndFees`` on ``CommissionReport``
  and ``OrderState``. The legacy name keeps working with a
  ``DeprecationWarning`` until v4.0.
* ``HistogramData.count`` is renamed to ``HistogramData.size`` and
  retyped to ``Decimal | None``.
* ``PnLSingle.position`` is now ``Decimal | None`` (was ``int``).
* Hot-path records (``AccountValue``, ``Position``, ``PortfolioItem``,
  ``Fill``, ``TickData``, ``HistoricalTick*``, ``TickByTick*``,
  ``MktDepthData``, ``DOMLevel``, ``PriceIncrement``,
  ``OrderAllocation``, ``OrderCancel``, ``IneligibilityReason``)
  moved from ``NamedTuple`` to slotted-frozen ``dataclass``. Indexing
  (``av[1]``) and tuple iteration no longer work. Use attribute
  access (``av.tag``). ``_asdict()`` / ``_replace()`` are replaced by
  ``dataclasses.asdict()`` / ``dataclasses.replace()``.

**Added**

* **Protobuf wire protocol** alongside the legacy binary path. The
  client emits protobuf for messages whose gate the negotiated TWS /
  IB Gateway server version supports; falls back to binary below the
  gate. Per-message gating means a server at version 207 uses
  protobuf for accounts but binary for historical data, etc. The
  binary path remains fully supported for older server versions.
* **14 new public methods on** ``IB`` **for parity with IBKR's
  reference** ``EClient``:

  * ``IB.reqCurrentTimeInMillisAsync`` (server >= 213)
  * ``IB.setServerLogLevel``
  * ``IB.reqSoftDollarTiersAsync``
  * ``IB.reqFamilyCodesAsync``
  * ``IB.cancelHeadTimeStamp`` (now settles awaiter with ``CancelledError``)
  * ``IB.cancelHistogramData`` (now settles awaiter with ``CancelledError``)
  * ``IB.queryDisplayGroups``, ``IB.subscribeToGroupEvents``,
    ``IB.updateDisplayGroup``, ``IB.unsubscribeFromGroupEvents``
  * ``IB.cancelContractData`` (protobuf-only, server >= 215; settles awaiter)
  * ``IB.cancelHistoricalTicks`` (protobuf-only, server >= 215; settles awaiter)
  * ``IB.reqConfigAsync``, ``IB.updateConfigAsync`` (protobuf-only, server >= 219)

* **Attached-order linkage on** ``Order``: new ``slOrderId`` /
  ``slOrderType`` / ``ptOrderId`` / ``ptOrderType`` fields preserve
  the stop-loss and profit-target ids of a bracket or OCO group
  across the wire. Previously the linkage was silently dropped on
  receive.
* **Specialized order behaviour fields on** ``Order``:
  ``allowPreOpen``, ``deactivate``, ``postOnly``, ``ignoreOpenAuction``,
  ``seekPriceImprovement``, ``whatIfType``, ``hedgeMaxSize``. Both
  receive (``createOrder``) and send (``createOrderProto`` / binary
  ``placeOrder``) handle them.
* **``OrderCancel`` envelope** for ``IB.cancelOrder`` and
  ``IB.reqGlobalCancel`` carrying CME-compliance fields
  (``manualOrderCancelTime``, ``extOperator``,
  ``manualOrderIndicator``). Optional — callers without an envelope
  see unchanged v2.x behaviour.
* **``ExecutionFilter`` parametrized day-window**: new ``lastNDays``
  + ``specificDates`` fields for narrowing ``reqExecutions`` queries
  without walking the full session.
* **``ContractDetails.lastTradeDate``** split out from
  ``lastTradeDateOrContractMonth`` at server gate 182.
* **Bond ``ContractDetails``** trading-hours block at server gate 188.
* **``TickAttrib``** (``canAutoExecute``, ``pastLimit``, ``preOpen``)
  surfaced on ``priceSizeTick``.
* **``Ticker.tickAttrib``** + **``Ticker.news``** (``deque(maxlen=5)``):
  per-quote flags and a bounded per-contract news ring are now
  attached directly to the matching ``Ticker``. O(1) hot-path cost,
  additive. The global ``IB.tickNewsEvent`` / ``wrapper.newsTicks``
  still fan out.
* **``Client.setOptionalCapabilities``** for runtime feature
  negotiation.
* **5 compliance / origination fields on** ``Order`` **now written
  on send too** (``customerAccount``, ``professionalCustomer``,
  ``bondAccruedInterest``, ``includeOvernight``, ``submitter``).
  Previously they were populated on receive but silently dropped on
  send — a fetched-then-replaced order lost its originating-session
  tagging.

**Changed (breaking)**

* **``Decimal | None`` end-to-end** for financial numerics on
  ``Order``, ``OrderStatus``, ``OrderState``, ``Execution``,
  ``CommissionReport``, ``ContractDetails``, ``Position``,
  ``PortfolioItem``, ``BarData``, ``RealTimeBar``, ``HistogramData``,
  ``PnLSingle``. ``None`` is the unset sentinel —
  ``Decimal('NaN')`` is never used (it is silently truthy in Python
  and corrupted downstream comparisons).
* **``commission`` → ``commissionAndFees``** on ``CommissionReport``
  and ``OrderState``. Matches IBKR's reference. Legacy ``commission``
  attribute and constructor keyword keep working with
  ``DeprecationWarning`` until v4.0.
* **``HistogramData.count: int`` → ``HistogramData.size: Decimal | None``**
  — the field was the wrong name and the wrong type. ``count`` was
  always a Decimal-encoded quantity on the wire; the legacy name
  shipped truncated to ``int``.
* **``PnLSingle.position: int`` → ``Decimal | None``** so fractional
  positions don't truncate.
* **``AccountValue.decimalValue`` stricter**: returns ``None`` for
  non-currency tags (``Leverage``, ``DayTradesRemaining``,
  ``AccountType``, etc.) and for IBKR UNSET sentinel strings / NaN
  / Infinity. Previously surfaced ``1.7976931348623157e+308`` as a
  legitimate NetLiquidation.
* **``NamedTuple`` → ``@dataclass(slots=True, frozen=True)``** for
  ``AccountValue``, ``Position``, ``PortfolioItem``, ``Fill``,
  ``TickData``, ``HistoricalTick*``, ``TickByTick*``,
  ``MktDepthData``, ``DOMLevel``, ``PriceIncrement``,
  ``OrderAllocation``, ``OrderCancel``, ``IneligibilityReason``.
  Equality, hashability, and pickle are preserved. Indexing and
  tuple iteration no longer work; use attribute access.
  ``_asdict()`` / ``_replace()`` replaced by
  ``dataclasses.asdict()`` / ``dataclasses.replace()``.
* **``tickByTick*.time``** now uses the wire-supplied exchange epoch
  instead of the local-clock ``lastTime``.
* **``Wrapper.sendMsg``** signature changed from ``str`` to
  ``bytes | None``. Subclassers must update.
* **``Client.MaxClientVersion = 225``** (was 178). The 178 cap
  silently disabled every gate 201+ feature on v2.x against modern
  TWS / Gateway — no v2.x deployment could reach protobuf.
* **Cancel-async methods raise ``CancelledError``** on the awaiter
  instead of hanging forever. Affects ``cancelHeadTimeStamp``,
  ``cancelHistogramData``, ``cancelContractData``,
  ``cancelHistoricalTicks``.
* **``OrderState.transform()``** now applies the transformer to all
  9 ``*OutsideRTH`` margin variants in addition to the regular 9.
  ``.numeric()`` / ``.formatted()`` no longer leave OutsideRTH
  fields as raw wire strings.
* **``RealTimeBar.endTime`` removed.** The field was never populated
  from the wire (IBKR's ``RealTimeBarTick`` proto has only
  ``time`` / OHLC / volume / WAP / count, and their reference Python
  has no such field) and the wrapper hardcoded ``-1``. If you need
  an end-of-window timestamp, compute it from ``bar.time``
  (5-second windows).
* **Universal-unset-is-None sweep**: every magic-value default in
  the domain dataclasses (``UNSET_INTEGER`` / ``UNSET_DOUBLE`` /
  ``UNSET_LONG`` / ``UNSET_DECIMAL`` / ``nan``) replaced with
  ``T | None = None``. Affected: ``Order`` (~25 fields),
  ``OrderStateNumeric`` (18 fields), ``Ticker`` (80 fields), ``Bar``
  (4 fields), ``PnL`` / ``PnLSingle`` (7 fields),
  ``ScannerSubscription``, ``ExecutionFilter``,
  ``ContractDetails.aggGroup``. Readers updated from
  ``isNan(x)`` / ``x == UNSET_*`` to ``x is None``.

**Fixed (silent-data-loss and wire-protocol bugs)**

These were broken on v2.x against modern TWS / Gateway versions and
are fixed in v3.0:

* **``MaxClientVersion = 178`` cap** made every gate 201+ feature
  unreachable in production.
* **``errorMsg`` decoder** mis-shifted on server >= 194 (ERROR_TIME
  gate); server errors landed on the wrong reqId.
* **``cancelOrder`` wire frame** corrupted on server >= 192 (CME
  tagging fields).
* **``placeOrder`` binary path** missing gates 179-225 (rejected by
  183+ server).
* **``historicalData``** ``HISTORICAL_DATA_END`` msgId broken on
  server >= 196.
* **``_protoError`` handler** missing entirely — server errors
  silently dropped on the protobuf path.
* **``orderStatus``** legacy version prefix and ``mktCapPrice``
  trailing field gated on the correct server version (131).
* **``contractDetails``** aggGroup / underSymbol / underSecType /
  marketRuleIds / realExpirationDate / stockType / fund-data /
  ineligibility-reasons reads gated on their respective constants
  (121-186).
* **Binary ``openOrder`` duration field gate** corrected from
  ``>= 159`` literal to ``MIN_SERVER_VER_DURATION = 158``.
* **``TagValue`` option lists** now thread through the proto send
  path for 7 request types — were silently dropped on protobuf.
* **``replaceFA`` trailing ``reqId`` field** gated on
  ``MIN_SERVER_VER_REPLACE_FA_END = 157``.
* **``requestFA`` / ``replaceFA``** reject ``faData=2`` (Profiles)
  at gate 177.
* **``placeOrder`` volatility-clear** workaround hoisted above the
  protobuf branch so it applies on both wire paths.
* **``tickOptionComputation``** correctly maps the ``-2`` sentinel
  to ``None`` for vega and theta (was a tautology returning ``-2.0``).
* **``PnLSingle.position``** no longer truncates fractional positions
  to ``int``.
* **``HistogramData.size``** is now a ``Decimal`` (was buggy
  ``count: int``).
* **``Execution.optExerciseOrLapseType``** default corrected to
  ``-1`` (IBKR's ``NoneItem`` sentinel; ``0`` means "Exercise").
* **``commissionReport``** arriving before ``execDetails`` is now
  parked in a bounded ``OrderedDict`` (1024 entries, FIFO eviction)
  instead of being silently dropped or leaking unbounded memory.
* **``IB.disconnect``** fires ``wrapper.connectionClosed`` exactly
  once (was double-firing, causing ``InvalidStateError`` on
  in-flight futures).
* **``IB._backgroundTasks``** strongly references reconnect-resync
  tasks so asyncio's weak loop reference doesn't GC them mid-run.
* **``Watchdog.probeContract``** is now per-instance (was a
  class-level shared mutable default — multiple watchdog instances
  silently shared one contract).
* **``IBC.terminateAsync``** bounded by SIGTERM 20s + SIGKILL 10s
  (was unbounded — hung TWS during daily reset blocked the
  reconnect loop forever).
* **``IBC.monitorAsync``** catches stdout read exceptions cleanly
  and decodes with ``errors="replace"``.
* **``Wrapper.headTimestamp``** widened from ``except ValueError``
  to ``except Exception`` so ``ZoneInfoNotFoundError`` doesn't
  leak past and leave the awaiter hanging.
* **``Order._toDecimal``** filters NaN / Infinity from both float
  and Decimal inputs so a stray ``Decimal('NaN')`` from user code
  lands as ``None``.
* **Binary path msgId framing** at server >= 201 now uses a 4-byte
  big-endian raw integer prefix (matching IBKR's reference
  ``comm.make_msg(..., useRawIntMsgId=True)``). The legacy NUL-text
  framing was silently dropped by server 201+.
* **Wire-boundary None-coalesce** at the protobuf converter entry
  mirrors the binary path's ``_FORMAT_HANDLERS[type(None)] =
  lambda _: ""`` behaviour: callers that stamp ``None`` onto plain-
  scalar dataclass fields (e.g. an order-preview path setting
  ``parentId = None``) now produce wire frames with the field at its
  dataclass default rather than absent, which TWS rejected as
  ``Error 135: Can't find order with id = 2147483647``. Applied
  uniformly at every user-mutable converter boundary.

**Internal**

* **Pinned TWS API version, single source of truth.** The version
  + SHA256 of IBKR's TWS API archive live in ``pyproject.toml``
  under ``[tool.ib_async.twsapi]``. ``scripts/generate_protos.py``
  fetches that exact archive from ``interactivebrokers.github.io``,
  verifies the SHA, and caches the result under
  ``~/.cache/ib_async/twsapi-{version}/``. The same archive ships
  both the ``.proto`` schemas AND the reference ``client_utils.py``
  that the parity audit walks against — version-locked together,
  so generated bindings and audit ground truth can never drift. CI
  reads the same pin and keys its cache step on it. Contributors no
  longer need a TWS install locally; ``make protos`` is
  self-contained.
* **Release engineering.** ``ib_async/_pb/`` (generated protobuf
  bindings) is gitignored. The release build regenerates the
  modules and bundles them into the sdist / wheel via a
  ``[tool.poetry.include]`` glob in ``pyproject.toml``. End users
  of ``pip install ib_async`` get the bindings without needing
  ``protoc`` or ``grpcio-tools``; only the runtime ``protobuf``
  dependency is declared. ``scripts/release.py`` orchestrates the
  full pipeline (fetch + extract → generate → ruff + mypy → parity
  audit → owned tests → ``uv build`` → clean-venv smoke install).
  Publishing is gated behind ``--publish``.
* **Makefile** targets: ``make protos`` / ``make audit`` /
  ``make build`` / ``make release`` / ``make publish`` /
  ``make test`` / ``make lint`` / ``make format`` / ``make clean``.
* **Protobuf send-path parity audit script** at
  ``scripts/audit_proto_parity.py`` AST-walks IBKR's reference
  ``client_utils.py`` and our ``_proto/*.py``, classifies every
  per-field gate, and reports any divergence. CI runs it as a
  regression test; any future converter edit that drifts from
  IBKR's ``isValidIntValue`` / ``isValidFloatValue`` /
  ``isValidLongValue`` / ``isValidDecimalValue`` semantics breaks
  the test immediately.
* Hot-path tick / depth records use ``__slots__``.
* ``processProtoBuf`` caches resolved bound methods on the dispatch
  path.
* ``safe_decimal(str | Decimal | None) → Decimal | None`` is the
  single source of truth for IBKR UNSET-sentinel rejection.
* Comprehensive owned-test suite covering the protobuf seam,
  Decimal coercion, request / subscription lifecycles, dataclass
  invariants, cross-version decoder gating, and wire-frame parity
  against IBKR's reference client. Each behavioural fix listed
  above is pinned by at least one regression test.

2.0
---

Version 2.2.0 (Unreleased)
^^^^^^^^^^^^^^^^^^^^^^^^^^

A stability and correctness release between v2.1.0 and the v3.0
protobuf migration. The headline change is the internal architecture
refactor that replaces ten parallel mutable dicts on ``Wrapper``
with two typed registries plus self-managing ``Subscription``
objects. Single source of truth for every kind of in-flight state,
no behavioural change to the public API.

**Added**

* **``Trade.serverOrder``** — the most recent unmerged TWS-authored
  snapshot of an order's state, with ``?`` placeholder values
  stripped. Populated on every ``openOrder`` callback alongside the
  existing allowlist merge into ``trade.order``. Non-breaking
  escape hatch: callers who need a yet-to-be-allowlisted field can
  read it directly from the raw snapshot. Existing semantics of
  ``trade.order`` are unchanged.
* **``IB.subscriptions()``** accessor returns the live-subscription
  enumeration.
* **More outbound events** emitted for matching inbound events so
  consumers can observe lifecycle without polling.
* **Defaults-system coverage** extended to ``realizedPNL`` and
  ``yield_`` on the matching wrapper paths.
* **``NewsTick``** now carries its originating ``Contract`` so
  downstream handlers don't have to round-trip through the
  subscription registry to identify which instrument the news
  applies to.

**Changed**

* **Internal architecture refactor (no public API change)**: ten
  parallel mutable dicts on ``Wrapper`` (``_futures``, ``_results``,
  ``_reqId2Contract``, ``reqId2Ticker``, ``ticker2ReqId``,
  ``reqId2Subscriber``, ``reqId2PnL``, ``reqId2PnlSingle``,
  ``pnlKey2ReqId``, ``pnlSingleKey2ReqId``) replaced with two typed
  registries plus eight self-managing ``Subscription`` types:

  * ``RequestRegistry`` owns every in-flight one-shot / singleton
    request. Discriminated key types (``ReqIdKey``,
    ``SingletonKey``, ``CompositeKey``, ``WhatIfKey``) prevent
    cross-namespace lookups. Idempotent ``set_result`` /
    ``set_error`` survive late-callback races.
  * ``SubscriptionRegistry`` owns every long-lived live data flow
    plus the per-contract ``Ticker`` pool. Each subscription
    (``MktDataSub``, ``TickByTickSub``, ``MktDepthSub``,
    ``RealTimeBarsSub``, ``HistoricalBarsSub``, ``ScannerSub``,
    ``PnLSub``, ``PnLSingleSub``) manages its own reqId, sends its
    own cancel, and unregisters from every index atomically on
    ``close()``.

* **Order field updates auto-track TWS** via a redesigned mutable
  field allowlist with explicit documentation of why the allowlist
  shape is correct for live trading (denylist failures silently
  overwrite user-set values; allowlist failures recover via
  ``Trade.serverOrder``).
* **Date normalization** extended to honour the user-requested
  timezone consistently across more wrapper callbacks.
* **Python 3.11 minimum** (was 3.10). Drops compatibility shims for
  older interpreters.
* **``uv`` toolchain support** alongside ``poetry``. Both
  ``uv sync`` and ``poetry install`` work; CI tests under both.

**Fixed**

* **Voluntary ``IB.disconnect()``** wraps
  ``wrapper.connectionClosed()`` in ``try/finally`` so the socket
  closes even if a user trade-event handler raises during teardown.
* **Redundant disconnect event** no longer fires twice on a clean
  socket close.
* **Scanner subscriptions release their registry indexes on cancel**
  — previously a bare ``client.cancelScannerSubscription`` left
  the entry behind, leaking memory across the daily server-side
  reset.
* **``Wrapper.connectionClosed``** iterates
  ``list(self.trades.values())`` so user-driven side-effects on
  trade events can't mutate the dict while it's being traversed.
* **``reqMktDepth``** no longer clears the in-progress DOM on a
  failed add — the prior depth book stays intact.
* **Six ``req*Async`` methods** actively cancel their request on
  timeout via the new ``_awaitOrTimeout`` helper instead of leaking
  a pending future.
* **``reqHistoricalDataAsync(keepUpToDate=True)``** closes its
  ``HistoricalBarsSub`` on timeout.
* **Late or replayed errors** no longer mutate already-finished
  ``Trade`` objects (Filled/Cancelled trades are skipped by
  ``Wrapper.error``).
* **What-if order placement** no longer hangs on wire-level errors:
  ``RequestRegistry.find_by_reqid`` checks both ``ReqIdKey`` and
  ``WhatIfKey`` so a contract-details-style error reaches its
  whatIf future.
* **``endTicker``** drops its ``reqId2Ticker`` entry — previously
  leaked one entry per cancel for the lifetime of the connection.
* **Single-flight fixed-key requests** prevent orphaned futures when
  two concurrent callers issue the same singleton request.
* **``Decoder.historicalTicksBidAsk``** decodes its
  ``TickAttribBidAsk`` mask bits per spec (bit 0 = bidPastLow,
  bit 1 = askPastHigh), matching the live ``tickByTickBidAsk``
  decoder. Previously the two flags were swapped on every historical
  bid/ask tick.
* **``Decoder.securityDefinitionOptionParameter``** coerces
  ``underlyingConId`` to ``int`` before invoking the wrapper.
* **``Decoder.execDetails``** narrows ``date | datetime`` ambiguity
  with ``isinstance`` instead of ``typing.cast``.
* **``Decoder.wrap()``'s exception handler** no longer references an
  unbound ``args`` local that could mask the original error with
  ``UnboundLocalError`` when per-field coercion itself raised.
* **HistoricalNews return type** corrected to the actual list-of-news
  shape (was annotated as a single news item).
* **Error 10349** demoted from order-cancelling error to warning
  so the order survives.
* **``tzdata``** dependency pin relaxed from too-specific to
  ``>=2025.2`` so existing user installs aren't unnecessarily
  upgraded.

**Performance**

* **``Wrapper._get_ticker``** cached as a bound method, eliminating
  per-tick attribute-lookup overhead on the dispatch hot path.
* **``Ticker``** is ``@dataclass(slots=True)``, eliminating
  per-attribute ``__dict__`` indirection on every tick handler.
* **``Decoder.wrap()``** resolves ``getattr(wrapper, methodName)``
  and the per-type converter list once at construction, removing a
  ``getattr`` and a four-way is-comparison ternary per dispatch.
* **``Decoder.parse()``** memoizes per-class field-coercion plans,
  removing the ``dataclasses.fields()`` walk from every call.
* **``defaultTimezone``** hoisted out of the historical-tick decode
  loops.
* **Module-level Final frozensets** ``_TICK_BY_TICK_LAST_TYPES`` /
  ``_PEG_BENCH_ORDER_TYPES`` replace inline set literals on hot
  paths.
* **Module-level Final dicts** for ``Client.send`` format handlers.
* **Typed PnL / PnL-single iterators** avoid a full subscription
  scan.

**Dependency / tooling**

* Minimum Python version raised to 3.11.
* ``uv`` toolchain supported as an alternative to ``poetry``.
* ``mypy`` no longer runs on PyPy (it was a no-op on that
  interpreter).

**Test coverage**

* Owned test suite covering decoder mask-bit fixes, slotted
  ``Ticker`` edge cases (copy / deepcopy / pickle / repr /
  ``__post_init__`` guard / typo enforcement), and the registry
  lifecycle invariants.
* Test helpers (``tests/_helpers.py``) consolidate
  ``inject_trade()`` / ``inject_fill()`` so future tests have a
  single place to update if ``Wrapper``'s internal trade/fill maps
  restructure.

Version 2.1.0 (2025-12-06)
^^^^^^^^^^^^^^^^^^^^^^^^^^

This release includes several bug fixes, performance improvements, and new features based on recent development work.

**Added**

* **New EFP Data Support**: Added Exchange for Physical (EFP) data structures and ticker fields for futures trading

  * New ``EfpData`` dataclass with fields for basis points, implied future price, dividend impact, and expiration data
  * New ticker fields: ``bidEfp``, ``askEfp``, ``lastEfp``, ``openEfp``, ``highEfp``, ``lowEfp``, ``closeEfp``
  * Support for EFP tick types in the wrapper

* **Additional Ticker Fields**: New fields for enhanced market data access

  * ``openInterest``, ``lastRthTrade``, ``lastRegTime``, ``optionBidExch``, ``optionAskExch``, ``bondFactorMultiplier``, ``creditmanMarkPrice``, ``creditmanSlowMarkPrice``, ``delayedLastTimestamp``, ``delayedHalted``, ``reutersMutualFunds``, ``etfNavClose``, ``etfNavPriorClose``, ``etfNavBid``, ``etfNavAsk``, ``etfNavLast``, ``etfFrozenNavLast``, ``etfNavHigh``, ``etfNavLow``, ``socialMarketAnalytics``, ``estimatedIpoMidpoint``, ``finalIpoLast``
  * New ``custGreeks`` option computation field
  * Enhanced ETF NAV (Net Asset Value) tracking fields

* **Environment Variable Configuration**: Added ability to override flexReport URL with environment variable

  * New ``IB_FLEXREPORT_URL`` environment variable support
  * URL validation for custom endpoints
  * Updated documentation for flexible endpoint configuration

* **Improved Event Loop Handling**: Better event loop retrieval with fallback mechanisms

  * Non-cached event loop access to avoid stale loop issues
  * Enhanced fallback for synchronous contexts
  * Better handling of closed event loops

* **Missing Tick Types**: Implemented various tick types that were missing from the library

  * Support for tick types 57, 78, 79, 92-102, 22, 60, 90, 53, 38-44, 25, 26, 32, 33, 84, 85, 91, 100, 45, 88, 48, 77
  * Optimized tick processing with lookup maps instead of if/else chains
  * New helper methods for timestamp and RT volume tick processing

**Changed**

* **Modern Python Syntax**: Updated type annotations to use modern Python 3.10+ syntax

  * Replaced ``Optional[Type]`` with ``Type | None`` union syntax
  * Converted ``Union[TypeA, TypeB]`` to ``TypeA | TypeB`` syntax
  * Updated imports to use more efficient organization

* **Ruff Configuration**: Improved code quality with expanded linter exclusions

  * Added ``notebooks/``, ``upstream_api_architecture/``, and ``examples/`` to exclude list
  * Updated ruff rules for modern Python patterns

* **Dependency Management**: Added explicit ``tzdata`` dependency for timezone support

  * Removed conditional import guard for ``zoneinfo`` since Python 3.9+ guarantees availability
  * Ensured timezone functionality works across all platforms

* **Performance Improvements**: Optimized tick processing with O(1) dictionary lookups

  * Replaced sequential if/else chains with lookup maps for tick types
  * Added helper methods for timestamp and RT volume processing
  * More efficient string-to-datetime conversion

**Fixed**

* **Timebars Typo**: Fixed ``isUnset`` to ``isNan`` helper function in TimeBars class (:issue:`197`)
* **FlexReport URL**: Fixed flexReport URL endpoint and added environment variable override support (:issue:`199`, :issue:`172`)
* **Setuptools Warning**: Fixed deprecation warnings for modern setuptools (:issue:`198`)
* **Event Loop Caching**: Fixed stale event loop bugs that occurred in complex async contexts (:issue:`160`, :issue:`186`, :issue:`159`)
* **Empty Ticker Fields**: Fixed initialization of additional ticker fields to proper unset values
* **Tick Type Processing**: Improved handling of various tick types with proper validation and processing
* **URL Validation**: Added proper URL validation for flexReport requests

**Dependency Updates**

* Added explicit ``tzdata`` dependency to ensure timezone functionality across platforms (:issue:`188`)
* Updated pyproject.toml to include license files and remove deprecated classifier (:issue:`182`)

Version 2.0.1 (2025-06-22)
^^^^^^^^^^^^^^^^^^^^^^^^^^

Minor dependency change to fix pypi package building.

**Dependency Fix**

The ``eventkit`` dependency is now ``aeventkit`` because ``eventkit`` is locked behind a closed account and pypi doesn't allow dependencies with direct github URL tags.

Version 2.0.0 (2025-06-13)
^^^^^^^^^^^^^^^^^^^^^^^^^^

This major release includes significant new features, performance improvements, and critical bug fixes. The most notable addition is the custom defaults system, allowing users to customize how ib_async handles empty values and timestamps throughout the library.

**Added**

* **Custom Default Values**: Major new feature allowing customization of default values used throughout the library via ``IBDefaults`` object passed to ``IB()`` constructor

  * Customize ``emptyPrice``, ``emptySize``, ``unset`` values, and ``timezone`` settings
  * Replace IBKR's default values (``emptyPrice=-1``, ``emptySize=0``, ``unset=nan``) with your preferred defaults (e.g., ``None``)
  * Set custom timezone for timestamp display (e.g., ``pytz.timezone("US/Eastern")`` instead of UTC)

* **Enhanced Ticker Data**: New ticker fields for improved market data analysis

  * ``timestamp``: Float format timestamp for easier mathematical operations alongside existing ``time`` field
  * ``shortable``: Shortability score (0-3) for instruments
  * ``volumeRate3Min``, ``volumeRate5Min``, ``volumeRate10Min``: IBKR-provided volume acceleration metrics
  * ``lastTimestamp``: Timestamp of the last trade event

* **OrderStatus Enhancements**: Extended order management capabilities

  * New API status states added to ``OrderStatus`` enum
  * ``totalQuantity()`` method to report total order quantity
  * Additional helper methods for reading order states

* **OrderState Conversion Helpers**: New utility methods for ``OrderState`` objects

  * ``numeric()``: Convert string values to numbers with optional digit rounding
  * ``formatted()``: Convert values to comma-separated formatted strings
  * Both methods handle ``UNSET_DOUBLE`` values automatically

* **OptionComputation Mathematical Operations**: Options can now be added, subtracted, and multiplied

  * Enables direct calculation of Greeks for spreads (e.g., vertical spreads: ``longGreeks - shortGreeks``)

* **Contract-from-params Abstraction**: Centralized logic for converting generic ``Contract`` objects to specific subclass types (e.g., ``Contract(secType="OPT")`` → ``Option()``)

* **Enhanced Contract Support**:

  * Event Contracts ("EC" security type) recognition for binary event betting
  * Bag contracts can now be hashed using leg details, symbol, and exchange

* **Improved Market Data Subscription Management**:

  * ``cancelMktData()`` now returns success/failure status instead of just logging
  * Contract lookups now use ``hash(contract)`` instead of ``id(contract)``, allowing reuse of equivalent contract objects

**Changed**

* **Breaking**: ``qualifyContractsAsync()`` behavior significantly improved

  * Now returns N results for N input contracts (previously returned fewer results if some failed)
  * Failed qualifications return ``None`` in corresponding position
  * New ``returnAll`` parameter: when ``True``, returns all possible matches as a list instead of failing for ambiguous contracts
  * Enables reliable ``zip(requestContracts, resultContracts)`` usage

* **Ticker Previous Value Logic**: Simplified and more accurate tracking

  * Previous price/size now always reflects the truly previous values, regardless of whether they match current values
  * Removed conditional updating that caused inaccurate "previous" data representation
  * Better performance by eliminating unnecessary comparisons

* **Type System Modernization**: Extensive type annotation improvements

  * ``Dict`` → ``dict``, ``List`` → ``list``, ``FrozenSet`` → ``frozenset`` throughout codebase
  * Enhanced ``Order`` class with proper type annotations and ``Decimal`` support for price/quantity fields
  * Converted ``NamedTuple`` instances to frozen dataclasses for better extensibility

* **Event Loop Handling**: Updated for modern Python compatibility (recent asyncio API changes)

**Fixed**

* **Critical Order Management Bug**: Fixed order cache deletion issues that caused "phantom orders"

  * Orders are no longer incorrectly deleted from client state when modification validation fails
  * Warning messages are now logged to order history instead of causing state corruption
  * Prevents situation where orders appear cancelled locally but remain active at broker

* **Order Modification Bug Prevention**: Added API-level validation to prevent common modification errors

  * Automatic handling of IBKR API field overwrites that conflict with user data
  * Prevents submission of unintended order updates from cached order objects

* **TWS API Contract Matching Bug Workaround**: Fixed cross-instrument contract suggestions

  * When requesting FOP contracts, IBKR was incorrectly also returning Event Contracts
  * Now filters results to only return contracts matching the requested security type

* **Bulk Data Tick Types**: Fixed default value handling in bulk tick processing
* **Last Trade Timestamp Validation**: Improved handling of invalid '0' timestamps from ticker startup
* **Volatility Order Type**: Corrected "VOL" → "VOLAT" order type specification
* **Missing Import**: Added missing import that was causing import errors
* **False Order Cache Deletion**: Additional fix for orders being incorrectly removed during modification validation

**Performance**

* **Tick Processing Optimization**: Significant performance improvements for market data handling

  * Replaced multi-case if/else branches with lookup maps for tick type processing
  * More efficient handling of generic ticks and Greek ticks
  * Added explicit error handling for unknown tick types to aid future development

* **Ticker Update Performance**: Eliminated unnecessary comparison operations during ticker updates

  * Always replace fields instead of conditionally checking for changes
  * Faster processing of instruments with frequent same-price trades

**Developer Experience**

* **Enhanced Error Handling**: Better error messages and logging throughout

  * Unknown tick types now generate explicit error messages for easier debugging
  * More verbose validation error reporting

* **Code Style**: Comprehensive formatting and linting improvements

  * Applied ``ruff format`` and ``ufmt`` formatting across entire codebase
  * Fixed various style warnings and modernized code patterns
  * Variable naming improvements (fixed illegal variable names like 'l')

**Internal**

* **Disconnection Logic**: Improved connection state management

  * Full state reset on disconnect/reconnect cycles
  * Returns connection status string with session details

* **Utility Functions**: Modernized ``util.py`` with updated Python patterns and async compatibility

**Migration Notes for v2.0.0:**

1. **qualifyContractsAsync() users**: The return value now always contains the same number of elements as input contracts. Check for ``None`` values to detect failed qualifications.

2. **Custom defaults users**: Consider using ``IBDefaults()`` to customize empty values if you've been manually handling ``-1`` prices or ``0`` sizes.

3. **Ticker previous value users**: The logic for ``previousPrice``/``previousSize`` is now more accurate but may show different values if you were relying on the old conditional update behavior.

4. **Order management users**: Order validation errors are now logged to order history instead of causing order deletions. Check order event logs for validation details.

1.0
---

Version 1.0.3 (2024-07-06)
^^^^^^^^^^^^^^^^^^^^^^^^^^

General improvements and minor correctness fixes.

* Fixed :issue:`42`: Order preview requests would often fail for non-limit-order types due to incorrect value comparison. This has previous attempted fixes over the years, but we finally found the proper fix to the other fixes. Now order preview requests work properly for all order types.
* Now market depth data is removed from the ``Ticker`` object when a market depth request is stopped because the data isn't being live updated anymore.
* Added `ib_fundamental <https://github.com/quantbelt/ib_fundamental>`_ to community utility listing in README

Version 1.0.2 (2024-06-29)
^^^^^^^^^^^^^^^^^^^^^^^^^^

General improvements and minor correctness fixes.

* Fixed :issue:`28`: Add ability to optionally disable account data synchronization on startup. If you are an advanced user, you may not need all your data synchronized on startup (which can slow down the initial connections due to the multiple sequential request loading) or you may want to control when the account data is loaded on your own schedule.
* Fixed :issue:`33`: Improved reliability of L2 depth of market reporting
* Fixed :issue:`10` and :issue:`11`: Fixed links in documentation
* Fixed :issue:`16`: Fixed documentation typo
* Fixed :issue:`32`: Use delayed data instead of denied data in example notebooks
* Improved error logging if a wrapped method fails
* Removed a potential exception when shutting down the event loop from within a larger system

Version 1.0.1 (2024-03-20)
^^^^^^^^^^^^^^^^^^^^^^^^^^

* Fixed :issue:`4`: Messaging sending bug for unresolved contracts due to cleanup in 1.0.0

Solved this messaging sending bug by refactoring message parsing logic to be more stable. Also added a test case verifying it works as expected now.

Version 1.0.0 (2024-03-18)
^^^^^^^^^^^^^^^^^^^^^^^^^^

This is the first version under new management after the unexpected passing of `Ewald de Wit <https://github.com/erdewit/ib_insync>`_ on March 11, 2024. We wish to maintain his legacy while continuing to improve the project going forward. We are resetting the project name, development practices, modernization levels, and project structure to hopefully grow more contributors over time.

This version update does not include any feature improvements and is functionally equivalent to the final version of ``ib_insync 0.9.86``.

Code Cleanup:

* Reformatted all code with ruff and improved readability throughout
* Now uses sets for membership checking everywhere
* Fixed a technical error around API message formatting

Project Changes:

* Renamed ib_insync to ib_async everywhere
* Increased minimum Python version from 3.6 (2016) to 3.10 (2021)
* Removed dependencies for supporting Python versions less than 3.9
* Converted README.rst to README.md
* Updated IBKR API links to new ibkrcampus instead of old github docs
* Removed setup.{py,cfg} to use Poetry for installing, docs, packaging
* Converted links from /erdewit/ account to new /ib-api-reloaded/ org
* Removed helper scripts for packaging and building docs
* Removed docs-generated HTML from repository
* Auto-build docs and update github docs site on every push
* Documentation now auto-builds and is hosted on github pages instead of readthedocs


Original ``ib_insync`` Changelog (2017-2023)
--------------------------------------------


Note: due to the project moving to a github organization, all auto-generated links below to mentioned issues and PRs don't work anymore. You can use the issue numbers in the `original ib_insync repo <https://github.com/erdewit/ib_insync/issues>`_ for historical reference.

0.9
---

Version 0.9.86
^^^^^^^^^^^^^^

* Fixed: :issue:`588`: Fixed account summary tag.
* Fixed: :issue:`589`: Fixed more account summary tags.
* pull:`598`: Year updates

Version 0.9.85
^^^^^^^^^^^^^^
* Fixed: :issue:`586`: Revert socket protocol back to version 176.

Version 0.9.84
^^^^^^^^^^^^^^
* Potential fix for ``reqWshEventData``.

Version 0.9.83
^^^^^^^^^^^^^^
* Added support for WSH (Wall Street Horizon) requests plus
  the (blocking) convenience methods ``getWshMetaData`` and ``getWshEventData``.
* Updated socket protocol to version 177.
* Added support for ``Event`` security type.

Version 0.9.82
^^^^^^^^^^^^^^

* Fixed: :issue:`534`: Session parsing for Forex contracts.
* Fixed: :issue:`536`: Handle empty session field.
* Fixed: :issue:`541`: Remove superfluous closing bracket.
* Fixed: :issue:`542`: Use float size for ``pnlSingle``.
* Fixed: :issue:`544`: Cancel head-time request after completion.
* Fixed: :issue:`545`: Return ``Trade`` instead of ``Order`` for
  ``reqOpenOrders`` and ``reqAllOpenOrders``.
* :pull:`553`: Volume bar added.
* :pull:`565`: Typo fix.

Version 0.9.81
^^^^^^^^^^^^^^

* Add ``ContractDetails.tradingSessions()`` and
  ``ContractDetails.liquidSessions()`` to parse session times.
* Fix ``IBC.on2fatimeout`` command line argument for Unix.

Version 0.9.80
^^^^^^^^^^^^^^

* Fix ``ib.reqMatchingSymbols`` to handle bond contracts.

Version 0.9.79
^^^^^^^^^^^^^^

* Fix datetime parsing.

Version 0.9.78
^^^^^^^^^^^^^^

* Added ``account`` parameter to ``ib.portfolio()``.
* Added ``IBC.on2fatimeout`` field.
* Removed obsolete ``IBController``.
* Fixed: :issue:`530`: Use explicit timezone in requests as per new API requirement.

Version 0.9.77
^^^^^^^^^^^^^^

* :pull:`528`: Fixes regression in ``client.py``.

Version 0.9.76
^^^^^^^^^^^^^^

* Fixed: :issue:`525`: For ``whatIf`` request treat error 110 as failure.

Version 0.9.75
^^^^^^^^^^^^^^

* Fixed: :issue:`524`: Use fix from Papakipos for issue with ``FlexReport`` downloading.

Version 0.9.74
^^^^^^^^^^^^^^

* Fix ``reqContractDetails`` bug in combination with latest TWS.
* Update the code to comply with stricter MyPy checks.

Version 0.9.73
^^^^^^^^^^^^^^

* :pull:`523`: Fix ``completedOrder`` parsing for new socket protocol.

Version 0.9.72
^^^^^^^^^^^^^^

* :pull:`507`: Fixes ``bondContractDetails`` request.
* Fixed: :issue:`502`: Treat error 110 as a warning.
* Added ``manualOrderTime`` and ``manualCancelOrderTime`` for audit trails.
* Added ``PEG MID`` and ``PEG BEST`` order types.
* Added contract fields ``description`` and ``issuerId``.
* Added ``IB.reqUserInfo()``.
* Support socket protocol version 176.

Version 0.9.71
^^^^^^^^^^^^^^

* :pull:`453`: Added support for ``bidExchange`` and ``askExchange`` fields to ``Ticker``.
* :pull:`489`: ``Watchdog.start()`` now returns a ``Future``.
* Fixed: :issue:`439`: Set ``marketDataType`` directly on ``Ticker``.
* Fixed: :issue:`441`: Add explicit timezone of None to accomodate pandas Timestamp.
* Fixed: :issue:`471`: Revised ``Ticker.marketPrice()`` calculation.
* Added ``minTick``, ``bboExchange`` and ``snapshotPermissions`` fields to ``Ticker``.
* Added ``minSize``, ``sizeIncrement`` and ``suggestedSizeIncrement`` fields to ``ContractDetails``.
* Added ``IB.reqHistoricalSchedule`` request.
* Added ``IB.reqSmartComponents`` request.
* Added ``Order.advancedErrorOverride`` field. Any advanced error message is made availble from
  ``Trade.advancedError``.
* Added a `recipe for integration with PyGame <https://ib-insync.readthedocs.io/recipes.html#integration-with-pygame>`_.
* Minimum required TWSAPI client protocol version is 157 now.

Version 0.9.70
^^^^^^^^^^^^^^

* Fixed: :issue:`413`: Set the appropriate events as done on disconnect.
* Exported symbols are now static so that the VSCode/PyLance code analyzer can understand it.

Version 0.9.69
^^^^^^^^^^^^^^

* Fixed: :issue:`403`: Change validity test for whatIfOrder response.

Version 0.9.68
^^^^^^^^^^^^^^

* Fixed: :issue:`402`: Downloading historical ticks for crypto currencies.

Version 0.9.67
^^^^^^^^^^^^^^

* ``Crypto`` security class added. To accommodate fractional crypto currency sizes,
  all the various ``size`` and ``volume`` fields that were of type ``int`` are now of type ``float``.
* :pull:`385`: Get day trades remaining for next four days in ``IB.accountSummary``.
* Fixed: :issue:`361`: Prevent ``util.logToConsole`` and ``util.logToFile`` from messing with the root logger.
* Fixed: :issue:`370`: Catch ``asyncio.CancelledError`` during connect.
* Fixed: :issue:`371`: Fix type annotation for ``reqMarketRuleAsync``.
* Fixed: :issue:`380`: Reject bogus ``whatIf`` order response.
* Fixed: :issue:`389`: Add ``TradeLogEntry.errorCode`` field.

Version 0.9.66
^^^^^^^^^^^^^^

* Fixed: :issue:`360`: Improved disconnect.
* Fixed issue with duplicate orderId.
* Update ``Order`` default values to work with the latest beta TWS/gateway.
* :pull:`348`: Added PySide6 support.

Version 0.9.65
^^^^^^^^^^^^^^

* Fixed: :issue:`337`.
* :pull:`317`: Update and order's ``totalQuantity``, ``lmtPrice``, ``auxPrice`` and ``orderType``
  when the order is modified externally.
* :pull:`332`: Typo.

Version 0.9.64
^^^^^^^^^^^^^^

* Fixed: :issue:`309`: Aggregate past fills into the ``Trade`` they belong to upon connect.
* ``ContFut`` objects are now hashable (:issue:`310`).
* Added ``Watchdog.probeTimeout`` parameter (:issue:`307`).

Version 0.9.63
^^^^^^^^^^^^^^

* Fixed :issue:`282`: ``util.Qt()`` also works with the ProactorEventLoop
  (default on Windows) now.
* Fixed :issue:`303`: A regression in TWS 480.4l+ is bypassed now to avoid
  ``IB.connect()`` timeouts. Request timeouts during syncing are logged as errors but will let
  the connect proceed.

Version 0.9.62
^^^^^^^^^^^^^^

* ``IB.TimezoneTWS`` field added, for when the TWS timezone differs from the
  local system timezone (:issue:`287`).
* ``IB.RaiseRequestErrors`` field added, can be set to ``True`` to raise
  ``RequestError`` when certain requests fail, instead of returning
  empty data (:pull:`296`).
* ``IB.accountSummaryAsync()`` method added (:issue:`267`).
* ``Watchdog.probeContract`` field added, to use a contract other then EURUSD
  for probing the data connection (:issue:`298`).
* ``Ticker.rtTime`` added (:issue:`274`, :pull:`275`). Please note that this
  timestamp appears to be mostly bogus.
* Fixed :issue:`270`: Clear ticker depth data when canceling market
  depth subscription.
* Fixed issue with duplicate order IDs.

Version 0.9.61
^^^^^^^^^^^^^^
* ``Ticker.marketDataType`` added to indicate the delayed/frozen status of
  the ``reqMktData`` ticks.

Version 0.9.60
^^^^^^^^^^^^^^

* ``IB.reqHistoricalData()`` has a new ``timeout`` parameter that automatically
  cancels the request after timing out.
* ``BracketOrder`` is iterable again.
* ``IB.waitOnUpdate()`` returns ``False`` on timeout now.
* :pull:`210`: Fix decoding of execDetails time.
* :pull:`215`: New scanner notebook added, courtesy of C. Valcarcel.
* :pull:`220`: Added ``readonly`` option for Watchdog.
* Fixed :issue:`221`: Delayed close ticks handling by ``Ticker``.
* Fixed :issue:`224`: Added timeout for ``completedOrders`` request during connect.
* Fixed :issue:`227`: ``IB.MaxSyncedSubAccounts`` added.
* Fixed :issue:`230`: Fixed ``IB.reqHistogramData`` method.
* Fixed :issue:`235`: ``Order.discretionaryAmt`` is now of type ``float`` (was ``int``).
* Fixed :issue:`236`: ``ticker.updateEvent`` is now fired for any change made to the ticker.
* Fixed :issue:`245`: Emit ``trade.statusEvent`` when order is implicitly canceled by a problem.
* You can now `sponsor the development of IB-insync! <https://github.com/sponsors/erdewit>`_

Version 0.9.59
^^^^^^^^^^^^^^

* PR #205 adds more typing annotations.
* ``dataclasses`` are now used for objects (instead of inheriting from a base
  ``Object``). For Python 3.6.* install it with ``pip install dataclasses``

Version 0.9.58
^^^^^^^^^^^^^^

* PR #196 treats error 492 as a warning so that scanner results can still
  be used.

Version 0.9.57
^^^^^^^^^^^^^^

* PR #184, #185 and #186 add the new Ticker fields
  ``rtTradeVolume``, ``auctionVolume``, ``auctionPrice`` and
  ``auctionImbalance``.
* PR #191 lets ``util.schedule`` return a handle that can be canceled.
* PR #192 adds ``throttleStart`` and ``throttleEnd`` events to the ``Client``.
* PR #194 adds better JSON support for ``namedtuple`` objects.

Version 0.9.56
^^^^^^^^^^^^^^

* Fix bug #178: ``Order.totalQuantity`` is now float.

Version 0.9.55
^^^^^^^^^^^^^^

* Sphinx update for documentation.

Version 0.9.54
^^^^^^^^^^^^^^

* ``ContractDetails.stockType`` added.
* Fixed ``Trade.filled()`` for combo (BAG) contracts.
* Server version check added to make sure TWS/gateway version is at least 972.

Version 0.9.53
^^^^^^^^^^^^^^

* Fix bug #155 (IB.commissionReportEvent not firing).
* Help editors with the code completion for Events.

Version 0.9.52
^^^^^^^^^^^^^^

* Fix Client.exerciseOptions (bug #152).

Version 0.9.51
^^^^^^^^^^^^^^

* Fix ``ib.placeOrder`` for older TWS/gateway versions.
* Better handling of unclean disconnects.

Version 0.9.50
^^^^^^^^^^^^^^

* Fix ``execDetailsEvent`` regression.
* Added ``readonly`` argument to ``ib.connect`` method. Set this to ``True``
  when the API is in read-only mode.

Version 0.9.49
^^^^^^^^^^^^^^

* ``ib.reqCompletedOrders()`` request added (requires TWS/gateway >= 976).
  Completed orders are automatically synced on connect and are available from
  ``ib.trades()``, complete with fills and commission info.
* Fixed bug #144.

Version 0.9.48
^^^^^^^^^^^^^^

* ``Ticker.halted`` field added.
* ``Client.reqFundamentalData`` fixed.

Version 0.9.47
^^^^^^^^^^^^^^

* ``ibapi`` package from IB is no longer needed, ib_async handles its own
  socket protocol encoding and decoding now.
* Documentation moved to readthedocs as
  rawgit will cease operation later this year.
* Blocking requests will now raise ``ConnectionError`` on a connection failure.
  This also goes for ``util.run``, ``util.timeRange``, etc.

Version 0.9.46
^^^^^^^^^^^^^^

* ``Event`` class has been replaced with the one from
  `eventkit <https://github.com/erdewit/eventkit>`_.
* Event-driven bar construction from ticks added (via ``Ticker.updateEvent``)
* Fixed bug #136.
* Default request throttling is now 45 requests/s for compatibility with
  TWS/gateway 974 and higher.

Version 0.9.45
^^^^^^^^^^^^^^

* ``Event.merge()`` added.
* ``TagValue`` serialization fixed.

Version 0.9.44
^^^^^^^^^^^^^^

* ``Event.any()`` and ``Event.all()`` added.
* Ticker fields added: ``tradeCount``, ``tradeRate``, ``volumeRate``,
  ``avOptionVolume``, ``markPrice``, ``histVolatility``,
  ``impliedVolatility``, ``rtHistVolatility`` and ``indexFuturePremium``.
* Parse ``ticker.fundamentalRatios`` into ``FundamentalRatios`` object.
* ``util.timeRangeAsync()`` and ``waitUntilAsync()`` added.
* ``ib.pendingTickersEvent`` now emits a ``set`` of Tickers
  instead of a ``list``.
* Tick handling has been streamlined.
* For harvesting tick data, an imperative code style with a
  ``waitOnUpdate`` loop should not be used anymore!

Version 0.9.43
^^^^^^^^^^^^^^

* Fixed issue #132.
* ``Event.aiter()`` added, all events can now be used
  as asynchronous iterators.
* ``Event.wait()`` added, all events are now also awaitable.
* Decreased default throttling to 95 requests per 2 sec.

Version 0.9.42
^^^^^^^^^^^^^^

* ``Ticker.shortableShares`` added (for use with generic tick 236).
* ``ib.reqAllOpenOrders()`` request added.
* tickByTick subscription will update ticker's bid, ask, last, etc.
* Drop redundant bid/ask ticks from ``reqMktData``.
* Fixed occasional "Group name cannot be null" error message on connect.
* ``Watchdog`` code rewritten to not need ``util.patchAsyncio``.
* ``Watchdog.start()`` is no longer blocking.

Version 0.9.41
^^^^^^^^^^^^^^

* Fixed bug #117.
* Fixed order modifications with TWS/gateway 974.

Version 0.9.40
^^^^^^^^^^^^^^

* ``Ticker.fundamentalRatios`` added (for use with generic tick 258).
* Fixed ``reqHistoricalTicks`` with MIDPOINT.

Version 0.9.39
^^^^^^^^^^^^^^

* Handle partially filled dividend data.
* Use ``secType='WAR'`` for warrants.

Version 0.9.38
^^^^^^^^^^^^^^

* ibapi v97.4 is now required.
* fixed tickByTick wrappers.

Version 0.9.37
^^^^^^^^^^^^^^

* Backward compatibility with older ibapi restored.

Version 0.9.36
^^^^^^^^^^^^^^

* Compatibility with ibapi v974.
* ``Client.setConnectOptions()`` added (for PACEAPI).

Version 0.9.35
^^^^^^^^^^^^^^

* ``Ticker.hasBidAsk()`` added.
* ``IB.newsBulletinEvent`` added.
* Various small fixes.

Version 0.9.34
^^^^^^^^^^^^^^

* Old event system (ib.setCallback) removed.
* Compatibility fix with previous ibapi version.

Version 0.9.33
^^^^^^^^^^^^^^

* Market scanner subscription improved.
* ``IB.scannerDataEvent`` now emits the full list of ScanData.
* ``ScanDataList`` added.

Version 0.9.32
^^^^^^^^^^^^^^

* Autocompletion with Jedi plugin as used in Spyder and VS Code working again.

Version 0.9.31
^^^^^^^^^^^^^^

* Request results will return specialized contract types (like ``Stock``)
  instead of generic ``Contract``.
* ``IB.scannerDataEvent`` added.
* ``ContractDetails`` field ``summary`` renamed to ``contract``.
* ``isSmartDepth`` parameter added for ``reqMktDepth``.
* Event loop nesting is now handled by the
  `nest_asyncio project <https://github.com/erdewit/nest_asyncio>`_.
* ``util.useQt`` is rewritten so that it can be used with any asyncio
  event loop, with support for both PyQt5 and PySide2.
  It does not use quamash anymore.
* Various fixes, extensive documentation overhaul and
  flake8-compliant code formatting.

Version 0.9.30
^^^^^^^^^^^^^^

* ``Watchdog.stop()`` will not trigger restart now.
* Fixed bug #93.

Version 0.9.29
^^^^^^^^^^^^^^
* ``util.patchAsyncio()`` updated for Python 3.7.

Version 0.9.28
^^^^^^^^^^^^^^

* ``IB.RequestTimeout`` added.
* ``util.schedule()`` accepts tz-aware datetimes now.
* Let ``client.disconnect()`` complete when no event loop is running.

Version 0.9.27
^^^^^^^^^^^^^^

* Fixed bug #77.

Version 0.9.26
^^^^^^^^^^^^^^

* PR #74 merged (``ib.reqCurrentTime()`` method added).
* Fixed bug with order error handling.

Version 0.9.25
^^^^^^^^^^^^^^

* Default throttling rate now compatible with reqTickers.
* Fixed issue with ``ib.waitOnUpdate()`` in combination.
  with ``ib.pendingTickersEvent``.
* Added timeout parameter for ``ib.waitOnUpdate()``.

Version 0.9.24
^^^^^^^^^^^^^^

* ``ticker.futuresOpenInterest`` added.
* ``execution.time`` was string, is now parsed to UTC datetime.
* ``ib.reqMarketRule()`` request added.

Version 0.9.23
^^^^^^^^^^^^^^

* Compatability with Tornado 5 as used in new Jupyter notebook server.

Version 0.9.22
^^^^^^^^^^^^^^

* updated ``ib.reqNewsArticle`` and ``ib.reqHistoricalNews`` to ibapi v9.73.07.

Version 0.9.21
^^^^^^^^^^^^^^

* updated ``ib.reqTickByTickData()`` signature to ibapi v9.73.07 while keeping
  backward compatibility.

Version 0.9.20
^^^^^^^^^^^^^^

* Fixed watchdog bug.

Version 0.9.19
^^^^^^^^^^^^^^

* Don't overwrite ``exchange='SMART'`` in qualifyContracts.

Version 0.9.18
^^^^^^^^^^^^^^

* Merged PR #65 (Fix misnamed event).


Version 0.9.17
^^^^^^^^^^^^^^

* New IB events ``disconnectedEvent``, ``newOrderEvent``, ``orderModifyEvent``
  and ``cancelOrderEvent``.
* ``Watchdog`` improvements.


Version 0.9.16
^^^^^^^^^^^^^^

* New event system that will supersede ``IB.setCallback()``.
* Notebooks updated to use events.
* ``Watchdog`` must now be given an ``IB`` instance.

Version 0.9.15
^^^^^^^^^^^^^^

* Fixed bug in default order conditions.
* Fixed regression from v0.9.13 in ``placeOrder``.

Version 0.9.14
^^^^^^^^^^^^^^

* Fixed ``orderStatus`` callback regression.

Version 0.9.13
^^^^^^^^^^^^^^

* Log handling improvements.
* ``Client`` with ``clientId=0`` can now manage manual TWS orders.
* ``Client`` with master clientId can now monitor manual TWS orders.


Version 0.9.12
^^^^^^^^^^^^^^

* Run ``IBC`` and ``IBController`` directly instead of via shell.

Version 0.9.11
^^^^^^^^^^^^^^

* Fixed bug when collecting ticks using ``ib.waitOnUpdate()``.
* Added ``ContFuture`` class (continuous futures).
* Added ``Ticker.midpoint()``.

Version 0.9.10
^^^^^^^^^^^^^^

* ``ib.accountValues()`` fixed for use with multiple accounts.

Version 0.9.9
^^^^^^^^^^^^^

* Fixed issue #57

Version 0.9.8
^^^^^^^^^^^^^

* Fix for ``ib.reqPnLSingle()``.

Version 0.9.7
^^^^^^^^^^^^^

* Profit and Loss (PnL) funcionality added.

Version 0.9.6
^^^^^^^^^^^^^

* ``IBC`` added.
* PR #53 (delayed greeks) merged.
* ``Ticker.futuresOpenInterest`` field removed.

Version 0.9.5
^^^^^^^^^^^^^

* Fixed canceling bar and tick subscriptions.

Version 0.9.4
^^^^^^^^^^^^^

* Fixed issue #49.

Version 0.9.3
^^^^^^^^^^^^^

* ``Watchdog`` class added.
* ``ib.setTimeout()`` added.
* ``Ticker.dividends`` added for use with ``genericTickList`` 456.
* Errors and warnings will now log the contract they apply to.
* ``IB`` ``error()`` callback signature changed to include contract.
* Fix for issue #44.

Version 0.9.2
^^^^^^^^^^^^^

* Historical ticks and realtime bars now return time in UTC.

Version 0.9.1
^^^^^^^^^^^^^

* ``IBController`` added.
* ``openOrder`` callback added.
* default arguments for ``ib.connect()`` and ``ib.reqMktData()``.

Version 0.9.0
^^^^^^^^^^^^^

* minimum API version is v9.73.06.
* ``tickByTick`` support.
* automatic request throttling.
* ``ib.accountValues()`` now works for multiple accounts.
* ``AccountValue.modelCode`` added.
* ``Ticker.rtVolume`` added.

0.8
---

Version 0.8.17
^^^^^^^^^^^^^^

* workaround for IBAPI v9.73.06 for ``Contract.lastTradeDateOrContractMonth``
  format.

Version 0.8.16
^^^^^^^^^^^^^^

* ``util.tree()`` method added.
* ``error`` callback signature changed to
  ``(reqId, errorCode, errorString)``.
* ``accountValue`` and ``accountSummary`` callbacks added.

Version 0.8.15
^^^^^^^^^^^^^^

* ``util.useQt()`` fixed for use with Windows.

Version 0.8.14
^^^^^^^^^^^^^^

* Fix for ``ib.schedule()``.

Version 0.8.13
^^^^^^^^^^^^^^

* Import order conditions into ib_async namespace.
* ``util.useQtAlt()`` added for using nested event loops on Windows with Qtl
* ``ib.schedule()`` added.

Version 0.8.12
^^^^^^^^^^^^^^

* Fixed conditional orders.

Version 0.8.11
^^^^^^^^^^^^^^

* ``FlexReport`` added.

Version 0.8.10
^^^^^^^^^^^^^^

* Fixed issue #22.

Version 0.8.9
^^^^^^^^^^^^^

* ``Ticker.vwap`` field added (for use with generic tick 233).
* Client with master clientId can now monitor orders and trades of
  other clients.

Version 0.8.8
^^^^^^^^^^^^^

* ``barUpdate`` event now used also for ``reqRealTimeBars`` responses
* ``reqRealTimeBars`` will return ``RealTimeBarList`` instead of list.
* realtime bars example added to bar data notebook.
* fixed event handling bug in ``Wrapper.execDetails``.

Version 0.8.7
^^^^^^^^^^^^^

* ``BarDataList`` now used with ``reqHistoricalData``; it also stores
  the request parameters.
* updated the typing annotations.
* added ``barUpdate`` event to ``IB``.
* bar- and tick-data notebooks updated to use callbacks for realtime data.

Version 0.8.6
^^^^^^^^^^^^^

* ``ticker.marketPrice`` adjusted to ignore price of -1.
* ``ticker.avVolume`` handling fixed.

Version 0.8.5
^^^^^^^^^^^^^

* ``realtimeBar`` wrapper fix.
* context manager for ``IB`` and ``IB.connect()``.

Version 0.8.4
^^^^^^^^^^^^^

* compatibility with upcoming ibapi changes.
* added ``error`` event to ``IB``.
* notebooks updated to use ``loopUntil``.
* small fixes and performance improvements.

Version 0.8.3
^^^^^^^^^^^^^

* new ``IB.reqHistoricalTicks()`` API method.
* new ``IB.loopUntil()`` method.
* fixed issues #4, #6, #7.

Version 0.8.2
^^^^^^^^^^^^^

* fixed swapped ``ticker.putOpenInterest`` vs ``ticker.callOpenInterest``.

Version 0.8.1
^^^^^^^^^^^^^

* fixed ``wrapper.tickSize`` regression.

Version 0.8.0
^^^^^^^^^^^^^

* support for realtime bars and ``keepUpToDate`` for historical bars
* added option greeks to ``Ticker``.
* new ``IB.waitUntil()`` and ``IB.timeRange()`` scheduling methods.
* notebooks no longer depend on PyQt5 for live updates.
* notebooks can be run in one go ('run all').
* tick handling bypasses ibapi decoder for more efficiency.

0.7
---

Version 0.7.3
^^^^^^^^^^^^^

* ``IB.whatIfOrder()`` added.
* Added detection and warning about common setup problems.

Version 0.7.2
^^^^^^^^^^^^^

* Removed import from ipykernel.

Version 0.7.1
^^^^^^^^^^^^^

* Removed dependencies for installing via pip.

Version 0.7.0
^^^^^^^^^^^^^

* added lots of request methods.
* order book (DOM) added.
* notebooks updated.

0.6
---

Version 0.6.1
^^^^^^^^^^^^^

* Added UTC timezone to some timestamps.
* Fixed issue #1.

Version 0.6.0
^^^^^^^^^^^^^

* Initial release.
