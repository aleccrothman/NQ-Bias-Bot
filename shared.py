"""
shared.py - Smokey Bias Bot shared code
All config, data fetching, message building, and sending functions.
"""

import os
import json
import time
import requests
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
import pytz

# ── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_BOT_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN",  "8757455017:AAFuZgFN5ml3xNCVVE3ww8DyzWThtQrTMos")
TELEGRAM_CHAT_ID      = os.getenv("TELEGRAM_CHAT_ID",    "5048230949")
TELEGRAM_CHANNEL_ID   = os.getenv("TELEGRAM_CHANNEL_ID", "-1003726448503")
TELEGRAM_FREE_CHANNEL = os.getenv("TELEGRAM_FREE_CHANNEL", "")

TV_USERNAME  = os.getenv("TV_USERNAME", "")
TV_PASSWORD  = os.getenv("TV_PASSWORD", "")
TV_CHART_URL = "https://www.tradingview.com/chart/hcbriKzA/"

DISCORD_WEBHOOK_NEWS = os.getenv("DISCORD_WEBHOOK_NEWS", "")
DISCORD_WEBHOOK_BIAS = os.getenv("DISCORD_WEBHOOK_BIAS", "")
DISCORD_WEBHOOK_NYO  = os.getenv("DISCORD_WEBHOOK_NYO",  "")
DISCORD_WEBHOOK_EOD  = os.getenv("DISCORD_WEBHOOK_EOD",  "")

SYMBOL          = "NQ=F"
IFVG_RANGE_PTS  = 100
IFVG_LOOKBACK_H = 48

ET  = pytz.timezone("America/New_York")
UTC = pytz.utc

SCREENSHOT_PATH  = Path("/tmp/nq_chart.png")
WINRATE_FILE     = Path("/tmp/nq_winrate.json")
TODAY_STATE_FILE = Path("/tmp/today_state.json")
LEVELS_FILE      = Path("/tmp/tv_levels.json")

# ── HELPERS ───────────────────────────────────────────────────────────────────
def fmt(val, decimals=2):
    if val is None:
        return "N/A"
    try:
        return str(round(float(val), decimals))
    except Exception:
        return "N/A"

# ── STATE ─────────────────────────────────────────────────────────────────────
today_state = {
    "bias": None, "score": 0,
    "midnight_open": None,
    "asia_high": None, "asia_low": None,
    "london_high": None, "london_low": None,
    "pdh": None, "pdl": None, "date": None,
}

def save_today_state():
    try:
        TODAY_STATE_FILE.write_text(json.dumps(today_state))
    except Exception as e:
        print("  -> Failed to save today_state: " + str(e))

def load_today_state():
    try:
        if not TODAY_STATE_FILE.exists():
            return
        data = json.loads(TODAY_STATE_FILE.read_text())
        today = datetime.now(ET).strftime("%Y-%m-%d")
        if data.get("date") == today:
            today_state.update(data)
            print("  -> Loaded today_state: " + str(data.get("bias")) + " bias")
        else:
            print("  -> today_state is from a different day, ignoring")
    except Exception as e:
        print("  -> Failed to load today_state: " + str(e))

def load_tv_levels():
    if not LEVELS_FILE.exists():
        return {}
    try:
        data = json.loads(LEVELS_FILE.read_text())
        today = datetime.now(ET).strftime("%Y-%m-%d")
        return data.get(today, {})
    except Exception:
        return {}

# ── WIN RATE ──────────────────────────────────────────────────────────────────
def load_winrate():
    if WINRATE_FILE.exists():
        try:
            return json.loads(WINRATE_FILE.read_text())
        except Exception:
            pass
    return {"wins": 0, "losses": 0, "neutrals": 0, "history": []}

def save_winrate(data):
    WINRATE_FILE.write_text(json.dumps(data, indent=2))

def record_result_v2(bias_direction, result_type):
    data = load_winrate()
    date_str = datetime.now(ET).strftime("%Y-%m-%d")
    if result_type == "win":
        data["wins"] += 1
        result = "W"
    elif result_type == "failed":
        data["losses"] += 1
        result = "L"
    else:
        data["neutrals"] += 1
        result = "C"
    data["history"].append({"date": date_str, "bias": bias_direction, "result_type": result_type, "result": result})
    data["history"] = data["history"][-30:]
    save_winrate(data)
    return data

# ── DATA FETCHING ─────────────────────────────────────────────────────────────
def fetch_candles_yf(start_utc, end_utc, interval="1m"):
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(start=start_utc, end=end_utc, interval=interval)
    if df.empty:
        return []
    df = df.reset_index()
    return [{"open": float(r["Open"]), "high": float(r["High"]),
              "low": float(r["Low"]), "close": float(r["Close"])} for _, r in df.iterrows()]

def get_current_price():
    """Get most recent NQ price, looking back up to 4 hours to handle after-hours gaps."""
    now_utc = datetime.now(UTC)
    for minutes in [10, 30, 60, 120, 240]:
        candles = fetch_candles_yf(now_utc - timedelta(minutes=minutes), now_utc, "1m")
        if candles:
            print("  -> Price found looking back " + str(minutes) + " mins: " + str(candles[-1]["close"]))
            return candles[-1]["close"]
    candles = fetch_candles_yf(now_utc - timedelta(hours=6), now_utc, "5m")
    if candles:
        return candles[-1]["close"]
    print("  -> Could not fetch current price")
    return None

def get_session_windows():
    now_et = datetime.now(ET)
    today_et = now_et.date()
    midnight = ET.localize(datetime(today_et.year, today_et.month, today_et.day, 0, 0))
    return {
        "midnight_open_utc": midnight.astimezone(UTC),
        "asia_start_utc": (midnight - timedelta(hours=6)).astimezone(UTC),
        "asia_end_utc": midnight.astimezone(UTC),
        "london_start_utc": midnight.astimezone(UTC),
        "london_end_utc": (midnight + timedelta(hours=5)).astimezone(UTC),
    }

def get_midnight_open(midnight_utc):
    for interval, hours in [("1m", 0.5), ("1m", 1), ("5m", 1), ("5m", 2)]:
        candles = fetch_candles_yf(midnight_utc, midnight_utc + timedelta(hours=hours), interval)
        if candles:
            return candles[0]["open"]
    return None

def get_session_hl(start_utc, end_utc):
    candles = fetch_candles_yf(start_utc, end_utc, "1m")
    if not candles:
        return None, None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles), candles[-1]["close"]

def get_previous_day_hl():
    now_et = datetime.now(ET)
    today_et = now_et.date()
    midnight = ET.localize(datetime(today_et.year, today_et.month, today_et.day, 0, 0))
    prev_open  = (midnight - timedelta(hours=30)).astimezone(UTC)
    prev_close = (midnight - timedelta(hours=1)).astimezone(UTC)
    candles = fetch_candles_yf(prev_open, prev_close, "60m")
    if not candles:
        return None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles)

def get_vix():
    try:
        ticker = yf.Ticker("^VIX")
        for period in ["1d", "2d", "5d"]:
            df = ticker.history(period=period, interval="1h")
            if not df.empty:
                return round(float(df["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None

def build_vix_line(vix):
    if vix is None:
        return ""
    if vix >= 30:
        return "\U0001f6a8 VIX **" + str(vix) + "** \u2014 High fear, expect wide ranges & whips. Size down."
    elif vix >= 20:
        return "\u26a0\ufe0f VIX **" + str(vix) + "** \u2014 Elevated volatility. Watch for news reactions."
    elif vix >= 15:
        return "\U0001f7e1 VIX **" + str(vix) + "** \u2014 Moderate vol. Normal conditions."
    else:
        return "\U0001f7e2 VIX **" + str(vix) + "** \u2014 Low vol. Tight ranges, grind likely."

# ── iFVG DETECTION ────────────────────────────────────────────────────────────
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
            fvg_zones.append({"top": c2["low"], "bottom": c0["high"], "type": "bull_fvg", "formed_at": i})
        if c0["low"] > c2["high"]:
            fvg_zones.append({"top": c0["low"], "bottom": c2["high"], "type": "bear_fvg", "formed_at": i})
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
        dist = abs(current_price - zone_mid)
        if dist > IFVG_RANGE_PTS:
            continue
        ifvgs.append({
            "top": fvg["top"], "bottom": fvg["bottom"], "type": ifvg_type,
            "relation": "below" if ifvg_type == "bull" else "above",
            "target": "Buyside above" if ifvg_type == "bull" else "Sellside below",
            "dist": dist,
        })
    ifvgs.sort(key=lambda x: x["dist"])
    return ifvgs

# ── BIAS LOGIC ────────────────────────────────────────────────────────────────
def compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low, london_close=None):
    signals, score = {}, 0

    if current_price > midnight_open:
        signals["midnight_open"] = ("+1", "BULL", "Price " + fmt(current_price) + " > MO " + fmt(midnight_open))
        score += 1
    elif current_price < midnight_open:
        signals["midnight_open"] = ("-1", "BEAR", "Price " + fmt(current_price) + " < MO " + fmt(midnight_open))
        score -= 1
    else:
        signals["midnight_open"] = (" 0", "NEUT", "Price at MO " + fmt(midnight_open))

    if current_price > asia_high:
        signals["asia_range"] = ("+1", "BULL", "Above Asia High " + fmt(asia_high))
        score += 1
    elif current_price < asia_low:
        signals["asia_range"] = ("-1", "BEAR", "Below Asia Low " + fmt(asia_low))
        score -= 1
    else:
        signals["asia_range"] = (" 0", "NEUT", "Inside Asia Range")

    if london_high > asia_high:
        if london_close is not None and london_close < asia_high:
            signals["london_break"] = ("-1", "BEAR", "London swept Asia High (" + fmt(london_high) + ") then closed back below - bearish trap")
            score -= 1
        else:
            signals["london_break"] = ("+1", "BULL", "London broke above Asia High (" + fmt(london_high) + ")")
            score += 1
    elif london_low < asia_low:
        if london_close is not None and london_close > asia_low:
            signals["london_break"] = ("+1", "BULL", "London swept Asia Low (" + fmt(london_low) + ") then closed back above - bullish reversal")
            score += 1
        else:
            signals["london_break"] = ("-1", "BEAR", "London broke below Asia Low (" + fmt(london_low) + ")")
            score -= 1
    else:
        signals["london_break"] = (" 0", "NEUT", "London inside Asia range")

    if score >= 2:
        overall, direction = "BULLISH", "bullish"
    elif score <= -2:
        overall, direction = "BEARISH", "bearish"
    elif score == 1:
        overall, direction = "LEANING BULLISH", "bullish"
    elif score == -1:
        overall, direction = "LEANING BEARISH", "bearish"
    else:
        overall, direction = "NEUTRAL / MIXED", "neutral"

    abs_score = abs(score)
    if abs_score == 3:
        grade = "A"
    elif abs_score == 2:
        grade = "B"
    elif abs_score == 1:
        grade = "C"
    else:
        grade = "D"

    return {"overall": overall, "score": score, "signals": signals, "direction": direction, "grade": grade}

# ── FOREX FACTORY ─────────────────────────────────────────────────────────────
def get_forex_factory_news(days=3):
    try:
        import xml.etree.ElementTree as ET_xml
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        headers = {"User-Agent": "Mozilla/5.0"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        root = ET_xml.fromstring(resp.content)
        today_et = datetime.now(ET).date()
        cutoff   = today_et + timedelta(days=days)
        all_events = {}

        for event in root.findall("event"):
            if event.findtext("country", "") != "USD":
                continue
            impact = event.findtext("impact", "").lower()
            if impact not in ["high", "medium"]:
                continue
            impact_key   = "red" if impact == "high" else "orange"
            title        = event.findtext("title", "Unknown")
            date_str_raw = event.findtext("date", "")
            time_str_raw = event.findtext("time", "") or ""
            forecast     = event.findtext("forecast", "-") or "-"
            previous     = event.findtext("previous", "-") or "-"

            try:
                event_date = datetime.strptime(date_str_raw, "%m-%d-%Y").date()
            except Exception:
                try:
                    event_date = datetime.strptime(date_str_raw, "%Y-%m-%d").date()
                except Exception:
                    continue

            if event_date < today_et or event_date > cutoff:
                continue

            display_time     = "All Day"
            during_kill_zone = False
            et_hour          = -1
            if time_str_raw and time_str_raw.strip():
                try:
                    t_clean = time_str_raw.strip().upper()
                    for fmt_str in ["%I:%M%p", "%I:%M %p", "%H:%M"]:
                        try:
                            parsed_gmt  = datetime.strptime(t_clean, fmt_str)
                            now_utc_dt  = datetime.now(pytz.utc)
                            utc_offset  = int(now_utc_dt.astimezone(ET).utcoffset().total_seconds() / 3600)
                            et_hour     = (parsed_gmt.hour + utc_offset) % 24
                            et_dt       = parsed_gmt.replace(hour=et_hour, minute=parsed_gmt.minute)
                            display_time = et_dt.strftime("%-I:%M %p") + " ET"
                            if event_date == today_et and 7 <= et_hour < 10:
                                during_kill_zone = True
                            break
                        except Exception:
                            continue
                except Exception:
                    display_time = time_str_raw

            date_key = event_date.strftime("%a %b %d")
            if date_key not in all_events:
                all_events[date_key] = []
            all_events[date_key].append({
                "time": display_time, "event": title, "impact": impact_key,
                "forecast": forecast, "previous": previous,
                "during_kill_zone": during_kill_zone, "date": event_date,
                "sort_hour": et_hour if display_time != "All Day" else -1,
            })

        for date_key in all_events:
            all_events[date_key].sort(key=lambda x: x["sort_hour"])
        sorted_events = dict(sorted(all_events.items(), key=lambda x: x[1][0]["date"] if x[1] else today_et))
        return sorted_events
    except Exception as e:
        print("Forex Factory fetch failed: " + str(e))
        return {}

# ── CHART SCREENSHOT ──────────────────────────────────────────────────────────
def take_chart_screenshot():
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("Playwright not installed")
        return None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
            ])
            context = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
            page    = context.new_page()

            if TV_USERNAME and TV_PASSWORD:
                page.goto("https://www.tradingview.com/accounts/signin/", wait_until="domcontentloaded", timeout=30000)
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
                except Exception as e:
                    print("Login failed: " + str(e))

            page.goto(TV_CHART_URL, wait_until="domcontentloaded", timeout=30000)
            try:
                page.wait_for_selector("canvas", timeout=20000)
                page.wait_for_timeout(6000)
            except PWTimeout:
                pass
            for sel in ["[data-name='accept-cookies']", "button:has-text('Got it')", "button:has-text('Accept')"]:
                try:
                    btn = page.query_selector(sel)
                    if btn:
                        btn.click()
                        page.wait_for_timeout(500)
                except Exception:
                    pass
            try:
                chart = page.query_selector(".chart-container") or page.query_selector("canvas")
                if chart:
                    chart.screenshot(path=str(SCREENSHOT_PATH))
                else:
                    page.screenshot(path=str(SCREENSHOT_PATH))
            except Exception:
                page.screenshot(path=str(SCREENSHOT_PATH))
            browser.close()
            print("  -> Screenshot saved.")
            return SCREENSHOT_PATH
    except Exception as e:
        print("Screenshot failed: " + str(e))
        return None

def compress_screenshot(image_path):
    try:
        from PIL import Image, ImageDraw, ImageFont
        compressed_path = Path("/tmp/nq_chart_compressed.jpg")
        img = Image.open(image_path).convert("RGB")
        max_width = 1280
        if img.width > max_width:
            ratio = max_width / img.width
            img   = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        try:
            draw      = ImageDraw.Draw(img)
            watermark = "Smokey Bias | t.me/SmokeyNQBot"
            font_size = max(16, img.width // 50)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()
            bbox   = draw.textbbox((0, 0), watermark, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
            x = img.width  - text_w - 15
            y = img.height - text_h - 15
            draw.text((x+2, y+2), watermark, font=font, fill=(0, 0, 0, 180))
            draw.text((x, y),     watermark, font=font, fill=(255, 255, 255, 230))
        except Exception as e:
            print("  -> Watermark failed: " + str(e))
        img.save(compressed_path, "JPEG", quality=85, optimize=True)
        return compressed_path
    except Exception as e:
        print("Compression failed: " + str(e))
        return image_path

# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_telegram_text(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    for chat_id in [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]:
        if not chat_id:
            continue
        try:
            requests.post(url, json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}, timeout=10).raise_for_status()
        except Exception as e:
            print("  -> Text send error: " + str(e))
    print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Telegram text sent.")

def send_telegram_photo(image_path, caption):
    if not image_path or not image_path.exists() or image_path.stat().st_size < 1000:
        send_telegram_text(caption)
        return
    compressed  = compress_screenshot(image_path)
    safe_caption = caption[:1020] + "..." if len(caption) > 1024 else caption
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
    for chat_id in [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]:
        if not chat_id:
            continue
        try:
            with open(compressed, "rb") as img:
                resp = requests.post(url, data={"chat_id": chat_id, "caption": safe_caption, "parse_mode": "HTML"},
                                     files={"photo": img}, timeout=30)
                if not resp.ok:
                    send_telegram_text(safe_caption)
        except Exception as e:
            print("  -> Photo send error: " + str(e))
            send_telegram_text(safe_caption)
    print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Telegram photo sent.")

def send_teaser(bias_overall, grade, date_str):
    if not TELEGRAM_FREE_CHANNEL:
        return
    msg  = "\U0001f4ca <b>NQ1! Daily Bias | " + date_str + "</b>\n"
    msg += "--------------------\n"
    msg += "<b>" + bias_overall + "</b> | Grade: <b>" + grade + "</b>\n"
    msg += "--------------------\n"
    msg += "Full analysis + chart in premium channel\nJoin: @SmokeyNQBot\n"
    msg += "<i>Not financial advice.</i>"
    try:
        requests.post("https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage",
                      json={"chat_id": TELEGRAM_FREE_CHANNEL, "text": msg, "parse_mode": "HTML"}, timeout=10)
    except Exception as e:
        print("  -> Teaser send error: " + str(e))

# ── DISCORD ───────────────────────────────────────────────────────────────────
def send_discord_embed(embed, image_path=None, webhook=None):
    url = webhook or DISCORD_WEBHOOK_BIAS
    if not url:
        return
    try:
        if image_path and Path(image_path).exists() and Path(image_path).stat().st_size > 1000:
            compressed = compress_screenshot(Path(image_path))
            embed["image"] = {"url": "attachment://chart.jpg"}
            with open(compressed, "rb") as img:
                requests.post(url, data={"payload_json": json.dumps({"embeds": [embed]})},
                              files={"file": ("chart.jpg", img, "image/jpeg")}, timeout=30)
        else:
            requests.post(url, json={"embeds": [embed]}, timeout=10)
        print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Discord embed sent.")
    except Exception as e:
        print("  -> Discord embed error: " + str(e))

# ── MESSAGE BUILDERS ──────────────────────────────────────────────────────────
def build_news_message(all_events):
    today_et  = datetime.now(ET).date()
    today_str = today_et.strftime("%a %b %d")
    msg  = "--------------------\n"
    msg += "\U0001f4f0 <b>Macro Calendar | " + today_str + "</b>\n"
    msg += "--------------------\n"
    if not all_events:
        msg += "\u2705 No high/medium impact USD news today\n"
        msg += "--------------------\n<i>Not financial advice.</i>"
        return msg
    has_kill_zone = False
    for date_key, events in all_events.items():
        is_today = date_key == today_str
        msg += "\U0001f5d3 <b>TODAY</b>\n" if is_today else "\U0001f5d3 <b>" + date_key + "</b>\n"
        for e in events:
            impact_icon = "\U0001f534" if e["impact"] == "red" else "\U0001f7e0"
            kz = " \u26a1<b>KILL ZONE</b>" if e["during_kill_zone"] else ""
            if e["during_kill_zone"]:
                has_kill_zone = True
            msg += impact_icon + " <b>" + e["time"] + "</b>  " + e["event"] + kz + "\n"
            if is_today and (e["forecast"] != "-" or e["previous"] != "-"):
                msg += "   \U0001f4ca F: " + e["forecast"] + "  P: " + e["previous"] + "\n"
        msg += "\n"
    msg += "--------------------\n"
    if has_kill_zone:
        msg += "\u26a0\ufe0f <b>News during NY Kill Zone - trade carefully</b>\n"
    msg += "<i>Not financial advice.</i>"
    return msg

def build_discord_news(all_events):
    today_et  = datetime.now(ET).date()
    today_str = today_et.strftime("%a %b %d")
    if not all_events:
        return {"title": "\U0001f4f0  Macro Calendar  |  " + today_str,
                "description": "\u2705 No high/medium impact USD news today",
                "color": 0x22c55e,
                "footer": {"text": "Smokey Bias Bot  \u2022  Not financial advice."},
                "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    fields = []
    has_kill_zone = False
    for date_key, events in all_events.items():
        is_today  = date_key == today_str
        field_val = ""
        for e in events:
            impact_icon = "\U0001f534" if e["impact"] == "red" else "\U0001f7e0"
            kz = " \u26a1 **KILL ZONE**" if e["during_kill_zone"] else ""
            if e["during_kill_zone"]:
                has_kill_zone = True
            field_val += impact_icon + " **" + e["time"] + "** \u2014 " + e["event"] + kz + "\n"
            if is_today and (e["forecast"] != "-" or e["previous"] != "-"):
                field_val += "  \u2514 F: `" + e["forecast"] + "`  P: `" + e["previous"] + "`\n"
        fields.append({"name": ("\U0001f4c5  TODAY" if is_today else "\U0001f4c5  " + date_key),
                       "value": field_val.strip(), "inline": False})
    footer_text = "Smokey Bias Bot  \u2022  Not financial advice."
    if has_kill_zone:
        footer_text = "\u26a0\ufe0f  News during NY Kill Zone  \u2022  " + footer_text
    return {"title": "\U0001f4f0  Macro Calendar  |  " + today_str,
            "description": "High & medium impact USD events",
            "color": 0x3b82f6, "fields": fields,
            "footer": {"text": footer_text},
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}

def build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                          london_high, london_low, pdh, pdl, bias, ifvgs):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    score_str = ("+" if bias["score"] > 0 else "") + str(bias["score"]) + "/3"
    grade     = bias.get("grade", "C")
    if grade == "A" and ifvgs:
        grade = "A+"
    dow = datetime.now(ET).strftime("%A")
    dow_notes = {"Monday": "Mon - Watch for manipulation", "Tuesday": "Tue - Typical delivery day",
                 "Wednesday": "Wed - Typical delivery day", "Thursday": "Thu - Typical delivery day",
                 "Friday": "Fri - Watch for reversals"}
    dow_note  = dow_notes.get(dow, "")
    bias_icon = "\U0001f7e2" if "BULLISH" in bias["overall"] else "\U0001f534" if "BEARISH" in bias["overall"] else "\u26aa"
    vote_icons = {"+1": "\U0001f7e2", "-1": "\U0001f534", " 0": "\u26aa"}
    msg  = "--------------------\n"
    msg += "\U0001f4ca <b>NQ1! Daily Bias | " + date_str + "</b>\n"
    if dow_note:
        msg += "<i>" + dow_note + "</i>\n"
    msg += "--------------------\n"
    msg += bias_icon + " <b>" + bias["overall"] + "</b>  |  " + score_str + "  |  Grade: <b>" + grade + "</b>\n"
    msg += "--------------------\n"
    msg += "\U0001f4cd Price:   <b>" + fmt(current_price) + "</b>\n"
    msg += "\U0001f55b MO:      <b>" + fmt(midnight_open) + "</b>\n"
    if pdh and pdl:
        msg += "\U0001f4c5 PDH:     <b>" + fmt(pdh) + "</b>   PDL: <b>" + fmt(pdl) + "</b>\n"
    msg += "\U0001f30f Asia:    H <b>" + fmt(asia_high) + "</b>  L <b>" + fmt(asia_low) + "</b>\n"
    msg += "\U0001f30d London:  H <b>" + fmt(london_high) + "</b>  L <b>" + fmt(london_low) + "</b>\n"
    msg += "--------------------\n"
    msg += "<b>Signal Breakdown:</b>\n"
    labels = {"midnight_open": "MO     ", "asia_range": "Asia   ", "london_break": "London "}
    for key, (vote, direction, detail) in bias["signals"].items():
        icon      = vote_icons.get(vote.strip(), "\u26aa")
        tg_detail = detail.replace(">", "&gt;").replace("<", "&lt;")
        msg += icon + " " + labels[key] + " <i>" + tg_detail + "</i>\n"
    msg += "--------------------\n"
    msg += "<b>1H iFVGs +/-" + str(IFVG_RANGE_PTS) + "pts:</b>\n"
    if not ifvgs:
        msg += "\u2022 None nearby\n"
    else:
        for z in ifvgs:
            zone_icon = "\U0001f7e9" if z["relation"] == "below" else "\U0001f7e5"
            side = "Support (up)" if z["relation"] == "below" else "Resistance (down)"
            msg += zone_icon + " " + fmt(z["bottom"]) + " - " + fmt(z["top"]) + "  " + side + "  (" + str(round(z["dist"])) + "pts)\n"
            msg += "   " + z["target"] + "\n"
    msg += "--------------------\n<i>Not financial advice.</i>"
    return msg

def build_discord_morning(current_price, midnight_open, asia_high, asia_low,
                          london_high, london_low, pdh, pdl, bias, ifvgs):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    score_str = ("+" if bias["score"] > 0 else "") + str(bias["score"]) + "/3"
    grade     = bias.get("grade", "C")
    if grade == "A" and ifvgs:
        grade = "A+"
    dow = datetime.now(ET).strftime("%A")
    dow_notes = {"Monday": "Mon \u2014 Watch for manipulation", "Tuesday": "Tue \u2014 Typical delivery day",
                 "Wednesday": "Wed \u2014 Typical delivery day", "Thursday": "Thu \u2014 Typical delivery day",
                 "Friday": "Fri \u2014 Watch for reversals"}
    dow_note = dow_notes.get(dow, "")
    if "BULLISH" in bias["overall"]:
        color, bias_icon = 0x22c55e, "\U0001f7e2"
    elif "BEARISH" in bias["overall"]:
        color, bias_icon = 0xe74c3c, "\U0001f534"
    else:
        color, bias_icon = 0x95a5a6, "\u26aa"
    vote_icons = {"+1": "\U0001f7e2", "-1": "\U0001f534", "0": "\u26aa"}
    description  = bias_icon + " **" + bias["overall"] + "**   Score: **" + score_str + "**   Grade: **" + grade + "**"
    if dow_note:
        description += "\n> *" + dow_note + "*"
    vix      = get_vix()
    vix_line = build_vix_line(vix)
    if vix_line:
        description += "\n" + vix_line
    levels_val  = "`Price ` **" + fmt(current_price) + "**\n"
    levels_val += "`MO    ` **" + fmt(midnight_open) + "**\n"
    if pdh and pdl:
        levels_val += "`PDH   ` **" + fmt(pdh) + "**\n"
        levels_val += "`PDL   ` **" + fmt(pdl) + "**"
    sessions_val  = "`Asia H` **" + fmt(asia_high) + "**\n"
    sessions_val += "`Asia L` **" + fmt(asia_low) + "**\n"
    sessions_val += "`Lon H ` **" + fmt(london_high) + "**\n"
    sessions_val += "`Lon L ` **" + fmt(london_low) + "**"
    labels = {"midnight_open": "MO    ", "asia_range": "Asia  ", "london_break": "London"}
    signals_val = ""
    for key, (vote, direction, detail) in bias["signals"].items():
        icon = vote_icons.get(vote.strip(), "\u26aa")
        signals_val += icon + " `" + labels[key] + "` \u2014 " + detail + "\n"
    signals_val = signals_val.strip()
    if not ifvgs:
        ifvg_val = "*No iFVGs within " + str(IFVG_RANGE_PTS) + "pts*"
    else:
        ifvg_val = ""
        for z in ifvgs:
            zone_icon = "\U0001f7e9" if z["relation"] == "below" else "\U0001f7e5"
            side      = "Support \u2191" if z["relation"] == "below" else "Resistance \u2193"
            ifvg_val += zone_icon + " `" + fmt(z["bottom"]) + " \u2013 " + fmt(z["top"]) + "` " + side + "  *(" + str(round(z["dist"])) + "pts away)*\n"
        ifvg_val = ifvg_val.strip()
    return {"title": "\U0001f4ca  NQ1! Daily Bias  |  " + date_str,
            "description": description, "color": color,
            "fields": [
                {"name": "\U0001f4cc  Key Levels",       "value": levels_val,   "inline": True},
                {"name": "\U0001f305  Sessions",         "value": sessions_val, "inline": True},
                {"name": "\U0001f50d  Signal Breakdown", "value": signals_val,  "inline": False},
                {"name": "\u26a1  1H iFVGs \u00b1" + str(IFVG_RANGE_PTS) + "pts", "value": ifvg_val, "inline": False},
            ],
            "footer": {"text": "Smokey Bias Bot  \u2022  Not financial advice."},
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}

def build_nyo_message(current_price, bias, midnight_open, asia_high, asia_low,
                      london_high, london_low, pdh, pdl, ifvgs):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    direction = bias["direction"]
    mo        = midnight_open
    bias_icon = "\U0001f7e2" if "BULLISH" in bias["overall"] else "\U0001f534" if "BEARISH" in bias["overall"] else "\u26aa"
    if direction == "bullish":
        respecting = current_price > mo
        status = "Bias respected - price holding above MO" if respecting else "Bias challenged - price below MO"
    elif direction == "bearish":
        respecting = current_price < mo
        status = "Bias respected - price holding below MO" if respecting else "Bias challenged - price above MO"
    else:
        status = "Neutral bias - no directional expectation"
    def dist_label(price, level, name):
        diff  = price - level
        arrow = "above" if diff > 0 else "below"
        return name + ": " + fmt(level) + " (" + str(round(abs(diff))) + "pts " + arrow + ")"
    msg  = "--------------------\n"
    msg += "\U0001f514 <b>NYO Update | " + date_str + "</b>\n"
    msg += "--------------------\n"
    msg += bias_icon + " <b>" + bias["overall"] + "</b>  |  \U0001f4cd <b>" + fmt(current_price) + "</b>\n"
    msg += ("\u2705" if "respected" in status else "\u26a0\ufe0f") + " " + status + "\n"
    msg += "--------------------\n<b>Price vs Key Levels:</b>\n"
    msg += "\U0001f55b " + dist_label(current_price, mo, "MO") + "\n"
    if pdh and pdl:
        msg += "\U0001f4c5 " + dist_label(current_price, pdh, "PDH") + "\n"
        msg += "\U0001f4c5 " + dist_label(current_price, pdl, "PDL") + "\n"
    msg += "\U0001f30f " + dist_label(current_price, asia_high, "Asia H") + "\n"
    msg += "\U0001f30f " + dist_label(current_price, asia_low, "Asia L") + "\n"
    msg += "\U0001f30d " + dist_label(current_price, london_high, "London H") + "\n"
    msg += "\U0001f30d " + dist_label(current_price, london_low, "London L") + "\n"
    if ifvgs:
        msg += "--------------------\n<b>1H iFVGs +/-" + str(IFVG_RANGE_PTS) + "pts:</b>\n"
        for z in ifvgs:
            zone_icon = "\U0001f7e9" if z["relation"] == "below" else "\U0001f7e5"
            side = "Support (up)" if z["relation"] == "below" else "Resistance (down)"
            msg += zone_icon + " " + fmt(z["bottom"]) + " - " + fmt(z["top"]) + "  " + side + "  (" + str(round(z["dist"])) + "pts)\n"
    msg += "--------------------\n\u23f0 <i>NY Kill Zone: 7-10 AM ET</i>\n<i>Not financial advice.</i>"
    return msg

def build_discord_nyo(current_price, bias, midnight_open, asia_high, asia_low,
                      london_high, london_low, pdh, pdl, ifvgs):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    direction = bias["direction"]
    mo        = midnight_open
    if "BULLISH" in bias["overall"]:
        color, bias_icon = 0x22c55e, "\U0001f7e2"
    elif "BEARISH" in bias["overall"]:
        color, bias_icon = 0xe74c3c, "\U0001f534"
    else:
        color, bias_icon = 0x95a5a6, "\u26aa"
    if direction == "bullish":
        respecting = current_price > mo
        status = "\u2705 **Bias respected** \u2014 price holding above MO" if respecting else "\u26a0\ufe0f **Bias challenged** \u2014 price below MO"
    elif direction == "bearish":
        respecting = current_price < mo
        status = "\u2705 **Bias respected** \u2014 price holding below MO" if respecting else "\u26a0\ufe0f **Bias challenged** \u2014 price above MO"
    else:
        status = "\u26aa **Neutral** \u2014 no directional expectation"
    def dist_label(price, level, name):
        diff  = price - level
        arrow = "\u2191" if diff > 0 else "\u2193"
        return "`" + name + "` **" + fmt(level) + "**  " + arrow + " " + str(round(abs(diff))) + "pts"
    levels_val  = dist_label(current_price, mo, "MO     ") + "\n"
    if pdh and pdl:
        levels_val += dist_label(current_price, pdh, "PDH    ") + "\n"
        levels_val += dist_label(current_price, pdl, "PDL    ") + "\n"
    levels_val += dist_label(current_price, asia_high, "Asia H ") + "\n"
    levels_val += dist_label(current_price, asia_low,  "Asia L ") + "\n"
    levels_val += dist_label(current_price, london_high, "Lon H  ") + "\n"
    levels_val += dist_label(current_price, london_low,  "Lon L  ")
    ifvg_val = ""
    if ifvgs:
        for z in ifvgs:
            zone_icon = "\U0001f7e9" if z["relation"] == "below" else "\U0001f7e5"
            side      = "Support \u2191" if z["relation"] == "below" else "Resistance \u2193"
            ifvg_val += zone_icon + " `" + fmt(z["bottom"]) + " \u2013 " + fmt(z["top"]) + "` " + side + "  *(" + str(round(z["dist"])) + "pts away)*\n"
        ifvg_val = ifvg_val.strip()
    fields = [
        {"name": "\U0001f4cb  Status",             "value": status,     "inline": False},
        {"name": "\U0001f4cd  Price vs Key Levels", "value": levels_val, "inline": False},
    ]
    if ifvg_val:
        fields.append({"name": "\u26a1  1H iFVGs \u00b1" + str(IFVG_RANGE_PTS) + "pts", "value": ifvg_val, "inline": False})
    fields.append({"name": "\u23f0  NY Kill Zone", "value": "**7:00 \u2013 10:00 AM ET** \u2014 trade carefully", "inline": False})
    return {"title": "\U0001f514  NYO Update  |  " + date_str,
            "description": bias_icon + " **" + bias["overall"] + "**   \U0001f4cd **" + fmt(current_price) + "**",
            "color": color, "fields": fields,
            "footer": {"text": "Smokey Bias Bot  \u2022  Not financial advice."},
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}

def build_eod_message_v2(bias_direction, result_type, current_price, midnight_open, price_diff, winrate_data):
    date_str = datetime.now(ET).strftime("%a %b %d")
    wins, losses, neutrals = winrate_data["wins"], winrate_data["losses"], winrate_data["neutrals"]
    total  = wins + losses
    streak = "".join(r["result"] for r in winrate_data["history"][-10:])
    if result_type == "win":
        verdict, result_icon = "DELIVERED", "\u2705"
    elif result_type == "failed":
        verdict, result_icon = "FAILED", "\u274c"
    else:
        verdict, result_icon = "CHOPPY DAY", "\u26aa"
    bias_icon    = "\U0001f7e2" if bias_direction == "bullish" else "\U0001f534" if bias_direction == "bearish" else "\u26aa"
    direction_str = "above" if price_diff > 0 else "below"
    diff_str     = str(round(abs(price_diff))) + "pts " + direction_str + " MO"
    chop_reason  = ("Price stayed within 75pts of MO - no clear delivery" if result_type == "choppy"
                    else "" if result_type == "win" else "Price moved against bias direction")
    msg  = "--------------------\n"
    msg += "\U0001f4cb <b>EOD Score | " + date_str + "</b>\n--------------------\n"
    msg += bias_icon + " Bias: <b>" + bias_direction.upper() + "</b>  -&gt;  " + result_icon + " <b>" + verdict + "</b>\n"
    msg += "Close: <b>" + fmt(current_price) + "</b>  (" + diff_str + ")\n"
    msg += "MO:    <b>" + fmt(midnight_open) + "</b>\n"
    if chop_reason:
        msg += "<i>" + chop_reason + "</i>\n"
    msg += "--------------------\n"
    msg += str(wins) + "W  " + str(losses) + "L  " + str(neutrals) + "C\n"
    if total >= 10:
        pct = round(wins / total * 100)
        msg += "<b>Win Rate: " + str(pct) + "%</b> (" + str(total) + " directional days)\n"
    else:
        msg += "Streak so far: " + streak + "\n"
        msg += "<i>" + str(10 - total) + " more days to unlock win rate %</i>\n"
    msg += "--------------------\n<i>W=Win  C=Chop  L=Loss</i>\n<i>Not financial advice.</i>"
    return msg

def build_discord_eod(bias_direction, result_type, current_price, midnight_open, price_diff, winrate_data):
    date_str = datetime.now(ET).strftime("%a %b %d")
    wins, losses, neutrals = winrate_data["wins"], winrate_data["losses"], winrate_data["neutrals"]
    total  = wins + losses
    streak = "".join(r["result"] for r in winrate_data["history"][-10:])
    if result_type == "win":
        verdict, result_icon, color = "DELIVERED", "\u2705", 0x22c55e
    elif result_type == "failed":
        verdict, result_icon, color = "FAILED", "\u274c", 0xe74c3c
    else:
        verdict, result_icon, color = "CHOPPY DAY", "\u26aa", 0x95a5a6
    bias_icon      = "\U0001f7e2" if bias_direction == "bullish" else "\U0001f534" if bias_direction == "bearish" else "\u26aa"
    direction_arrow = "\u2191" if price_diff > 0 else "\u2193"
    reason = ("Price moved " + str(round(abs(price_diff))) + "pts in bias direction \u2714" if result_type == "win"
              else "Price stayed within 75pts of MO \u2014 no clear delivery" if result_type == "choppy"
              else "Price moved against bias direction")
    wr_val = ("**" + str(round(wins / total * 100)) + "%** accuracy (" + str(total) + " directional days)\n`" +
              str(wins) + "W` `" + str(losses) + "L` `" + str(neutrals) + "C`" if total >= 10
              else "`" + str(wins) + "W` `" + str(losses) + "L` `" + str(neutrals) + "C`\n*" +
              str(10 - total) + " more days to unlock win rate %*")
    return {"title": "\U0001f4cb  EOD Score  |  " + date_str,
            "description": bias_icon + " **" + bias_direction.upper() + "** \u2192 " + result_icon + " **" + verdict + "**",
            "color": color,
            "fields": [
                {"name": "\U0001f4cd  Price Action", "value": "`Close` **" + fmt(current_price) + "**\n`MO   ` **" + fmt(midnight_open) + "**\n" + str(round(abs(price_diff))) + "pts " + direction_arrow + " from MO", "inline": True},
                {"name": "\U0001f4ac  Verdict",      "value": reason, "inline": False},
                {"name": "\U0001f3c6  Win Rate",     "value": wr_val, "inline": True},
                {"name": "\U0001f4c8  Last 10",      "value": " ".join(list(streak)) if streak else "*Building...*", "inline": True},
            ],
            "footer": {"text": "Smokey Bias Bot  \u2022  Not financial advice.  \u2022  W=Win  C=Chop  L=Loss"},
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
