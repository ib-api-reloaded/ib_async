"""Protobuf wire-framing constants and outbound message ids.

``PROTOBUF_MSG_ID`` is the +200 sentinel that marks a protobuf frame on
the wire: every protobuf message is sent with ``wire_msgId = canonical +
200``, and a receiver subtracts 200 to recover the canonical id.

The constants below are IBKR's canonical ids for outbound messages. At
server version 226, the only one the client accepts, IBKR accepts every
one of them as protobuf, and the client sends nothing else.
"""

from __future__ import annotations

from typing import Final

# --- Wire sentinel --------------------------------------------------------
# A wire ``msgId`` greater than this means the body is a protobuf payload;
# the canonical id is recovered by subtracting this constant. Sender
# adds it via ``Client.sendProto``.
PROTOBUF_MSG_ID: Final = 200

# --- Canonical outbound message IDs --------------------------------------
# IBKR's protocol ids for outbound messages.
REQ_MKT_DATA: Final = 1
CANCEL_MKT_DATA: Final = 2
PLACE_ORDER: Final = 3
CANCEL_ORDER: Final = 4
REQ_OPEN_ORDERS: Final = 5
REQ_ACCT_DATA: Final = 6
REQ_EXECUTIONS: Final = 7
REQ_IDS: Final = 8
REQ_CONTRACT_DATA: Final = 9
REQ_MKT_DEPTH: Final = 10
CANCEL_MKT_DEPTH: Final = 11
REQ_NEWS_BULLETINS: Final = 12
CANCEL_NEWS_BULLETINS: Final = 13
SET_SERVER_LOGLEVEL: Final = 14
REQ_AUTO_OPEN_ORDERS: Final = 15
REQ_ALL_OPEN_ORDERS: Final = 16
REQ_MANAGED_ACCTS: Final = 17
REQ_FA: Final = 18
REPLACE_FA: Final = 19
REQ_HISTORICAL_DATA: Final = 20
EXERCISE_OPTIONS: Final = 21
REQ_SCANNER_SUBSCRIPTION: Final = 22
CANCEL_SCANNER_SUBSCRIPTION: Final = 23
REQ_SCANNER_PARAMETERS: Final = 24
CANCEL_HISTORICAL_DATA: Final = 25
REQ_CURRENT_TIME: Final = 49
REQ_REAL_TIME_BARS: Final = 50
CANCEL_REAL_TIME_BARS: Final = 51
REQ_CALC_IMPLIED_VOLAT: Final = 54
REQ_CALC_OPTION_PRICE: Final = 55
CANCEL_CALC_IMPLIED_VOLAT: Final = 56
CANCEL_CALC_OPTION_PRICE: Final = 57
REQ_GLOBAL_CANCEL: Final = 58
REQ_MARKET_DATA_TYPE: Final = 59
REQ_POSITIONS: Final = 61
REQ_ACCOUNT_SUMMARY: Final = 62
CANCEL_ACCOUNT_SUMMARY: Final = 63
CANCEL_POSITIONS: Final = 64
VERIFY_REQUEST: Final = 65
VERIFY_MESSAGE: Final = 66
QUERY_DISPLAY_GROUPS: Final = 67
SUBSCRIBE_TO_GROUP_EVENTS: Final = 68
UPDATE_DISPLAY_GROUP: Final = 69
UNSUBSCRIBE_FROM_GROUP_EVENTS: Final = 70
START_API: Final = 71
REQ_POSITIONS_MULTI: Final = 74
CANCEL_POSITIONS_MULTI: Final = 75
REQ_ACCOUNT_UPDATES_MULTI: Final = 76
CANCEL_ACCOUNT_UPDATES_MULTI: Final = 77
REQ_SEC_DEF_OPT_PARAMS: Final = 78
REQ_SOFT_DOLLAR_TIERS: Final = 79
REQ_FAMILY_CODES: Final = 80
REQ_MATCHING_SYMBOLS: Final = 81
REQ_MKT_DEPTH_EXCHANGES: Final = 82
REQ_SMART_COMPONENTS: Final = 83
REQ_NEWS_ARTICLE: Final = 84
REQ_NEWS_PROVIDERS: Final = 85
REQ_HISTORICAL_NEWS: Final = 86
REQ_HEAD_TIMESTAMP: Final = 87
REQ_HISTOGRAM_DATA: Final = 88
CANCEL_HISTOGRAM_DATA: Final = 89
CANCEL_HEAD_TIMESTAMP: Final = 90
REQ_MARKET_RULE: Final = 91
REQ_PNL: Final = 92
CANCEL_PNL: Final = 93
REQ_PNL_SINGLE: Final = 94
CANCEL_PNL_SINGLE: Final = 95
REQ_HISTORICAL_TICKS: Final = 96
REQ_TICK_BY_TICK_DATA: Final = 97
CANCEL_TICK_BY_TICK_DATA: Final = 98
REQ_COMPLETED_ORDERS: Final = 99
REQ_WSH_META_DATA: Final = 100
CANCEL_WSH_META_DATA: Final = 101
REQ_WSH_EVENT_DATA: Final = 102
CANCEL_WSH_EVENT_DATA: Final = 103
REQ_USER_INFO: Final = 104
REQ_CURRENT_TIME_IN_MILLIS: Final = 105
CANCEL_CONTRACT_DATA: Final = 106
CANCEL_HISTORICAL_TICKS: Final = 107
REQ_CONFIG: Final = 108
UPDATE_CONFIG: Final = 109
