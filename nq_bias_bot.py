"""
NQ1! Daily Bias Bot — v4
Uses Yahoo Finance (yfinance) — no API key needed.
Sends a Telegram photo at 8:00 AM ET with:
  - 15m NQ1! TradingView screenshot (dark theme)
  - Bias caption: midnight open, Asia H/L, London H/L, 1H iFVGs
"""

import os
import time
import requests
import schedule
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# ─────────────────────────────────────────────
# CONFIG — paste your values here
# ─────────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8757455017:AAFuZgFN5ml3xNCVVE3ww8DyzWThtQrTMos")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "5048230949")

# Yahoo Finance symbol for NQ futures (continuous contract)
SYMBOL          = "NQ=F"
IFVG_RANGE_PTS  = 100
IFVG_LOOKBACK_H = 48

ET  = pytz.timezone("America/New_York")
UTC = pytz.utc

TRADINGVIEW_URL = (
    "https://www.tradingview.com/chart/?symbol=CME_MINI%3ANQ1%21"
    "&interval=15"
    "&theme=dark"
    "&style=1"
)
SCREENSHOT_PATH = Path("/tmp/nq_chart.png")


# ─────────────────────────────────────────────
# DATA FETCHING — Yahoo Finance
# ─────────────────────────────────────────────

def fetch_candles_yf(start_utc: datetime, end_utc: datetime, interval: str = "1m") -> list:
    """
    Fetch OHLC candles from Yahoo Finance.
    interval options: "1m", "2m", "5m", "15m", "30m", "60m", "1d"
    Note: 1m data only available for last 7 days.
          60m data available for last 730 days.
    Returns list of dicts: {open, high, low, close, datetime}
    """
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(start=start_utc, end=end_utc, interval=interval)
    if df.empty:
        return []
    df = df.reset_index()
    candles = []
    for _, row in df.iterrows():
        candles.append({
            "open":     float(row["Open"]),
            "high":     float(row["High"]),
            "low":      float(row["Low"]),
            "close":    float(row["Close"]),
            "datetime": row["Datetime"] if "Datetime" in row else row.get("Date"),
        })
    return candles


def get_session_windows() -> dict:
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


def get_midnight_open(midnight_utc: datetime) -> float | None:
    """Get the open price at midnight ET."""
    end = midnight_utc + timedelta(minutes=5)
    candles = fetch_candles_yf(midnight_utc, end, interval="1m")
    return candles[0]["open"] if candles else None


def get_session_hl(start_utc: datetime, end_utc: datetime) -> tuple:
    """Return (high, low) over a session window using 1m candles."""
    candles = fetch_candles_yf(start_utc, end_utc, interval="1m")
    if not candles:
        return None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles)


def get_current_price() -> float | None:
    """Get the most recent close price."""
    now_utc = datetime.now(UTC)
    candles = fetch_candles_yf(now_utc - timedelta(minutes=10), now_utc, interval="1m")
    return candles[-1]["close"] if candles else None


# ─────────────────────────────────────────────
# iFVG DETECTION (1H candles)
# ─────────────────────────────────────────────

def detect_ifvgs(current_price: float) -> list:
    now_utc   = datetime.now(UTC)
    start_utc = now_utc - timedelta(hours=IFVG_LOOKBACK_H)
    candles   = fetch_candles_yf(start_utc, now_utc, interval="60m")

    if len(candles) < 3:
        return []

    # Step 1: find all FVGs
    fvg_zones = []
    for i in range(2, len(candles)):
        c0, c2 = candles[i - 2], candles[i]
        if c0["high"] < c2["low"]:
            fvg_zones.append({"top": c2["low"], "bottom": c0["high"],
                               "type": "bull_fvg", "formed_at": i})
        if c0["low"] > c2["high"]:
            fvg_zones.append({"top": c0["low"], "bottom": c2["high"],
                               "type": "bear_fvg", "formed_at": i})

    # Step 2: check for inversion
    ifvgs = []
    for fvg in fvg_zones:
        ifvg_type = None
        for j in range(fvg["formed_at"] + 1, len(candles)):
            close = candles[j]["close"]
            if fvg["type"] == "bull_fvg" and close < fvg["bottom"]:
                ifvg_type = "bear"; break
            if fvg["type"] == "bear_fvg" and close > fvg["top"]:
                ifvg_type = "bull"; break
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
            "target":   "🎯 Target: Buyside above" if ifvg_type == "bull" else "🎯 Target: Sellside below",
            "dist":     dist,
        })

    ifvgs.sort(key=lambda x: x["dist"])
    return ifvgs


# ─────────────────────────────────────────────
# BIAS LOGIC
# ─────────────────────────────────────────────

def compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low) -> dict:
    signals, score = {}, 0

    if current_price > midnight_open:
        signals["midnight_open"] = ("+1 🟢", f"Price {current_price:.2f} > MO {midnight_open:.2f}"); score += 1
    elif current_price < midnight_open:
        signals["midnight_open"] = ("-1 🔴", f"Price {current_price:.2f} < MO {midnight_open:.2f}"); score -= 1
    else:
        signals["midnight_open"] = (" 0 ⚪", f"Price at MO {midnight_open:.2f}")

    if current_price > asia_high:
        signals["asia_range"] = ("+1 🟢", f"Above Asia High {asia_high:.2f}"); score += 1
    elif current_price < asia_low:
        signals["asia_range"] = ("-1 🔴", f"Below Asia Low {asia_low:.2f}"); score -= 1
    else:
        signals["asia_range"] = (" 0 ⚪", "Inside Asia Range")

    if london_high > asia_high:
        signals["london_break"] = ("+1 🟢", f"London swept Asia High ({london_high:.2f})"); score += 1
    elif london_low < asia_low:
        signals["london_break"] = ("-1 🔴", f"London swept Asia Low ({london_low:.2f})"); score -= 1
    else:
        signals["london_break"] = (" 0 ⚪", "London inside Asia range")

    if   score >= 2:  overall = "🟢 BULLISH"
    elif score <= -2: overall = "🔴 BEARISH"
    elif score == 1:  overall = "🟡 LEANING BULLISH"
    elif score == -1: overall = "🟡 LEANING BEARISH"
    else:             overall = "⚪ NEUTRAL / MIXED"

    return {"overall": overall, "score": score, "signals": signals}


# ─────────────────────────────────────────────
# MESSAGE BUILDER
# ─────────────────────────────────────────────

def build_caption(current_price, midnight_open, asia_high, asia_low,
                  london_high, london_low, bias, ifvgs) -> str:
    date_str = datetime.now(ET).strftime("%a %b %d")

    msg  = f"📊 <b>NQ1! 15m — {date_str}</b>\n"
    msg += f"<b>{bias['overall']}</b> ({bias['score']:+d}/3)\n"
    msg += "─────────────────────\n"
    msg += f"📍 <b>{current_price:.2f}</b>   🕛 MO: <b>{midnight_open:.2f}</b>\n"
    msg += f"🌏 Asia  H <b>{asia_high:.2f}</b> / L <b>{asia_low:.2f}</b>\n"
    msg += f"🌍 London H <b>{london_high:.2f}</b> / L <b>{london_low:.2f}</b>\n"
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

    msg += "<i>Not financial advice.</i>"
    return msg


# ─────────────────────────────────────────────
# CHART SCREENSHOT (Playwright)
# ─────────────────────────────────────────────

def take_chart_screenshot() -> Path | None:
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("Playwright not installed. Run: pip install playwright && playwright install chromium")
        return None

    print("  → Launching headless browser...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
            ])
            page = browser.new_context(
                viewport={"width": 1600, "height": 900},
                device_scale_factor=2,
            ).new_page()

            page.goto(TRADINGVIEW_URL, wait_until="domcontentloaded", timeout=30000)
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

            page.screenshot(path=str(SCREENSHOT_PATH))
            browser.close()
            print(f"  → Screenshot saved.")
            return SCREENSHOT_PATH
    except Exception as e:
        print(f"  ✗ Screenshot failed: {e}")
        return None


# ─────────────────────────────────────────────
# TELEGRAM
# ─────────────────────────────────────────────

def send_telegram_photo(image_path: Path, caption: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
    with open(image_path, "rb") as img:
        requests.post(url, data={
            "chat_id": TELEGRAM_CHAT_ID,
            "caption": caption,
            "parse_mode": "HTML",
        }, files={"photo": img}, timeout=30).raise_for_status()
    print(f"[{datetime.now(ET).strftime('%H:%M:%S ET')}] Photo sent.")


def send_telegram_text(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }, timeout=10).raise_for_status()
    print(f"[{datetime.now(ET).strftime('%H:%M:%S ET')}] Text sent.")


# ─────────────────────────────────────────────
# MAIN JOB
# ─────────────────────────────────────────────

def run_bias_job():
    print(f"\n[{datetime.now(ET).strftime('%Y-%m-%d %H:%M ET')}] Running NQ bias job...")
    windows = get_session_windows()

    try:
        print("  → Fetching market data from Yahoo Finance...")
        midnight_open           = get_midnight_open(windows["midnight_open_utc"])
        asia_high, asia_low     = get_session_hl(windows["asia_start_utc"], windows["asia_end_utc"])
        london_high, london_low = get_session_hl(windows["london_start_utc"], windows["london_end_utc"])
        current_price           = get_current_price() or midnight_open

        if not all([midnight_open, asia_high, asia_low, london_high, london_low, current_price]):
            send_telegram_text("⚠️ <b>NQ Bias Bot</b>: Missing session data — market may be closed.")
            return

        bias    = compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low)
        ifvgs   = detect_ifvgs(current_price)
        caption = build_caption(current_price, midnight_open, asia_high, asia_low,
                                london_high, london_low, bias, ifvgs)

        screenshot = take_chart_screenshot()

        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, caption)
        else:
            caption += "\n\n⚠️ <i>Chart screenshot unavailable.</i>"
            send_telegram_text(caption)

    except Exception as e:
        err = f"⚠️ <b>NQ Bias Bot Error:</b> {e}"
        print(err)
        try:
            send_telegram_text(err)
        except Exception:
            pass


# ─────────────────────────────────────────────
# SCHEDULER
# ─────────────────────────────────────────────

def main():
    print("NQ1! Bias Bot v4 — scheduled 08:00 AM ET daily.")

    schedule.every().day.at("08:00").do(run_bias_job)

    # ── Uncomment to test immediately ──
    #run_bias_job()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
