# Kangaroo

PWA for startup founders: social progress feed, leaderboard, and an AI roast agent that challenges ideas through the project journey.

## Run

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
flask --app run.py run
```

## Environment

| Variable | Description |
|----------|-------------|
| `DATABASE_URL` | SQLite default; use PostgreSQL in prod |
| `REDIS_URL` | Optional Redis for OTP cache |
| `SMS_PROVIDER` | `mock` (default) or `twilio` |
| `SMS_API_KEY` | Twilio `account_sid:auth_token` |
| `OPENAI_API_KEY` | Required for AI features |
| `INVESTOR_INVITE_CODES` | Comma-separated codes for investor signup |
| `AI_FREE_MONTHLY_LIMIT` | Free tier AI requests per month (default 30) |
| `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` | Web push |

## Migrations

```bash
flask --app run.py db upgrade
```
