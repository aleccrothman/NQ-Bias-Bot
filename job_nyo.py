"""
job_nyo.py - NYO update job
Railway Cron: 0 13 * * 1-5  (13:00 UTC = 9:00 AM ET, weekdays only)
"""
from shared import *

def main():
    print("[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running NYO update...")
    try:
        load_today_state()
        current_price = get_current_price()

        if not current_price or not today_state["midnight_open"]:
            send_telegram_text("NYO Update: No data available. Bias may not have run yet.")
            return

        bias = {
            "overall":   "BULLISH" if today_state["bias"] == "bullish" else "BEARISH" if today_state["bias"] == "bearish" else "NEUTRAL",
            "direction": today_state["bias"],
            "score":     today_state["score"],
        }
        ifvgs      = detect_ifvgs(current_price)
        screenshot = take_chart_screenshot()

        # Telegram
        tg_msg = build_nyo_message(current_price, bias,
                                    today_state["midnight_open"],
                                    today_state["asia_high"],   today_state["asia_low"],
                                    today_state["london_high"], today_state["london_low"],
                                    today_state["pdh"],         today_state["pdl"], ifvgs)
        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, tg_msg)
        else:
            send_telegram_text(tg_msg)

        # Discord
        embed = build_discord_nyo(current_price, bias,
                                   today_state["midnight_open"],
                                   today_state["asia_high"],   today_state["asia_low"],
                                   today_state["london_high"], today_state["london_low"],
                                   today_state["pdh"],         today_state["pdl"], ifvgs)
        send_discord_embed(embed, screenshot if screenshot and screenshot.exists() else None,
                           webhook=DISCORD_WEBHOOK_NYO)

        print("NYO job complete.")
    except Exception as e:
        print("NYO error: " + str(e))
        try:
            send_telegram_text("<b>NYO Update Error:</b> " + str(e))
        except Exception:
            pass

if __name__ == "__main__":
    main()
