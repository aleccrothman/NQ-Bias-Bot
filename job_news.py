"""
job_news.py - Macro news job
Railway Cron: 0 11 * * 1-5  (11:00 UTC = 7:00 AM ET, weekdays only)
"""
from shared import *

def main():
    print("[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running macro news job...")
    try:
        all_events = get_forex_factory_news(days=3)
        # Telegram
        send_telegram_text(build_news_message(all_events))
        # Discord
        send_discord_embed(build_discord_news(all_events), webhook=DISCORD_WEBHOOK_NEWS)
        print("News job complete.")
    except Exception as e:
        print("News job error: " + str(e))
        try:
            send_telegram_text("<b>News Error:</b> " + str(e))
        except Exception:
            pass

if __name__ == "__main__":
    main()
