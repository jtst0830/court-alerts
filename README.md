# Court Docket Alerts

Automatically tracks new filings in four federal cases and exports them
to a live HTML page hosted on GitHub Pages.

## Tracked Cases

| Docket ID | Case |
|-----------|------|
| 71994556  | United States v. Cole |
| 72099987  | United States v. Cole |
| 72236187  | United States v. Brian Cole Jr. |
| 73220023  | Kerkhoff v. Blaze Media LLC |

## Setup

1. `pip install -r requirements.txt`
2. Copy `.env.example` → `.env` and fill in your tokens
3. Run `python seed-alerts.py` to create the initial `alerts.html`
4. Run `bash subscribe-alerts.sh` to subscribe to docket alerts
5. Configure a webhook endpoint in CourtListener → Settings → Webhooks
6. Start the server: `python webhook-server.py`
7. View alerts at `https://jtst0830.github.io/court-alerts/alerts.html`

## How It Works
```
CourtListener docket update
  → POST webhook to your server
  → Server formats alert as HTML
  → Server pushes updated alerts.html to GitHub via Contents API
  → GitHub Pages serves the live page
```

## CourtListener Webhook Details

- Events are POSTed as JSON with `webhook` and `payload` keys
- Sender IPs: `34.210.230.218`, `54.189.59.91`
- Each event includes an `Idempotency-Key` header for deduplication
