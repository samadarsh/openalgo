# PendingOrders

List the orders your API key queued in the Action Center, and what became of each one.

In Semi-Auto order mode, `placeorder` and the other order calls do not reach the broker: they
wait in the Action Center for you to approve or reject them, and the response carries only a
`pending_order_id`. This endpoint lets the client that queued an order find out whether it is
still pending, was approved (with the broker order id and broker status once it was sent) or
was rejected (with the reason). It is read-only: approving and rejecting stay in the Action
Center.

## Endpoint URL

```http
Local Host   :  POST http://127.0.0.1:5000/api/v1/pendingorders
Ngrok Domain :  POST https://<your-ngrok-domain>.ngrok-free.app/api/v1/pendingorders
Custom Domain:  POST https://<your-custom-domain>/api/v1/pendingorders
```

## Sample API Request

```json
{
  "apikey": "<your_app_apikey>",
  "status": "approved",
  "limit": 50
}
```

## Sample cURL Request

```bash
curl -X POST http://127.0.0.1:5000/api/v1/pendingorders \
  -H 'Content-Type: application/json' \
  -d '{
  "apikey": "<your_app_apikey>"
}'
```

## Sample API Response

```json
{
  "status": "success",
  "data": {
    "orders": [
      {
        "pending_order_id": 42,
        "api_type": "placeorder",
        "status": "approved",
        "created_at_ist": "2026-11-03 15:05:12 IST",
        "approved_at_ist": "2026-11-03 15:07:40 IST",
        "rejected_at_ist": null,
        "rejected_reason": null,
        "broker_order_id": "251103000123456",
        "broker_status": "complete",
        "order": {
          "strategy": "MyStrategy",
          "symbol": "SBIN",
          "exchange": "NSE",
          "action": "BUY",
          "quantity": "10",
          "pricetype": "LIMIT",
          "price": "812.35",
          "product": "CNC"
        }
      }
    ]
  }
}
```

## Request Body

| Parameter | Description | Mandatory/Optional | Default Value |
|-----------|-------------|-------------------|---------------|
| apikey | Your OpenAlgo API key | Mandatory | - |
| status | Only orders in this state: `pending`, `approved` or `rejected` | Optional | all |
| limit | Most orders returned, newest first (1 to 500) | Optional | 100 |

## Response Fields

| Field | Type | Description |
|-------|------|-------------|
| pending_order_id | number | The id `placeorder` returned in Semi-Auto |
| api_type | string | The call that was queued, e.g. `placeorder`, `basketorder` |
| status | string | `pending`, `approved` or `rejected` |
| created_at_ist / approved_at_ist / rejected_at_ist | string | When it was queued, approved or rejected (IST) |
| rejected_reason | string | The reason given when it was rejected |
| broker_order_id | string | The broker's order id, once an approved order was sent |
| broker_status | string | The broker's answer to the approved order, e.g. `complete`, `open`, `rejected` |
| order | object | The order as it was queued, without the API key |

## Notes

- Only the orders of the user the API key belongs to are returned.
- An order stays `pending` until you approve or reject it in the Action Center.
- Works in both Auto and Semi-Auto, and in analyzer mode.
