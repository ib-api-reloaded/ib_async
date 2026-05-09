"""Internal protobuf integration layer.

Hand-written converters that translate IBKR protobuf messages to and
from our existing domain dataclasses (``Contract``, ``Order``,
``Trade``, etc.). Stays internal; nothing here is part of the public
``ib_async`` API surface.
"""
