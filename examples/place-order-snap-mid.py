from ib_async import IB, Future, SnapMidOrder, TimeCondition
from datetime import datetime, timedelta, timezone

ib = IB()
ib.connect(
    host = "127.0.0.1",
    port = 7497,
    clientId = 1
)

# Define the ES futures contract (E-mini S&P 500 Futures)
# SNAP MID orders are mostly used to make better-than MKT fill
# for highly liquid instruments, but those which don't support
# more sophisticated IB order types.
# Common example is Futures/CFD
contract = Future(
    symbol = "ES",
    lastTradeDateOrContractMonth = "20250321",   # use actual expiration date
    exchange = "CME"
)

# Define an execution condition for order - some time in future
# to make sure order is not executed immediately (for testing purposes)
future_date = datetime.now(timezone.utc) + timedelta(days = 10)
time_condition = TimeCondition(
    time = future_date.strftime("%Y%m%d %H:%M:%S UTC")
)

# Create order object
order = SnapMidOrder(
    action = "BUY",
    totalQuantity = 1,
    conditions = [
        time_condition
    ]
)

# Place the order with the time condition
print("Placing order...")
trade = ib.placeOrder(contract, order)

print("waiting a bit...")
ib.sleep(1)

print("Order placed")
print(f"status: {trade.orderStatus.status}")

ib.disconnect()
