from google.protobuf.internal import containers as _containers
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class ScannerSubscription(_message.Message):
    __slots__ = ("numberOfRows", "instrument", "locationCode", "scanCode", "abovePrice", "belowPrice", "aboveVolume", "marketCapAbove", "marketCapBelow", "moodyRatingAbove", "moodyRatingBelow", "spRatingAbove", "spRatingBelow", "maturityDateAbove", "maturityDateBelow", "couponRateAbove", "couponRateBelow", "excludeConvertible", "averageOptionVolumeAbove", "scannerSettingPairs", "stockTypeFilter", "scannerSubscriptionFilterOptions", "scannerSubscriptionOptions")
    class ScannerSubscriptionFilterOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    class ScannerSubscriptionOptionsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    NUMBEROFROWS_FIELD_NUMBER: _ClassVar[int]
    INSTRUMENT_FIELD_NUMBER: _ClassVar[int]
    LOCATIONCODE_FIELD_NUMBER: _ClassVar[int]
    SCANCODE_FIELD_NUMBER: _ClassVar[int]
    ABOVEPRICE_FIELD_NUMBER: _ClassVar[int]
    BELOWPRICE_FIELD_NUMBER: _ClassVar[int]
    ABOVEVOLUME_FIELD_NUMBER: _ClassVar[int]
    MARKETCAPABOVE_FIELD_NUMBER: _ClassVar[int]
    MARKETCAPBELOW_FIELD_NUMBER: _ClassVar[int]
    MOODYRATINGABOVE_FIELD_NUMBER: _ClassVar[int]
    MOODYRATINGBELOW_FIELD_NUMBER: _ClassVar[int]
    SPRATINGABOVE_FIELD_NUMBER: _ClassVar[int]
    SPRATINGBELOW_FIELD_NUMBER: _ClassVar[int]
    MATURITYDATEABOVE_FIELD_NUMBER: _ClassVar[int]
    MATURITYDATEBELOW_FIELD_NUMBER: _ClassVar[int]
    COUPONRATEABOVE_FIELD_NUMBER: _ClassVar[int]
    COUPONRATEBELOW_FIELD_NUMBER: _ClassVar[int]
    EXCLUDECONVERTIBLE_FIELD_NUMBER: _ClassVar[int]
    AVERAGEOPTIONVOLUMEABOVE_FIELD_NUMBER: _ClassVar[int]
    SCANNERSETTINGPAIRS_FIELD_NUMBER: _ClassVar[int]
    STOCKTYPEFILTER_FIELD_NUMBER: _ClassVar[int]
    SCANNERSUBSCRIPTIONFILTEROPTIONS_FIELD_NUMBER: _ClassVar[int]
    SCANNERSUBSCRIPTIONOPTIONS_FIELD_NUMBER: _ClassVar[int]
    numberOfRows: int
    instrument: str
    locationCode: str
    scanCode: str
    abovePrice: float
    belowPrice: float
    aboveVolume: int
    marketCapAbove: float
    marketCapBelow: float
    moodyRatingAbove: str
    moodyRatingBelow: str
    spRatingAbove: str
    spRatingBelow: str
    maturityDateAbove: str
    maturityDateBelow: str
    couponRateAbove: float
    couponRateBelow: float
    excludeConvertible: bool
    averageOptionVolumeAbove: int
    scannerSettingPairs: str
    stockTypeFilter: str
    scannerSubscriptionFilterOptions: _containers.ScalarMap[str, str]
    scannerSubscriptionOptions: _containers.ScalarMap[str, str]
    def __init__(self, numberOfRows: _Optional[int] = ..., instrument: _Optional[str] = ..., locationCode: _Optional[str] = ..., scanCode: _Optional[str] = ..., abovePrice: _Optional[float] = ..., belowPrice: _Optional[float] = ..., aboveVolume: _Optional[int] = ..., marketCapAbove: _Optional[float] = ..., marketCapBelow: _Optional[float] = ..., moodyRatingAbove: _Optional[str] = ..., moodyRatingBelow: _Optional[str] = ..., spRatingAbove: _Optional[str] = ..., spRatingBelow: _Optional[str] = ..., maturityDateAbove: _Optional[str] = ..., maturityDateBelow: _Optional[str] = ..., couponRateAbove: _Optional[float] = ..., couponRateBelow: _Optional[float] = ..., excludeConvertible: bool = ..., averageOptionVolumeAbove: _Optional[int] = ..., scannerSettingPairs: _Optional[str] = ..., stockTypeFilter: _Optional[str] = ..., scannerSubscriptionFilterOptions: _Optional[_Mapping[str, str]] = ..., scannerSubscriptionOptions: _Optional[_Mapping[str, str]] = ...) -> None: ...
