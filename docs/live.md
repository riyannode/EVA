# Live Execution

Live execution is a separate operator surface from EVA's adaptive benchmark graph. The graph can evaluate synthetic and paper targets, but it cannot submit a live order.

Set the backend environment explicitly:

```powershell
BITGET_MODE=live
ENABLE_LIVE_TRADING=true
BITGET_EXECUTABLE=bgc
```

The dashboard first calls `POST /trading/orders/preview`. The operator must then enable the confirmation checkbox and submit a UUID idempotency key through `POST /trading/orders`.

The SQLite `live_orders` ledger records `SUBMITTING`, `SUBMITTED`, `FAILED`, or `UNKNOWN`. `UNKNOWN` means the CLI outcome could not be established, commonly after a timeout. Do not retry an `UNKNOWN` request with the same or a new key until the exchange order history is reconciled.

The adapter uses the fixed `bgc order --action place` argument array without `shell=True`. The project does not send an order during tests or startup. Credentials remain in the process environment and are never returned by the API.
