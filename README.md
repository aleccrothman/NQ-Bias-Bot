# Smokey Bias Bot - Railway Cron Setup

## Files
- `shared.py` — all shared code (import this in every job)
- `job_news.py` — macro news
- `job_bias.py` — morning bias + chart
- `job_nyo.py` — NYO update + chart
- `job_eod.py` — EOD score + win rate

## Railway Setup

Create 4 separate Cron Job services in Railway, each pointing to this repo.

| Service Name     | Start Command             | Cron Schedule     | When (ET)     |
|------------------|---------------------------|-------------------|---------------|
| smokey-news      | `python job_news.py`      | `0 11 * * 1-5`    | 7:00 AM ET    |
| smokey-bias      | `python job_bias.py`      | `30 12 * * 1-5`   | 8:30 AM ET    |
| smokey-nyo       | `python job_nyo.py`       | `0 13 * * 1-5`    | 9:00 AM ET    |
| smokey-eod       | `python job_eod.py`       | `0 20 * * 1-5`    | 4:00 PM ET    |

## Environment Variables (set on ALL 4 services)

```
TELEGRAM_BOT_TOKEN
TELEGRAM_CHAT_ID
TELEGRAM_CHANNEL_ID
DISCORD_WEBHOOK_NEWS
DISCORD_WEBHOOK_BIAS
DISCORD_WEBHOOK_NYO
DISCORD_WEBHOOK_EOD
TV_USERNAME
TV_PASSWORD
```

## Requirements
```
requests
yfinance
pytz
playwright
pillow
```
