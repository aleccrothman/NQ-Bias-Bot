"""
job_eod.py - EOD score job
Railway Cron: 0 20 * * 1-5  (20:00 UTC = 4:00 PM ET, weekdays only)
"""
from shared import *

def main():
    print("[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running EOD score...")
    try:
        load_today_state()
        current_price = get_current_price()
        mo            = today_state["midnight_open"]
        direction     = today_state["bias"]

        if not current_price or not mo or not direction:
            send_telegram_text("EOD Score: No bias data for today.")
            return

        price_diff = current_price - mo
        abs_diff   = abs(price_diff)

        if abs_diff <= 75:
            result_type = "choppy"
        elif direction == "bullish":
            result_type = "win" if price_diff >= 100 else "failed"
        elif direction == "bearish":
            result_type = "win" if price_diff <= -100 else "failed"
        else:
            result_type = "choppy"

        winrate_data = record_result_v2(direction, result_type)

        # Telegram
        send_telegram_text(build_eod_message_v2(direction, result_type, current_price, mo, price_diff, winrate_data))

        # Discord
        send_discord_embed(build_discord_eod(direction, result_type, current_price, mo, price_diff, winrate_data),
                           webhook=DISCORD_WEBHOOK_EOD)

        print("EOD job complete.")
    except Exception as e:
        print("EOD error: " + str(e))
        try:
            send_telegram_text("<b>EOD Score Error:</b> " + str(e))
        except Exception:
            pass

if __name__ == "__main__":
    main()
