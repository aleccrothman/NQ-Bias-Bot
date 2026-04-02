"""
job_bias.py - Morning bias job
Railway Cron: 30 12 * * 1-5  (12:30 UTC = 8:30 AM ET, weekdays only)
"""
from shared import *

def main():
    print("[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running morning bias job...")
    windows = get_session_windows()
    try:
        tv = load_tv_levels()
        if tv.get("midnight_open") and tv.get("asia_high") and tv.get("london_high"):
            print("  -> Using TradingView webhook levels")
            midnight_open = tv["midnight_open"]
            asia_high     = tv["asia_high"]
            asia_low      = tv["asia_low"]
            london_high   = tv["london_high"]
            london_low    = tv["london_low"]
            london_close  = london_low
        else:
            print("  -> Using Yahoo Finance")
            midnight_open = get_midnight_open(windows["midnight_open_utc"])
            asia_high, asia_low, _ = get_session_hl(windows["asia_start_utc"], windows["asia_end_utc"])
            london_high, london_low, london_close = get_session_hl(windows["london_start_utc"], windows["london_end_utc"])

        pdh, pdl      = get_previous_day_hl()
        current_price = get_current_price() or midnight_open
        screenshot    = take_chart_screenshot()

        missing = [k for k, v in {"midnight_open": midnight_open, "asia_high": asia_high,
                                   "london_high": london_high, "current_price": current_price}.items() if not v]
        if missing:
            print("  -> Missing data: " + str(missing))

        if not midnight_open or not current_price or (not asia_high and not london_high):
            msg = "NQ Bias Bot: Missing critical session data - " + str(missing)
            send_telegram_text(msg)
            return

        if not asia_high and london_high:
            asia_high, asia_low = london_high, london_low
        if not london_high and asia_high:
            london_high, london_low = asia_high, asia_low

        bias  = compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low, london_close)
        ifvgs = detect_ifvgs(current_price)

        today_state.update({
            "bias": bias["direction"], "score": bias["score"],
            "midnight_open": midnight_open,
            "asia_high": asia_high, "asia_low": asia_low,
            "london_high": london_high, "london_low": london_low,
            "pdh": pdh, "pdl": pdl,
            "date": datetime.now(ET).strftime("%Y-%m-%d"),
        })
        save_today_state()

        grade = bias.get("grade", "C")
        if grade == "A" and ifvgs:
            grade = "A+"

        # Telegram
        send_teaser(bias["overall"], grade, datetime.now(ET).strftime("%a %b %d"))
        caption = build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                                        london_high, london_low, pdh, pdl, bias, ifvgs)
        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, caption)
        else:
            send_telegram_text(caption + "\nChart screenshot unavailable.")

        # Discord
        embed = build_discord_morning(current_price, midnight_open, asia_high, asia_low,
                                      london_high, london_low, pdh, pdl, bias, ifvgs)
        send_discord_embed(embed, screenshot if screenshot and screenshot.exists() else None,
                           webhook=DISCORD_WEBHOOK_BIAS)

        print("Morning bias job complete.")
    except Exception as e:
        print("Morning bias error: " + str(e))
        try:
            send_telegram_text("<b>Morning Bias Error:</b> " + str(e))
        except Exception:
            pass

if __name__ == "__main__":
    main()
