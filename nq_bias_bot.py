"""
NQ1! Daily Bias Bot — Final
Smokey Bias Bot

Schedule (all times ET, stored as UTC for Railway):
  12:00 UTC (08:00 ET) — Morning bias + TradingView chart screenshot
  13:00 UTC (09:00 ET) — NYO update
  20:00 UTC (16:00 ET) — EOD score + win rate
"""

import os
import json
import time
import requests
import schedule
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# ─────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN  = "8757455017:AAFuZgFN5ml3xNCVVE3ww8DyzWThtQrTMos"
TELEGRAM_CHAT_ID    = "5048230949"
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003726448503")

TV_USERNAME  = os.getenv("TV_USERNAME", "")
TV_PASSWORD  = os.getenv("TV_PASSWORD", "")
TV_CHART_URL = "https://www.tradingview.com/chart/hcbriKzA/"

SYMBOL          = "NQ=F"
IFVG_RANGE_PTS  = 100
IFVG_LOOKBACK_H = 48

ET  = pytz.timezone("America/New_York")
UTC = pytz.utc

SCREENSHOT_PATH = Path("/tmp/nq_chart.png")
WINRATE_FILE    = Path("/tmp/nq_winrate.json")

# Shared state between jobs
today_state = {
    "bias":          None,
    "score":         0,
    "midnight_open": None,
    "asia_high":     None,
    "asia_low":      None,
    "london_high":   None,
    "london_low":    None,
    "pdh":           None,
    "pdl":           None,
    "date":          None,
}


# ─────────────────────────────────────────────
# WIN RATE TRACKER
# ─────────────────────────────────────────────

def load_winrate():
    if WINRATE_FILE.exists():
        try:
            return json.loads(WINRATE_FILE.read_text())
        except Exception:
            pass
    return {"wins": 0, "losses": 0, "neutrals": 0, "history": []}


def save_winrate(data):
    WINRATE_FILE.write_text(json.dumps(data, indent=2))


def record_result(bias_direction, delivered):
    data = load_winrate()
    date_str = datetime.now(ET).strftime("%Y-%m-%d")
    if bias_direction == "neutral":
        data["neutrals"] += 1
        result = "⚪"
    elif delivered:
        data["wins"] += 1
        result = "✅"
    else:
        data["losses"] += 1
        result = "❌"
    data["history"].append({
        "date": date_str, "bias": bias_direction,
        "delivered": delivered, "result": result,
    })
    data["history"] = data["history"][-30:]
    save_winrate(data)
    return data


def get_winrate_summary():
    data = load_winrate()
    wins     = data["wins"]
    losses   = data["losses"]
    neutrals = data["neutrals"]
    total    = wins + losses
    pct      = (wins / total * 100) if total > 0 else 0
    msg  = f"📈 <b>Bias Win Rate</b>\n"
    msg += f"✅ {wins}W  ❌ {losses}L  ⚪ {neutrals}N\n"
    msg += f"<b>{pct:.0f}% accuracy</b> ({total} directional days)\n"
    if data["history"]:
        streak = "".join(r["result"] for r in data["history"][-10:])
        msg += f"Last 10: {streak}\n"
    msg += "<i>Not financial advice.</i>"
    return msg


# ─────────────────────────────────────────────
# DATA FETCHING
# ─────────────────────────────────────────────

def fetch_candles_yf(start_utc, end_utc, interval="1m"):
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(start=start_utc, end=end_utc, interval=interval)
    if df.empty:
        return []
    df = df.reset_index()
    candles = []
    for _, row in df.iterrows():
        candles.append({
            "open":  float(row["Open"]),
            "high":  float(row["High"]),
            "low":   float(row["Low"]),
            "close": float(row["Close"]),
        })
    return candles


def get_session_windows():
    now_et   = datetime.now(ET)
    today_et = now_et.date()
    midnight = ET.localize(datetime(today_et.year, today_et.month, today_et.day, 0, 0))
    return {
        "midnight_open_utc": midnight.astimezone(UTC),
        "asia_start_utc":   (midnight - timedelta(hours=6)).astimezone(UTC),
        "asia_end_utc":      midnight.astimezone(UTC),
        "london_start_utc":  midnight.astimezone(UTC),
        "london_end_utc":   (midnight + timedelta(hours=5)).astimezone(UTC),
    }


def get_midnight_open(midnight_utc):
    candles = fetch_candles_yf(midnight_utc, midnight_utc + timedelta(minutes=5), "1m")
    return candles[0]["open"] if candles else None


def get_session_hl(start_utc, end_utc):
    candles = fetch_candles_yf(start_utc, end_utc, "1m")
    if not candles:
        return None, None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles), candles[-1]["close"]


def get_current_price():
    now_utc = datetime.now(UTC)
    candles = fetch_candles_yf(now_utc - timedelta(minutes=10), now_utc, "1m")
    return candles[-1]["close"] if candles else None


def get_previous_day_hl():
    now_et   = datetime.now(ET)
    today_et = now_et.date()
    midnight = ET.localize(datetime(today_et.year, today_et.month, today_et.day, 0, 0))
    prev_open  = (midnight - timedelta(hours=30)).astimezone(UTC)
    prev_close = (midnight - timedelta(hours=1)).astimezone(UTC)
    candles = fetch_candles_yf(prev_open, prev_close, "60m")
    if not candles:
        return None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles)


# ─────────────────────────────────────────────
# iFVG DETECTION
# ─────────────────────────────────────────────

def detect_ifvgs(current_price):
    now_utc   = datetime.now(UTC)
    start_utc = now_utc - timedelta(hours=IFVG_LOOKBACK_H)
    candles   = fetch_candles_yf(start_utc, now_utc, "60m")
    if len(candles) < 3:
        return []

    fvg_zones = []
    for i in range(2, len(candles)):
        c0, c2 = candles[i - 2], candles[i]
        if c0["high"] < c2["low"]:
            fvg_zones.append({"top": c2["low"], "bottom": c0["high"],
                               "type": "bull_fvg", "formed_at": i})
        if c0["low"] > c2["high"]:
            fvg_zones.append({"top": c0["low"], "bottom": c2["high"],
                               "type": "bear_fvg", "formed_at": i})

    ifvgs = []
    for fvg in fvg_zones:
        ifvg_type = None
        for j in range(fvg["formed_at"] + 1, len(candles)):
            close = candles[j]["close"]
            if fvg["type"] == "bull_fvg" and close < fvg["bottom"]:
                ifvg_type = "bear"
                break
            if fvg["type"] == "bear_fvg" and close > fvg["top"]:
                ifvg_type = "bull"
                break
        if not ifvg_type:
            continue
        zone_mid = (fvg["top"] + fvg["bottom"]) / 2
        dist     = abs(current_price - zone_mid)
        if dist > IFVG_RANGE_PTS:
            continue
        ifvgs.append({
            "top":      fvg["top"],
            "bottom":   fvg["bottom"],
            "type":     ifvg_type,
            "relation": "below" if ifvg_type == "bull" else "above",
            "target":   "🎯 Buyside above" if ifvg_type == "bull" else "🎯 Sellside below",
            "dist":     dist,
        })

    ifvgs.sort(key=lambda x: x["dist"])
    return ifvgs


# ─────────────────────────────────────────────
# BIAS LOGIC
# ─────────────────────────────────────────────

def compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low, london_close=None):
    signals, score = {}, 0

    if current_price > midnight_open:
        signals["midnight_open"] = ("+1 🟢", f"Price {current_price:.2f} > MO {midnight_open:.2f}")
        score += 1
    elif current_price < midnight_open:
        signals["midnight_open"] = ("-1 🔴", f"Price {current_price:.2f} < MO {midnight_open:.2f}")
        score -= 1
    else:
        signals["midnight_open"] = (" 0 ⚪", f"Price at MO {midnight_open:.2f}")

    if current_price > asia_high:
        signals["asia_range"] = ("+1 🟢", f"Above Asia High {asia_high:.2f}")
        score += 1
    elif current_price < asia_low:
        signals["asia_range"] = ("-1 🔴", f"Below Asia Low {asia_low:.2f}")
        score -= 1
    else:
        signals["asia_range"] = (" 0 ⚪", "Inside Asia Range")

    # London break with reversal detection
    # If London swept a level but closed back inside the Asia range = liquidity grab (opposite bias)
    if london_high > asia_high:
        if london_close is not None and london_close < asia_high:
            # Swept Asia High but closed back below = bearish liquidity grab
            signals["london_break"] = ("+1 🟢", f"London swept Asia High ({london_high:.2f}) then closed back below — bullish reversal signal")
            score += 1
        else:
            signals["london_break"] = ("+1 🟢", f"London broke above Asia High ({london_high:.2f})")
            score += 1
    elif london_low < asia_low:
        if london_close is not None and london_close > asia_low:
            # Swept Asia Low but closed back above = bullish liquidity grab
            signals["london_break"] = ("+1 🟢", f"London swept Asia Low ({london_low:.2f}) then closed back above — bullish reversal signal")
            score += 1
        else:
            signals["london_break"] = ("-1 🔴", f"London broke below Asia Low ({london_low:.2f})")
            score -= 1
    else:
        signals["london_break"] = (" 0 ⚪", "London inside Asia range")

    if score >= 2:
        overall, direction = "🟢 BULLISH", "bullish"
    elif score <= -2:
        overall, direction = "🔴 BEARISH", "bearish"
    elif score == 1:
        overall, direction = "🟡 LEANING BULLISH", "bullish"
    elif score == -1:
        overall, direction = "🟡 LEANING BEARISH", "bearish"
    else:
        overall, direction = "⚪ NEUTRAL / MIXED", "neutral"

    return {"overall": overall, "score": score, "signals": signals, "direction": direction}


# ─────────────────────────────────────────────
# MESSAGE BUILDERS
# ─────────────────────────────────────────────

def build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                          london_high, london_low, pdh, pdl, bias, ifvgs):
    date_str = datetime.now(ET).strftime("%a %b %d")
    winrate  = get_winrate_summary()

    msg  = f"📊 <b>NQ1! 15m — {date_str}</b>\n"
    msg += f"<b>{bias['overall']}</b> ({bias['score']:+d}/3)\n"
    msg += "─────────────────────\n"
    msg += f"📍 Price:  <b>{current_price:.2f}</b>\n"
    msg += f"🕛 MO:     <b>{midnight_open:.2f}</b>\n"
    if pdh and pdl:
        msg += f"📅 PDH:    <b>{pdh:.2f}</b>  PDL: <b>{pdl:.2f}</b>\n"
    msg += f"🌏 Asia:   H <b>{asia_high:.2f}</b> / L <b>{asia_low:.2f}</b>\n"
    msg += f"🌍 London: H <b>{london_high:.2f}</b> / L <b>{london_low:.2f}</b>\n"
    msg += "─────────────────────\n"
    labels = {"midnight_open": "MO", "asia_range": "Asia", "london_break": "London"}
    for key, (vote, detail) in bias["signals"].items():
        msg += f"• {vote} {labels[key]}: <i>{detail}</i>\n"
    msg += "─────────────────────\n"
    msg += f"<b>1H iFVGs ±{IFVG_RANGE_PTS}pts:</b>\n"
    if not ifvgs:
        msg += "• None nearby\n"
    else:
        for z in ifvgs:
            icon = "🟩" if z["type"] == "bull" else "🟥"
            side = "Support ↓" if z["relation"] == "below" else "Resistance ↑"
            msg += f"• {icon} {z['bottom']:.2f}–{z['top']:.2f} {side} ({z['dist']:.0f}pts) {z['target']}\n"
    msg += "─────────────────────\n"
    msg += winrate
    msg += "<i>Not financial advice.</i>"
    return msg


def build_nyo_message(current_price, bias, midnight_open,
                      asia_high, asia_low, london_high, london_low, pdh, pdl):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    direction = bias["direction"]
    mo        = midnight_open

    if direction == "bullish":
        respecting = current_price > mo
        status = "✅ Bias respected — price holding above MO" if respecting else "⚠️ Bias challenged — price below MO"
    elif direction == "bearish":
        respecting = current_price < mo
        status = "✅ Bias respected — price holding below MO" if respecting else "⚠️ Bias challenged — price above MO"
    else:
        status = "⚪ Neutral bias — no directional expectation"

    def dist_label(price, level, name):
        diff  = price - level
        arrow = "↑" if diff > 0 else "↓"
        return f"{name}: {level:.2f} ({arrow}{abs(diff):.0f}pts)"

    msg  = f"🔔 <b>NYO Update — {date_str}</b>\n"
    msg += f"<b>{bias['overall']}</b> | 📍 <b>{current_price:.2f}</b>\n"
    msg += "─────────────────────\n"
    msg += f"{status}\n"
    msg += "─────────────────────\n"
    msg += "<b>Price vs Key Levels:</b>\n"
    msg += f"• {dist_label(current_price, mo, '🕛 MO')}\n"
    if pdh and pdl:
        msg += f"• {dist_label(current_price, pdh, '📅 PDH')}\n"
        msg += f"• {dist_label(current_price, pdl, '📅 PDL')}\n"
    msg += f"• {dist_label(current_price, asia_high,   '🌏 Asia H')}\n"
    msg += f"• {dist_label(current_price, asia_low,    '🌏 Asia L')}\n"
    msg += f"• {dist_label(current_price, london_high, '🌍 London H')}\n"
    msg += f"• {dist_label(current_price, london_low,  '🌍 London L')}\n"
    msg += "─────────────────────\n"
    msg += "<i>NY Kill Zone: 7–10 AM ET</i>\n"
    msg += "<i>Not financial advice.</i>"
    return msg


def build_eod_message(bias_direction, delivered, current_price, midnight_open, winrate_data):
    date_str = datetime.now(ET).strftime("%a %b %d")
    result   = "✅ DELIVERED" if delivered else "❌ FAILED"
    wins     = winrate_data["wins"]
    losses   = winrate_data["losses"]
    neutrals = winrate_data["neutrals"]
    total    = wins + losses
    pct      = (wins / total * 100) if total > 0 else 0
    streak   = "".join(r["result"] for r in winrate_data["history"][-10:])

    msg  = f"📋 <b>EOD Score — {date_str}</b>\n"
    msg += f"Bias: <b>{bias_direction.upper()}</b> → {result}\n"
    msg += f"Close: <b>{current_price:.2f}</b>  MO: <b>{midnight_open:.2f}</b>\n"
    msg += "─────────────────────\n"
    msg += f"<b>Win Rate: {pct:.0f}%</b> ({wins}W / {losses}L / {neutrals}N)\n"
    msg += f"Last 10: {streak}\n"
    msg += "<i>Not financial advice.</i>"
    return msg


# ─────────────────────────────────────────────
# CHART SCREENSHOT
# ─────────────────────────────────────────────

def take_chart_screenshot():
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("  ✗ Playwright not installed")
        return None

    print("  → Launching headless browser...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
            ])
            context = browser.new_context(
                viewport={"width": 1600, "height": 900},
                device_scale_factor=2,
            )
            page = context.new_page()

            # Log into TradingView if credentials provided
            if TV_USERNAME and TV_PASSWORD:
                print("  → Logging into TradingView...")
                page.goto("https://www.tradingview.com/accounts/signin/",
                          wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)

                for sel in ["[data-name='accept-cookies']", "button:has-text('Got it')", "button:has-text('Accept all')"]:
                    try:
                        btn = page.query_selector(sel)
                        if btn:
                            btn.click()
                            page.wait_for_timeout(500)
                    except Exception:
                        pass

                try:
                    email_btn = page.query_selector("button[name='Email']") or page.query_selector("text=Email")
                    if email_btn:
                        email_btn.click()
                        page.wait_for_timeout(1000)
                except Exception:
                    pass

                try:
                    page.fill("input[name='username']", TV_USERNAME)
                    page.wait_for_timeout(500)
                    page.fill("input[name='password']", TV_PASSWORD)
                    page.wait_for_timeout(500)
                    page.keyboard.press("Enter")
                    page.wait_for_timeout(4000)
                    print("  → Login submitted.")
                except Exception as e:
                    print(f"  ⚠ Login failed: {e}")

            # Navigate to chart
            print("  → Loading chart...")
            page.goto(TV_CHART_URL, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_selector("canvas", timeout=20000)
                page.wait_for_timeout(6000)
            except PWTimeout:
                pass

            # Dismiss popups
            for sel in ["[data-name='accept-cookies']", "button:has-text('Got it')", "button:has-text('Accept')"]:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass

            # Screenshot chart area
            try:
                chart = page.query_selector(".chart-container") or page.query_selector("canvas")
                if chart:
                    chart.screenshot(path=str(SCREENSHOT_PATH))
                else:
                    page.screenshot(path=str(SCREENSHOT_PATH))
            except Exception:
                page.screenshot(path=str(SCREENSHOT_PATH))

            browser.close()
            print("  → Screenshot saved.")
            return SCREENSHOT_PATH

    except Exception as e:
        print(f"  ✗ Screenshot failed: {e}")
        return None


def compress_screenshot(image_path):
    try:
        from PIL import Image
        compressed_path = Path("/tmp/nq_chart_compressed.jpg")
        img = Image.open(image_path)
        max_width = 1280
        if img.width > max_width:
            ratio = max_width / img.width
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        img.convert("RGB").save(compressed_path, "JPEG", quality=85, optimize=True)
        print(f"  → Compressed to {compressed_path.stat().st_size // 1024}KB")
        return compressed_path
    except Exception as e:
        print(f"  ⚠ Compression failed: {e}")
        return image_path


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def send_telegram_photo(image_path, caption):
    compressed = compress_screenshot(image_path)
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    for chat_id in [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]:
        if not chat_id:
            continue
        with open(compressed, "rb") as img:
            requests.post(url, data={
                "chat_id":    chat_id,
                "caption":    caption,
                "parse_mode": "HTML",
            }, files={"photo": img}, timeout=30).raise_for_status()
    print(f"[{datetime.now(ET).strftime('%H:%M:%S ET')}] Photo sent to all chats.")


def send_telegram_text(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chat_id in [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]:
        if not chat_id:
            continue
        requests.post(url, json={
            "chat_id":    chat_id,
            "text":       message,
            "parse_mode": "HTML",
        }, timeout=10).raise_for_status()
    print(f"[{datetime.now(ET).strftime('%H:%M:%S ET')}] Text sent to all chats.")


# ─────────────────────────────────────────────
# JOBS
# ─────────────────────────────────────────────

def run_morning_bias():
    print(f"\n[{datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}] Running morning bias job...")
    windows = get_session_windows()

    try:
        midnight_open           = get_midnight_open(windows["midnight_open_utc"])
        asia_high, asia_low, _          = get_session_hl(windows["asia_start_utc"], windows["asia_end_utc"])
        london_high, london_low, london_close = get_session_hl(windows["london_start_utc"], windows["london_end_utc"])
        pdh, pdl                = get_previous_day_hl()
        current_price           = get_current_price() or midnight_open

        # Always take screenshot first
        screenshot = take_chart_screenshot()

        if not all([midnight_open, asia_high, asia_low, london_high, london_low, current_price]):
            caption = "⚠️ <b>NQ Bias Bot</b>: Missing session data — market may be closed."
            if screenshot and screenshot.exists():
                send_telegram_photo(screenshot, caption)
            else:
                send_telegram_text(caption)
            return

        bias  = compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low, london_close)
        ifvgs = detect_ifvgs(current_price)

        # Store for NYO and EOD jobs
        today_state.update({
            "bias":          bias["direction"],
            "score":         bias["score"],
            "midnight_open": midnight_open,
            "asia_high":     asia_high,
            "asia_low":      asia_low,
            "london_high":   london_high,
            "london_low":    london_low,
            "pdh":           pdh,
            "pdl":           pdl,
            "date":          datetime.now(ET).strftime("%Y-%m-%d"),
        })

        caption = build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                                        london_high, london_low, pdh, pdl, bias, ifvgs)

        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, caption)
        else:
            caption += "\n\n⚠️ <i>Chart screenshot unavailable.</i>"
            send_telegram_text(caption)

    except Exception as e:
        err = f"⚠️ <b>Morning Bias Error:</b> {e}"
        print(err)
        try:
            send_telegram_text(err)
        except Exception:
            pass


def run_nyo_update():
    print(f"\n[{datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}] Running NYO update...")

    try:
        current_price = get_current_price()
        if not current_price or not today_state["midnight_open"]:
            send_telegram_text("⚠️ <b>NYO Update</b>: No data available.")
            return

        bias = {
            "overall":   "🟢 BULLISH" if today_state["bias"] == "bullish" else "🔴 BEARISH" if today_state["bias"] == "bearish" else "⚪ NEUTRAL",
            "direction": today_state["bias"],
            "score":     today_state["score"],
        }

        msg = build_nyo_message(
            current_price, bias,
            today_state["midnight_open"],
            today_state["asia_high"],   today_state["asia_low"],
            today_state["london_high"], today_state["london_low"],
            today_state["pdh"],         today_state["pdl"],
        )
        screenshot = take_chart_screenshot()
        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, msg)
        else:
            send_telegram_text(msg)

    except Exception as e:
        err = f"⚠️ <b>NYO Update Error:</b> {e}"
        print(err)
        try:
            send_telegram_text(err)
        except Exception:
            pass


def run_eod_score():
    print(f"\n[{datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}] Running EOD score...")

    try:
        current_price = get_current_price()
        mo            = today_state["midnight_open"]
        direction     = today_state["bias"]

        if not current_price or not mo or not direction:
            send_telegram_text("⚠️ <b>EOD Score</b>: No bias data for today.")
            return

        if direction == "bullish":
            delivered = current_price > mo
        elif direction == "bearish":
            delivered = current_price < mo
        else:
            delivered = False

        winrate_data = record_result(direction, delivered)
        msg = build_eod_message(direction, delivered, current_price, mo, winrate_data)
        send_telegram_text(msg)

    except Exception as e:
        err = f"⚠️ <b>EOD Score Error:</b> {e}"
        print(err)
        try:
            send_telegram_text(err)
        except Exception:
            pass


# ─────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────

def main():
    print("Smokey Bias Bot — scheduled daily:")
    print("  12:00 UTC (08:00 ET) — Morning bias + chart")
    print("  13:00 UTC (09:00 ET) — NYO update")
    print("  20:00 UTC (16:00 ET) — EOD score + win rate\n")

    schedule.every().day.at("12:00").do(run_morning_bias)
    schedule.every().day.at("13:00").do(run_nyo_update)
    schedule.every().day.at("20:00").do(run_eod_score)

    # ── Uncomment to test immediately ──
    # run_morning_bias()
    # run_nyo_update()
    # run_eod_score()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
