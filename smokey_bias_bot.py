"""
Smokey Bias Bot - Final
Schedule (UTC times for Railway):
  11:00 UTC (07:00 ET) - Macro news from Forex Factory
  12:00 UTC (08:00 ET) - Morning bias + chart screenshot
  13:00 UTC (09:00 ET) - NYO update + chart screenshot
  20:00 UTC (16:00 ET) - EOD score + win rate\n"""

import os
import json
import time
import requests
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import pytz

# ── Vision verification (Opus 4.7 cross-check of bias call) ──
# Safe import: if the module or its deps are missing, vision is simply skipped.
try:
    from bias_vision import (
        verify_bias, apply_vision_adjustment,
        verify_nyo_bias, format_nyo_vision_note,
    )
    VISION_AVAILABLE = True
except ImportError as _e:
    print("[VISION] bias_vision module not available (" + str(_e) + ") — vision checks disabled")
    VISION_AVAILABLE = False
    def verify_bias(**kwargs):
        return None
    def apply_vision_adjustment(original_bias, original_grade, verification):
        return original_bias, original_grade, None
    def verify_nyo_bias(**kwargs):
        return None
    def format_nyo_vision_note(verification):
        return None

# CONFIG
TELEGRAM_BOT_TOKEN  = "8757455017:AAFuZgFN5ml3xNCVVE3ww8DyzWThtQrTMos"
TELEGRAM_CHAT_ID    = "5048230949"
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003726448503")

TV_USERNAME  = os.getenv("TV_USERNAME", "")
TV_PASSWORD  = os.getenv("TV_PASSWORD", "")
TV_CHART_URL = "https://www.tradingview.com/chart/hcbriKzA/"  # Your saved 15m NQ chart

DISCORD_WEBHOOK_NEWS  = os.getenv("DISCORD_WEBHOOK_NEWS",  "")
DISCORD_WEBHOOK_BIAS  = os.getenv("DISCORD_WEBHOOK_BIAS",  "")
DISCORD_WEBHOOK_NYO   = os.getenv("DISCORD_WEBHOOK_NYO",   "")
DISCORD_WEBHOOK_EOD   = os.getenv("DISCORD_WEBHOOK_EOD",   "https://discord.com/api/webhooks/1488613489424470036/l2IZxV6gXzVD5HOY5UyHjQw_te38V-vXIuzwagz6v2gy9WNmPtG4qeynD2mLw9fGhveW")
DISCORD_WEBHOOK_XDRAFTS = os.getenv("DISCORD_WEBHOOK_XDRAFTS", "")
DISCORD_WEBHOOK_SMOKEY  = os.getenv("DISCORD_WEBHOOK_SMOKEY",  "")

# Optional: if set, bot listens for !test* commands in Discord
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN", "")

# Optional: if set, enables !draftreply command
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# ── Bot Avatar URLs ───────────────────────────────────────────────────────────
AVATAR_NEWS = "https://i.imgur.com/SfAZTze.jpeg"
AVATAR_BIAS = "https://i.imgur.com/8yGNdYt.jpeg"
AVATAR_NYO  = "https://i.imgur.com/C66iZ8S.jpeg"
AVATAR_EOD  = "https://i.imgur.com/fjvo4SM.jpeg"

SYMBOL          = "NQ=F"
IFVG_RANGE_PTS  = 100
IFVG_LOOKBACK_H = 48

def fmt(val, decimals=2):
    """Safely format a number, returning N/A if None."""
    if val is None:
        return "N/A"
    try:
        return str(round(float(val), decimals))
    except Exception:
        return "N/A"

ET  = pytz.timezone("America/New_York")
UTC = pytz.utc

SCREENSHOT_PATH = Path("/tmp/nq_chart.png")
WINRATE_FILE      = Path("/data/nq_winrate.json")
TODAY_STATE_FILE  = Path("/data/today_state.json")
LEVELS_FILE     = Path("/data/tv_levels.json")
JOBS_RAN_FILE   = Path("/data/jobs_ran.json")

# ── US BANK HOLIDAYS (NQ futures closed) ─────────────────────────────────────
US_HOLIDAYS_2026 = {
    "2026-01-01",  # New Year's Day
    "2026-01-19",  # MLK Day
    "2026-02-16",  # Presidents Day
    "2026-04-03",  # Good Friday
    "2026-05-25",  # Memorial Day
    "2026-07-03",  # Independence Day (observed)
    "2026-09-07",  # Labor Day
    "2026-11-26",  # Thanksgiving
    "2026-11-27",  # Black Friday (early close, skip)
    "2026-12-25",  # Christmas
}

US_HOLIDAYS_2027 = {
    "2027-01-01",  # New Year's Day
    "2027-01-18",  # MLK Day
    "2027-02-15",  # Presidents Day
    "2027-03-26",  # Good Friday
    "2027-05-31",  # Memorial Day
    "2027-07-05",  # Independence Day (observed)
    "2027-09-06",  # Labor Day
    "2027-11-25",  # Thanksgiving
    "2027-12-24",  # Christmas (observed)
}

US_HOLIDAYS = US_HOLIDAYS_2026 | US_HOLIDAYS_2027

def is_market_holiday():
    """Return True if today is a US bank/market holiday."""
    today = datetime.now(ET).strftime("%Y-%m-%d")
    if today in US_HOLIDAYS:
        print("[HOLIDAY] " + today + " is a market holiday - skipping all jobs")
        return True
    return False




def load_jobs_ran():
    """Load today's jobs-ran state - stored inside winrate file for persistence."""
    try:
        data = load_winrate()
        today = datetime.now(ET).strftime("%Y-%m-%d")
        jobs = data.get("jobs_ran", {})
        if jobs.get("date") == today:
            return jobs.get("ran", {})
        return {}
    except Exception:
        return {}

def mark_job_ran(job_name):
    """Record that a job has run today - persisted in winrate file."""
    try:
        today = datetime.now(ET).strftime("%Y-%m-%d")
        ran = load_jobs_ran()
        ran[job_name] = datetime.now(ET).strftime("%H:%M ET")
        data = load_winrate()
        data["jobs_ran"] = {"date": today, "ran": ran}
        save_winrate(data)
        print("  -> Marked job ran: " + job_name)
    except Exception as e:
        print("  -> Failed to mark job ran: " + str(e))

def job_already_ran(job_name):
    """Return True if this job already ran today."""
    ran = load_jobs_ran()
    return job_name in ran


def load_tv_levels():
    """Load TradingView levels sent via webhook. Returns today's levels or empty dict."""
    if not LEVELS_FILE.exists():
        return {}
    try:
        data = json.loads(LEVELS_FILE.read_text())
        today = datetime.now(ET).strftime("%Y-%m-%d")
        return data.get(today, {})
    except Exception:
        return {}

today_state = {
    "bias": None, "score": 0,
    "midnight_open": None,
    "asia_high": None, "asia_low": None,
    "london_high": None, "london_low": None,
    "pdh": None, "pdl": None, "date": None,
}


# WIN RATE TRACKER

def save_today_state():
    """Persist today_state to disk so it survives bot restarts."""
    try:
        TODAY_STATE_FILE.write_text(json.dumps(today_state))
    except Exception as e:
        print("  -> Failed to save today_state: " + str(e))


def load_today_state():
    """Load today_state from disk if it exists and is from today."""
    try:
        if not TODAY_STATE_FILE.exists():
            return
        data = json.loads(TODAY_STATE_FILE.read_text())
        today = datetime.now(ET).strftime("%Y-%m-%d")
        if data.get("date") == today:
            today_state.update(data)
            print("  -> Loaded today_state from disk: " + str(data.get("bias")) + " bias")
        else:
            print("  -> today_state on disk is from a different day, ignoring")
    except Exception as e:
        print("  -> Failed to load today_state: " + str(e))


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
        result = "N"
    elif delivered:
        data["wins"] += 1
        result = "W"
    else:
        data["losses"] += 1
        result = "L"
    data["history"].append({"date": date_str, "bias": bias_direction, "delivered": delivered, "result": result})
    data["history"] = data["history"][-30:]
    save_winrate(data)
    return data


def record_result_v2(bias_direction, result_type):
    """Enhanced scoring: win/failed/choppy/neutral."""
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


def build_eod_message_v2(bias_direction, result_type, current_price, midnight_open, price_diff, winrate_data):
    date_str = datetime.now(ET).strftime("%a %b %d")
    wins     = winrate_data["wins"]
    losses   = winrate_data["losses"]
    neutrals = winrate_data["neutrals"]
    total    = wins + losses
    streak   = "".join(r["result"] for r in winrate_data["history"][-10:])

    if result_type == "win":
        verdict     = "DELIVERED"
        result_icon = "✅"
    elif result_type == "failed":
        verdict     = "FAILED"
        result_icon = "❌"
    else:
        verdict     = "CHOPPY DAY"
        result_icon = "⚪"

    bias_icon     = "🟢" if bias_direction == "bullish" else "🔴" if bias_direction == "bearish" else "⚪"
    direction_str = "above" if price_diff > 0 else "below"
    diff_str      = str(round(abs(price_diff))) + "pts " + direction_str + " MO"

    # Choppy day analysis
    if result_type == "choppy":
        chop_reason = "Price stayed within 75pts of MO - no clear delivery"
    elif result_type == "win":
        chop_reason = ""
    else:
        chop_reason = "Price moved against bias direction"

    msg  = "--------------------\n"
    msg += "📋 <b>EOD Score | " + date_str + "</b>\n"
    msg += "--------------------\n"
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
        remaining = 10 - total
        msg += "Streak so far: " + streak + "\n"
        msg += "<i>" + str(remaining) + " more days to unlock win rate %</i>\n"
    msg += "--------------------\n"
    msg += "<i>W=Win  C=Chop  L=Loss</i>\n"
    msg += "<i>Not financial advice.</i>"
    return msg

def get_winrate_summary():
    data = load_winrate()
    wins = data["wins"]
    losses = data["losses"]
    neutrals = data["neutrals"]
    total = wins + losses
    msg = "<b>Bias Win Rate</b>\n"
    msg += str(wins) + "W  " + str(losses) + "L  " + str(neutrals) + "C\n"
    if total >= 10:
        pct = round(wins / total * 100)
        msg += "<b>" + str(pct) + "% accuracy</b> (" + str(total) + " directional days)\n"
    else:
        remaining = 10 - total
        msg += "<i>Building sample size (" + str(remaining) + " more days needed)</i>\n"
    if data["history"] and len(data["history"]) >= 3:
        streak = "".join(r["result"] for r in data["history"][-10:])
        msg += "Last " + str(len(data["history"][-10:])) + ": " + streak + "\n"
    return msg


# FOREX FACTORY NEWS SCRAPER

def get_forex_factory_news(days=3):
    """Fetch today + next N days of high/medium impact USD news from Forex Factory XML feed.
    Times in XML are GMT - we convert to ET."""
    try:
        import xml.etree.ElementTree as ET_xml
        url = "https://nfs.faireconomy.media/ff_calendar_thisweek.xml"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()

        root = ET_xml.fromstring(resp.content)
        today_et = datetime.now(ET).date()
        cutoff = today_et + timedelta(days=days)
        all_events = {}

        for event in root.findall("event"):
            currency = event.findtext("country", "")
            if currency != "USD":
                continue

            impact = event.findtext("impact", "").lower()
            if impact not in ["high", "medium"]:
                continue

            impact_key = "red" if impact == "high" else "orange"
            title = event.findtext("title", "Unknown")
            date_str = event.findtext("date", "")
            time_str_raw = event.findtext("time", "") or ""
            forecast = event.findtext("forecast", "-") or "-"
            previous = event.findtext("previous", "-") or "-"

            # Parse date (format: MM-DD-YYYY)
            try:
                event_date = datetime.strptime(date_str, "%m-%d-%Y").date()
            except Exception:
                try:
                    event_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                except Exception:
                    continue

            if event_date < today_et or event_date > cutoff:
                continue

            # Convert GMT time to ET
            display_time = "All Day"
            during_kill_zone = False
            et_hour = -1
            if time_str_raw and time_str_raw.strip():
                try:
                    # XML times are like "8:30am" in GMT
                    t_clean = time_str_raw.strip().upper()
                    # Try parsing GMT time
                    for fmt in ["%I:%M%p", "%I:%M %p", "%H:%M"]:
                        try:
                            parsed_gmt = datetime.strptime(t_clean, fmt)
                            # Convert GMT to ET (ET = GMT - 4 during DST, GMT - 5 during standard)
                            now_utc = datetime.now(pytz.utc)
                            now_et_check = now_utc.astimezone(ET)
                            utc_offset = int(now_et_check.utcoffset().total_seconds() / 3600)  # e.g. -4
                            et_hour = (parsed_gmt.hour + utc_offset) % 24
                            et_min = parsed_gmt.minute
                            # Format as 12hr ET
                            et_dt = parsed_gmt.replace(hour=et_hour, minute=et_min)
                            display_time = et_dt.strftime("%-I:%M %p") + " ET"
                            # Kill zone check (today only): 7-10 AM ET
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
                "time": display_time,
                "event": title,
                "impact": impact_key,
                "forecast": forecast,
                "previous": previous,
                "during_kill_zone": during_kill_zone,
                "date": event_date,
                "sort_hour": et_hour if display_time != "All Day" else -1,
            })

        # Sort each day by ET hour
        for date_key in all_events:
            all_events[date_key].sort(key=lambda x: x["sort_hour"])

        # Sort days chronologically
        sorted_events = dict(sorted(all_events.items(), key=lambda x: x[1][0]["date"] if x[1] else today_et))
        return sorted_events

    except Exception as e:
        print("Forex Factory XML fetch failed: " + str(e))
        return {}


def build_news_message(all_events):
    today_et = datetime.now(ET).date()
    today_str = today_et.strftime("%a %b %d")
    msg  = "--------------------\n"
    msg += "📰 <b>Macro Calendar | " + today_str + "</b>\n"
    msg += "--------------------\n"

    if not all_events:
        msg += "✅ No high/medium impact USD news today\n"
        msg += "--------------------\n"
        msg += "<i>Not financial advice.</i>"
        return msg

    has_kill_zone = False

    for date_key, events in all_events.items():
        is_today = date_key == today_str
        if is_today:
            msg += "🗓 <b>TODAY</b>\n"
        else:
            msg += "🗓 <b>" + date_key + "</b>\n"

        for e in events:
            if e["impact"] == "red":
                impact_icon = "🔴"
            else:
                impact_icon = "🟠"
            kz = " ⚡<b>KILL ZONE</b>" if e["during_kill_zone"] else ""
            if e["during_kill_zone"]:
                has_kill_zone = True
            msg += impact_icon + " <b>" + e["time"] + "</b>  " + e["event"] + kz + "\n"
            if is_today and (e["forecast"] != "-" or e["previous"] != "-"):
                msg += "   📊 F: " + e["forecast"] + "  P: " + e["previous"] + "\n"

        msg += "\n"

    msg += "--------------------\n"
    if has_kill_zone:
        msg += "⚠️ <b>News during NY Kill Zone - trade carefully</b>\n"
    msg += "<i>Not financial advice.</i>"
    return msg



def build_discord_news(all_events):
    """Build a Discord embed for the macro news calendar."""
    today_et  = datetime.now(ET).date()
    today_str = today_et.strftime("%a %b %d")

    if not all_events:
        return {
            "title": "\U0001f4f0  Macro Calendar  |  " + today_str,
            "description": "\u2705 No high/medium impact USD news today",
            "color": 0x22c55e,
            "footer": {"text": "Smokey Bias Bot  \u2022  Not financial advice."},
            "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    fields = []
    has_kill_zone = False
    for date_key, events in all_events.items():
        is_today = date_key == today_str
        field_name = "\U0001f4c5  TODAY" if is_today else "\U0001f4c5  " + date_key
        field_val = ""
        for e in events:
            impact_icon = "\U0001f534" if e["impact"] == "red" else "\U0001f7e0"
            kz = " \u26a1 **KILL ZONE**" if e["during_kill_zone"] else ""
            if e["during_kill_zone"]:
                has_kill_zone = True
            field_val += impact_icon + " **" + e["time"] + "** \u2014 " + e["event"] + kz + "\n"
            if is_today and (e["forecast"] != "-" or e["previous"] != "-"):
                field_val += "  \u2514 F: `" + e["forecast"] + "`  P: `" + e["previous"] + "`\n"
        fields.append({"name": field_name, "value": field_val.strip(), "inline": False})

    footer_text = "Smokey Bias Bot  \u2022  Not financial advice."
    if has_kill_zone:
        footer_text = "\u26a0\ufe0f  News during NY Kill Zone \u2014 trade carefully  \u2022  " + footer_text

    return {
        "title": "\U0001f4f0  Macro Calendar  |  " + today_str,
        "description": "High & medium impact USD events",
        "color": 0x3b82f6,
        "fields": fields,
        "footer": {"text": footer_text},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def run_news_job():
    if job_already_ran("news"):
        print("  -> News already ran today, skipping")
        return
    mark_job_ran("news")
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running macro news job...")
    try:
        all_events = get_forex_factory_news(days=3)
        # Telegram (HTML)
        tg_msg = build_news_message(all_events)
        send_telegram_text(tg_msg)
        # Discord (embed)
        news_embed = build_discord_news(all_events)
        send_discord_embed(news_embed, webhook=DISCORD_WEBHOOK_NEWS, avatar_url=AVATAR_NEWS)
    except Exception as e:
        try:
            send_telegram_text("<b>News Error:</b> " + str(e))
        except Exception:
            pass


# DATA FETCHING

def fetch_candles_yf(start_utc, end_utc, interval="1m"):
    """Fetch candles with fallback symbols. One attempt per symbol, no long waits."""
    for sym in [SYMBOL, "MNQ=F"]:
        try:
            ticker = yf.Ticker(sym)
            df = ticker.history(start=start_utc, end=end_utc, interval=interval)
            if not df.empty:
                if sym != SYMBOL:
                    print("  -> Using fallback symbol: " + sym)
                df = df.reset_index()
                return [{"open": float(r["Open"]), "high": float(r["High"]),
                         "low": float(r["Low"]), "close": float(r["Close"])} for _, r in df.iterrows()]
        except Exception as e:
            print("  -> " + sym + " error: " + str(e))
    return []


def get_vix():
    """Fetch current VIX level, with fallback for after-hours."""
    try:
        ticker = yf.Ticker("^VIX")
        # Try today first, then fall back to last 2 days
        for period in ["1d", "2d", "5d"]:
            df = ticker.history(period=period, interval="1h")
            if not df.empty:
                return round(float(df["Close"].iloc[-1]), 2)
    except Exception:
        pass
    return None

def build_vix_line(vix):
    """Return a one-liner sentiment note based on VIX level."""
    if vix is None:
        return ""
    if vix >= 30:
        return "\U0001f6a8 VIX **" + str(vix) + "** — High fear, expect wide ranges & whips. Size down."
    elif vix >= 20:
        return "\u26a0\ufe0f VIX **" + str(vix) + "** — Elevated volatility. Watch for news reactions."
    elif vix >= 15:
        return "\U0001f7e1 VIX **" + str(vix) + "** — Moderate vol. Normal conditions."
    else:
        return "\U0001f7e2 VIX **" + str(vix) + "** — Low vol. Tight ranges, grind likely."


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
    """Try progressively wider windows to find the midnight open."""
    for interval, hours in [("1m", 0.5), ("1m", 1), ("5m", 1), ("5m", 2), ("15m", 3), ("60m", 6)]:
        candles = fetch_candles_yf(midnight_utc, midnight_utc + timedelta(hours=hours), interval)
        if candles:
            print("  -> Midnight open found using " + interval + " (" + str(hours) + "h window)")
            return candles[0]["open"]
    return None

def get_session_hl(start_utc, end_utc):
    candles = fetch_candles_yf(start_utc, end_utc, "1m")
    if not candles:
        return None, None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles), candles[-1]["close"]

def get_current_price():
    """Get the most recent NQ price, looking back up to 2 hours to handle after-hours gaps."""
    now_utc = datetime.now(UTC)
    # Try progressively wider windows to find last traded price
    for minutes in [10, 30, 60, 120]:
        candles = fetch_candles_yf(now_utc - timedelta(minutes=minutes), now_utc, "1m")
        if candles:
            print("  -> Price found looking back " + str(minutes) + " mins: " + str(candles[-1]["close"]))
            return candles[-1]["close"]
    # Last resort: use 5m candles over 4 hours
    candles = fetch_candles_yf(now_utc - timedelta(hours=4), now_utc, "5m")
    if candles:
        print("  -> Price found via 5m fallback: " + str(candles[-1]["close"]))
        return candles[-1]["close"]
    print("  -> Could not fetch current price")
    return None

def get_previous_day_hl():
    now_et = datetime.now(ET)
    today_et = now_et.date()
    midnight = ET.localize(datetime(today_et.year, today_et.month, today_et.day, 0, 0))
    prev_open = (midnight - timedelta(hours=30)).astimezone(UTC)
    prev_close = (midnight - timedelta(hours=1)).astimezone(UTC)
    candles = fetch_candles_yf(prev_open, prev_close, "60m")
    if not candles:
        return None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles)



def detect_15m_displacement(midnight_open):
    """
    Check 15M candles near the MO for displacement.
    Looks at the 2 hours leading into NY open (6-8 AM ET = 10:00-12:30 UTC).
    Returns dict with signal, icon, and description.
    """
    try:
        now_utc   = datetime.now(UTC)
        # Look at last 2.5 hours of 15M candles
        start_utc = now_utc - timedelta(hours=2, minutes=30)
        candles   = fetch_candles_yf(start_utc, now_utc, "15m")

        if not candles or len(candles) < 3:
            return {"signal": "none", "icon": "\u26aa", "detail": "Not enough 15M data"}

        # Displacement = candle body size relative to recent average
        bodies = [abs(c["close"] - c["open"]) for c in candles]
        avg_body = sum(bodies) / len(bodies) if bodies else 1
        displacement_threshold = avg_body * 1.5  # 50% larger than average = displacement

        # Check last 3 candles for displacement near MO
        recent = candles[-3:]
        bullish_disp = False
        bearish_disp = False
        disp_size    = 0
        disp_close   = None

        for c in recent:
            body = abs(c["close"] - c["open"])
            if body < displacement_threshold:
                continue
            # Bullish displacement: closes above MO with strong body
            if c["close"] > midnight_open and c["close"] > c["open"]:
                bullish_disp = True
                disp_size    = round(body)
                disp_close   = c["close"]
            # Bearish displacement: closes below MO with strong body
            elif c["close"] < midnight_open and c["close"] < c["open"]:
                bearish_disp = True
                disp_size    = round(body)
                disp_close   = c["close"]

        if bullish_disp:
            return {
                "signal":  "bullish",
                "icon":    "\U0001f7e2",
                "detail":  "Bullish displacement above MO (" + str(disp_size) + "pt candle, closed " + str(round(disp_close)) + ")",
            }
        elif bearish_disp:
            return {
                "signal":  "bearish",
                "icon":    "\U0001f534",
                "detail":  "Bearish displacement below MO (" + str(disp_size) + "pt candle, closed " + str(round(disp_close)) + ")",
            }
        else:
            # Check if price is just oscillating around MO (choppy)
            closes     = [c["close"] for c in recent]
            above_mo   = sum(1 for c in closes if c > midnight_open)
            below_mo   = sum(1 for c in closes if c < midnight_open)
            if above_mo > 0 and below_mo > 0:
                return {"signal": "choppy", "icon": "\u26aa", "detail": "Price oscillating around MO - no clear displacement"}
            elif above_mo == len(closes):
                return {"signal": "weak_bull", "icon": "\U0001f7e1", "detail": "Price above MO but no displacement candle yet"}
            else:
                return {"signal": "weak_bear", "icon": "\U0001f7e1", "detail": "Price below MO but no displacement candle yet"}
    except Exception as e:
        print("  -> 15M displacement error: " + str(e))
        return {"signal": "none", "icon": "\u26aa", "detail": "15M data unavailable"}


# iFVG DETECTION

def detect_ifvgs(current_price):
    now_utc = datetime.now(UTC)
    start_utc = now_utc - timedelta(hours=IFVG_LOOKBACK_H)
    candles = fetch_candles_yf(start_utc, now_utc, "60m")
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


# BIAS LOGIC

def detect_london_displacement(london_start_utc, london_end_utc, asia_high, asia_low):
    """
    Detect liquidity sweep + displacement in London session.
    Returns dict with sweep type, displacement strength, and target.
    """
    try:
        candles = fetch_candles_yf(london_start_utc, london_end_utc, "60m")
        if not candles or len(candles) < 3:
            return {"swept": None, "displaced": False, "detail": "Not enough London data", "target": None}

        # Calculate average body size for displacement threshold
        bodies = [abs(c["close"] - c["open"]) for c in candles]
        avg_body = sum(bodies) / len(bodies) if bodies else 1
        disp_threshold = avg_body * 1.5

        swept_asia_low  = False
        swept_asia_high = False
        bullish_disp    = False
        bearish_disp    = False
        disp_size       = 0

        # Check each candle for sweep + displacement
        for i, c in enumerate(candles):
            # Sweep of Asia Low (wick below)
            if c["low"] < asia_low and not swept_asia_low:
                swept_asia_low = True
            # Sweep of Asia High (wick above)
            if c["high"] > asia_high and not swept_asia_high:
                swept_asia_high = True

            # Check for strong displacement candle after sweep
            body = abs(c["close"] - c["open"])
            if body >= disp_threshold:
                if swept_asia_low and c["close"] > c["open"]:
                    # Bullish displacement after sweeping sellside
                    bullish_disp = True
                    disp_size    = round(body)
                elif swept_asia_high and c["close"] < c["open"]:
                    # Bearish displacement after sweeping buyside
                    bearish_disp = True
                    disp_size    = round(body)

        if swept_asia_low and bullish_disp:
            return {
                "swept":      "sellside",
                "displaced":  True,
                "direction":  "bullish",
                "detail":     "London swept Asia Low (" + fmt(asia_low) + ") → strong bullish displacement (" + str(disp_size) + "pts)",
                "target":     "buyside",
                "target_detail": "Targeting Asia High / London High",
            }
        elif swept_asia_high and bearish_disp:
            return {
                "swept":      "buyside",
                "displaced":  True,
                "direction":  "bearish",
                "detail":     "London swept Asia High (" + fmt(asia_high) + ") → strong bearish displacement (" + str(disp_size) + "pts)",
                "target":     "sellside",
                "target_detail": "Targeting Asia Low / London Low",
            }
        elif swept_asia_low and not bullish_disp:
            return {
                "swept":      "sellside",
                "displaced":  False,
                "direction":  "neutral",
                "detail":     "London swept Asia Low (" + fmt(asia_low) + ") but no strong displacement — wait for confirmation",
                "target":     None,
                "target_detail": None,
            }
        elif swept_asia_high and not bearish_disp:
            return {
                "swept":      "buyside",
                "displaced":  False,
                "direction":  "neutral",
                "detail":     "London swept Asia High (" + fmt(asia_high) + ") but no strong displacement — wait for confirmation",
                "target":     None,
                "target_detail": None,
            }
        else:
            return {
                "swept":      None,
                "displaced":  False,
                "direction":  "neutral",
                "detail":     "London inside Asia range — no liquidity sweep",
                "target":     None,
                "target_detail": None,
            }
    except Exception as e:
        print("  -> London displacement error: " + str(e))
        return {"swept": None, "displaced": False, "direction": "neutral", "detail": "London analysis unavailable", "target": None, "target_detail": None}


def compute_bias(midnight_open, current_price, asia_high, asia_low,
                 london_high, london_low, london_close=None,
                 london_sweep=None):
    """
    ICT-based bias using liquidity sweep + displacement logic.
    london_sweep = result from detect_london_displacement()
    """
    signals = {}
    score   = 0

    # ── Signal 1: Midnight Open ───────────────────────────────────────────────
    if current_price > midnight_open:
        signals["midnight_open"] = ("+1", "BULL", "Price " + fmt(current_price) + " > MO " + fmt(midnight_open) + " — above midnight open")
        score += 1
    elif current_price < midnight_open:
        signals["midnight_open"] = ("-1", "BEAR", "Price " + fmt(current_price) + " < MO " + fmt(midnight_open) + " — below midnight open")
        score -= 1
    else:
        signals["midnight_open"] = (" 0", "NEUT", "Price at MO " + fmt(midnight_open))

    # ── Signal 2: London Sweep + Displacement (primary signal) ───────────────
    if london_sweep and london_sweep.get("displaced"):
        if london_sweep["direction"] == "bullish":
            signals["london_sweep"] = ("+2", "BULL", london_sweep["detail"])
            score += 2  # double weight — this is the main signal
        elif london_sweep["direction"] == "bearish":
            signals["london_sweep"] = ("-2", "BEAR", london_sweep["detail"])
            score -= 2
    elif london_sweep and london_sweep.get("swept") and not london_sweep.get("displaced"):
        # Sweep with no displacement = wait, neutral
        signals["london_sweep"] = (" 0", "NEUT", london_sweep["detail"])
    else:
        # No sweep = check basic London range break as weak signal
        if london_high > asia_high:
            signals["london_sweep"] = ("+1", "BULL", "London broke above Asia High (" + fmt(london_high) + ") — no sweep/displacement")
            score += 1
        elif london_low < asia_low:
            signals["london_sweep"] = ("-1", "BEAR", "London broke below Asia Low (" + fmt(london_low) + ") — no sweep/displacement")
            score -= 1
        else:
            signals["london_sweep"] = (" 0", "NEUT", "London inside Asia range — no directional signal")

    # ── Determine overall bias ────────────────────────────────────────────────
    if score >= 3:
        overall, direction = "BULLISH", "bullish"
        grade = "A"
    elif score == 2:
        overall, direction = "BULLISH", "bullish"
        grade = "B"
    elif score <= -3:
        overall, direction = "BEARISH", "bearish"
        grade = "A"
    elif score == -2:
        overall, direction = "BEARISH", "bearish"
        grade = "B"
    elif score == 1:
        overall, direction = "LEANING BULLISH", "bullish"
        grade = "C"
    elif score == -1:
        overall, direction = "LEANING BEARISH", "bearish"
        grade = "C"
    else:
        overall, direction = "NEUTRAL / NO TRADE", "neutral"
        grade = "D"

    # ── Target level ─────────────────────────────────────────────────────────
    if london_sweep and london_sweep.get("target_detail"):
        target_detail = london_sweep["target_detail"]
    elif direction == "bullish":
        target_detail = "Targeting buyside above — Asia High / London High"
    elif direction == "bearish":
        target_detail = "Targeting sellside below — Asia Low / London Low"
    else:
        target_detail = "No clear target — wait for NY confirmation"

    return {
        "overall":       overall,
        "score":         score,
        "signals":       signals,
        "direction":     direction,
        "grade":         grade,
        "target_detail": target_detail,
        "london_sweep":  london_sweep,
    }


# MESSAGE BUILDERS

def build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                          london_high, london_low, pdh, pdl, bias, ifvgs):
    date_str = datetime.now(ET).strftime("%a %b %d")
    score_str = ("+" if bias["score"] > 0 else "") + str(bias["score"]) + "/3"

    grade = bias.get("grade", "C")
    if grade == "A" and ifvgs:
        grade = "A+"

    dow = datetime.now(ET).strftime("%A")
    dow_notes = {
        "Monday":    "Mon - Watch for manipulation",
        "Tuesday":   "Tue - Typical delivery day",
        "Wednesday": "Wed - Typical delivery day",
        "Thursday":  "Thu - Typical delivery day",
        "Friday":    "Fri - Watch for reversals",
    }
    dow_note = dow_notes.get(dow, "")
    bias_icon = "🟢" if "BULLISH" in bias["overall"] else "🔴" if "BEARISH" in bias["overall"] else "⚪"
    vote_icons = {"+1": "🟢", "-1": "🔴", " 0": "⚪"}

    msg  = "--------------------\n"
    msg += "📊 <b>NQ1! Daily Bias | " + date_str + "</b>\n"
    if dow_note:
        msg += "<i>" + dow_note + "</i>\n"
    msg += "--------------------\n"
    msg += bias_icon + " <b>" + bias["overall"] + "</b>  |  " + score_str + "  |  Grade: <b>" + grade + "</b>\n"
    msg += "--------------------\n"
    msg += "📍 Price:   <b>" + fmt(current_price) + "</b>\n"
    msg += "🕛 MO:      <b>" + fmt(midnight_open) + "</b>\n"
    if pdh and pdl:
        msg += "📅 PDH:     <b>" + fmt(pdh) + "</b>   PDL: <b>" + fmt(pdl) + "</b>\n"
    msg += "🌏 Asia:    H <b>" + fmt(asia_high) + "</b>  L <b>" + fmt(asia_low) + "</b>\n"
    msg += "🌍 London:  H <b>" + fmt(london_high) + "</b>  L <b>" + fmt(london_low) + "</b>\n"
    msg += "--------------------\n"
    msg += "<b>Signal Breakdown:</b>\n"
    labels = {"midnight_open": "MO          ", "london_sweep": "London Sweep"}
    for key, (vote, direction, detail) in bias["signals"].items():
        icon = vote_icons.get(vote.strip(), "⚪")
        tg_detail = detail.replace(">", "&gt;").replace("<", "&lt;")
        msg += icon + " " + labels[key] + " <i>" + tg_detail + "</i>\n"
    # Target
    if bias.get("target_detail"):
        msg += "\U0001f3af <b>Target:</b> <i>" + bias["target_detail"] + "</i>\n"
    msg += "--------------------\n"
    msg += "<b>1H iFVGs +/-" + str(IFVG_RANGE_PTS) + "pts:</b>\n"
    if not ifvgs:
        msg += "• None nearby\n"
    else:
        for z in ifvgs:
            zone_icon = "🟩" if z["relation"] == "below" else "🟥"
            side = "Support (up)" if z["relation"] == "below" else "Resistance (down)"
            msg += zone_icon + " " + fmt(z["bottom"]) + " - " + fmt(z["top"]) + "  " + side + "  (" + str(round(z["dist"])) + "pts)\n"
            msg += "   " + z["target"] + "\n"
    msg += "--------------------\n"
    msg += "<i>Not financial advice.</i>"
    return msg


def build_nyo_message(current_price, bias, midnight_open,
                      asia_high, asia_low, london_high, london_low, pdh, pdl):
    date_str = datetime.now(ET).strftime("%a %b %d")
    direction = bias["direction"]
    mo = midnight_open

    if direction == "bullish":
        respecting = current_price > mo
        status = "Bias respected - price holding above MO" if respecting else "Bias challenged - price below MO"
    elif direction == "bearish":
        respecting = current_price < mo
        status = "Bias respected - price holding below MO" if respecting else "Bias challenged - price above MO"
    else:
        status = "Neutral bias - no directional expectation"

    def dist_label(price, level, name):
        diff = price - level
        arrow = "above" if diff > 0 else "below"
        return name + ": " + fmt(level) + " (" + str(round(abs(diff))) + "pts " + arrow + ")"

    bias_icon = "🟢" if "BULLISH" in bias["overall"] else "🔴" if "BEARISH" in bias["overall"] else "⚪"
    status_icon = "✅" if "respected" in status else "⚠️" if "challenged" in status else "⚪"

    msg  = "--------------------\n"
    msg += "🔔 <b>NYO Update | " + date_str + "</b>\n"
    msg += "--------------------\n"
    msg += bias_icon + " <b>" + bias["overall"] + "</b>  |  📍 <b>" + fmt(current_price) + "</b>\n"
    msg += status_icon + " " + status + "\n"
    msg += "--------------------\n"
    msg += "<b>Price vs Key Levels:</b>\n"
    msg += "🕛 " + dist_label(current_price, mo, "MO") + "\n"
    if pdh and pdl:
        msg += "📅 " + dist_label(current_price, pdh, "PDH") + "\n"
        msg += "📅 " + dist_label(current_price, pdl, "PDL") + "\n"
    msg += "🌏 " + dist_label(current_price, asia_high, "Asia H") + "\n"
    msg += "🌏 " + dist_label(current_price, asia_low, "Asia L") + "\n"
    msg += "🌍 " + dist_label(current_price, london_high, "London H") + "\n"
    msg += "🌍 " + dist_label(current_price, london_low, "London L") + "\n"
    msg += "--------------------\n"
    msg += "⏰ <i>NY Kill Zone: 7-10 AM ET</i>\n"
    msg += "<i>Not financial advice.</i>"
    return msg


def build_nyo_message_with_ifvgs(current_price, bias, midnight_open,
                                  asia_high, asia_low, london_high, london_low,
                                  pdh, pdl, ifvgs):
    """NYO message with iFVGs included."""
    base = build_nyo_message(current_price, bias, midnight_open,
                              asia_high, asia_low, london_high, london_low, pdh, pdl)
    if not ifvgs:
        return base

    ifvg_section = "--------------------\n"
    ifvg_section += "<b>1H iFVGs +/-" + str(IFVG_RANGE_PTS) + "pts:</b>\n"
    for z in ifvgs:
        zone_icon = "🟩" if z["relation"] == "below" else "🟥"
        side = "Support (up)" if z["relation"] == "below" else "Resistance (down)"
        ifvg_section += zone_icon + " " + fmt(z["bottom"]) + " - " + fmt(z["top"]) + "  " + side + "  (" + str(round(z["dist"])) + "pts)\n"
        ifvg_section += "   " + z["target"] + "\n"

    insert_before = "--------------------\n⏰"
    base = base.replace(insert_before, ifvg_section + insert_before)
    return base


def build_eod_message(bias_direction, delivered, current_price, midnight_open, winrate_data):
    date_str = datetime.now(ET).strftime("%a %b %d")
    result = "DELIVERED" if delivered else "FAILED"
    wins = winrate_data["wins"]
    losses = winrate_data["losses"]
    neutrals = winrate_data["neutrals"]
    total = wins + losses
    pct = round(wins / total * 100) if total > 0 else 0
    streak = "".join(r["result"] for r in winrate_data["history"][-10:])

    msg = "<b>EOD Score - " + date_str + "</b>\n"
    msg += "Bias: <b>" + bias_direction.upper() + "</b> - " + result + "\n"
    msg += "Close: <b>" + fmt(current_price) + "</b>  MO: <b>" + fmt(midnight_open) + "</b>\n"
    msg += "---------------------\n"
    msg += "<b>Win Rate: " + str(pct) + "%</b> (" + str(wins) + "W / " + str(losses) + "L / " + str(neutrals) + "N)\n"
    msg += "Last 10: " + streak + "\n"
    msg += "<i>Not financial advice.</i>"
    return msg


# CHART SCREENSHOT

def take_chart_screenshot():
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        print("Playwright not installed")
        return None

    print("  -> Launching headless browser...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=[
                "--no-sandbox", "--disable-setuid-sandbox",
                "--disable-dev-shm-usage", "--disable-gpu",
            ])
            context = browser.new_context(viewport={"width": 1600, "height": 900}, device_scale_factor=2)
            page = context.new_page()

            if TV_USERNAME and TV_PASSWORD:
                print("  -> Logging into TradingView...")
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

            print("  -> Loading chart...")
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
            img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)

        try:
            draw = ImageDraw.Draw(img)
            watermark = "Smokey Bias | t.me/SmokeyNQBot"
            font_size = max(16, img.width // 50)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

            bbox = draw.textbbox((0, 0), watermark, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            x = img.width - text_w - 15
            y = img.height - text_h - 15

            draw.text((x+2, y+2), watermark, font=font, fill=(0, 0, 0, 180))
            draw.text((x, y), watermark, font=font, fill=(255, 255, 255, 230))
        except Exception as e:
            print("  -> Watermark failed: " + str(e))

        img.save(compressed_path, "JPEG", quality=85, optimize=True)
        return compressed_path
    except Exception as e:
        print("Compression failed: " + str(e))
        return image_path


# TELEGRAM

def send_telegram_photo(image_path, caption):
    if not image_path or not image_path.exists():
        print("  -> No screenshot file found, sending text only")
        send_telegram_text(caption)
        return
    if image_path.stat().st_size < 1000:
        print("  -> Screenshot file too small (" + str(image_path.stat().st_size) + " bytes), sending text only")
        send_telegram_text(caption)
        return

    compressed = compress_screenshot(image_path)

    if not compressed.exists() or compressed.stat().st_size < 1000:
        print("  -> Compressed file invalid, sending text only")
        send_telegram_text(caption)
        return

    safe_caption = caption
    if len(safe_caption) > 1024:
        safe_caption = safe_caption[:1020] + "..."

    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendPhoto"
    for chat_id in [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]:
        if not chat_id:
            continue
        try:
            with open(compressed, "rb") as img:
                resp = requests.post(url, data={
                    "chat_id": chat_id,
                    "caption": safe_caption,
                    "parse_mode": "HTML",
                }, files={"photo": img}, timeout=30)
                if not resp.ok:
                    print("  -> Photo send failed: " + resp.text)
                    with open(compressed, "rb") as img2:
                        resp2 = requests.post(url, data={
                            "chat_id": chat_id,
                            "caption": safe_caption[:1024],
                        }, files={"photo": img2}, timeout=30)
                        if not resp2.ok:
                            send_telegram_text(safe_caption)
                    return
        except Exception as e:
            print("  -> Photo send error: " + str(e))
            send_telegram_text(safe_caption)
            return
    print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Photo sent.")

def send_telegram_text(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    for chat_id in [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]:
        if not chat_id:
            continue
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10).raise_for_status()
        except Exception as e:
            print("  -> Text send error: " + str(e))
    print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Text sent.")


def send_telegram_text(message):
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    for chat_id in [TELEGRAM_CHAT_ID, TELEGRAM_CHANNEL_ID]:
        if not chat_id:
            continue
        try:
            requests.post(url, json={
                "chat_id": chat_id,
                "text": message,
                "parse_mode": "HTML",
            }, timeout=10).raise_for_status()
        except Exception as e:
            print("  -> Text send error: " + str(e))
    print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Text sent.")


def send_teaser(bias_overall, grade, date_str):
    """Send a short teaser to the free channel to create FOMO."""
    if not TELEGRAM_FREE_CHANNEL:
        return
    msg  = "📊 <b>NQ1! Daily Bias | " + date_str + "</b>\n"
    msg += "--------------------\n"
    msg += "<b>" + bias_overall + "</b> | Grade: <b>" + grade + "</b>\n"
    msg += "--------------------\n"
    msg += "Full analysis + chart + iFVG levels in premium channel\n"
    msg += "Join: @SmokeyNQBot\n"
    msg += "<i>Not financial advice.</i>"
    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    try:
        requests.post(url, json={
            "chat_id": TELEGRAM_FREE_CHANNEL,
            "text": msg,
            "parse_mode": "HTML",
        }, timeout=10)
        print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Teaser sent to free channel.")
    except Exception as e:
        print("  -> Teaser send error: " + str(e))


def strip_html(text):
    """Convert Telegram HTML to Discord markdown."""
    import re
    text = re.sub(r"<b>(.*?)</b>", r"****", text, flags=re.DOTALL)
    text = re.sub(r"<i>(.*?)</i>", r"**", text, flags=re.DOTALL)
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def send_discord_embed(embed, image_path=None, webhook=None, avatar_url=None):
    """Send a Discord embed via webhook, with optional image attachment."""
    url = webhook or DISCORD_WEBHOOK_BIAS
    if not url:
        return
    try:
        payload = {"embeds": [embed]}
        if avatar_url:
            payload["avatar_url"] = avatar_url
        if image_path and Path(image_path).exists() and Path(image_path).stat().st_size > 1000:
            compressed = compress_screenshot(Path(image_path))
            embed["image"] = {"url": "attachment://chart.jpg"}
            with open(compressed, "rb") as img:
                requests.post(
                    url,
                    data={"payload_json": json.dumps(payload)},
                    files={"file": ("chart.jpg", img, "image/jpeg")},
                    timeout=30,
                )
        else:
            requests.post(url, json=payload, timeout=10)
        print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Discord embed sent.")
    except Exception as e:
        print("  -> Discord embed send error: " + str(e))


def send_discord_raw(content, image_path=None, webhook=None):
    """Send a plain text message to Discord webhook (used for news/EOD)."""
    url = webhook or DISCORD_WEBHOOK_BIAS
    if not url:
        return
    try:
        if len(content) > 2000:
            content = content[:1997] + "..."
        if image_path and Path(image_path).exists() and Path(image_path).stat().st_size > 1000:
            with open(image_path, "rb") as img:
                requests.post(url, data={"content": content},
                    files={"file": ("chart.jpg", img, "image/jpeg")}, timeout=30)
        else:
            requests.post(url, json={"content": content}, timeout=10)
        print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Discord sent.")
    except Exception as e:
        print("  -> Discord send error: " + str(e))


def build_discord_morning(current_price, midnight_open, asia_high, asia_low,
                          london_high, london_low, pdh, pdl, bias, ifvgs):
    """Build a polished Discord embed for the morning bias post."""
    date_str  = datetime.now(ET).strftime("%a %b %d")
    score_str = ("+" if bias["score"] > 0 else "") + str(bias["score"]) + "/3"
    grade     = bias.get("grade", "C")
    if grade == "A" and ifvgs:
        grade = "A+"

    dow = datetime.now(ET).strftime("%A")
    dow_notes = {
        "Monday":    "Mon — Watch for manipulation",
        "Tuesday":   "Tue — Typical delivery day",
        "Wednesday": "Wed — Typical delivery day",
        "Thursday":  "Thu — Typical delivery day",
        "Friday":    "Fri — Watch for reversals",
    }
    dow_note = dow_notes.get(dow, "")

    if "BULLISH" in bias["overall"]:
        color     = 0x22c55e
        bias_icon = "🟢"
    elif "BEARISH" in bias["overall"]:
        color     = 0xe74c3c
        bias_icon = "🔴"
    else:
        color     = 0x95a5a6
        bias_icon = "⚪"

    vote_icons = {"+1": "🟢", "-1": "🔴", "0": "⚪"}

    description  = bias_icon + " **" + bias["overall"] + "**"
    description += "   Score: **" + score_str + "**   Grade: **" + grade + "**"
    if dow_note:
        description += "\n> *" + dow_note + "*"

    levels_val  = "\U0001f4cd Price  **" + fmt(current_price) + "**\n"
    levels_val += "\U0001f55b MO      **" + fmt(midnight_open) + "**\n"
    if pdh and pdl:
        levels_val += "\U0001f4c5 PDH    **" + fmt(pdh) + "**\n"
        levels_val += "\U0001f4c5 PDL     **" + fmt(pdl) + "**"

    sessions_val  = "\U0001f30f Asia H  **" + fmt(asia_high) + "**\n"
    sessions_val += "\U0001f30f Asia L   **" + fmt(asia_low) + "**\n"
    sessions_val += "\U0001f30d Lon H   **" + fmt(london_high) + "**\n"
    sessions_val += "\U0001f30d Lon L    **" + fmt(london_low) + "**"

    labels = {"midnight_open": "MO          ", "london_sweep": "London Sweep"}
    signals_val = ""
    for key, (vote, direction, detail) in bias["signals"].items():
        icon = vote_icons.get(vote.strip(), "⚪")
        signals_val += icon + " **" + labels[key].strip() + "** — " + detail + "\n"
    signals_val = signals_val.strip()

    if not ifvgs:
        ifvg_val = "*No iFVGs within 100pts*"
    else:
        ifvg_val = ""
        for z in ifvgs:
            if z["relation"] == "below":
                zone_icon = "🟩"
                side      = "Support ↑"
            else:
                zone_icon = "🟥"
                side      = "Resistance ↓"
            ifvg_val += zone_icon + " **" + fmt(z["bottom"]) + " – " + fmt(z["top"]) + "** " + side + "  *(" + str(round(z["dist"])) + "pts away)*\n"
        ifvg_val = ifvg_val.strip()

    vix      = get_vix()
    vix_line = build_vix_line(vix)
    if vix_line:
        description += "\n" + vix_line

    # 15M displacement check
    disp = detect_15m_displacement(midnight_open)

    embed = {
        "title": "📊  NQ1! Daily Bias  |  " + date_str,
        "description": description,
        "color": color,
        "fields": [
            {"name": "\U0001f4cc  Key Levels",  "value": levels_val,   "inline": True},
            {"name": "\U0001f305  Sessions",    "value": sessions_val, "inline": True},
            {"name": "\U0001f50d  Signal Breakdown", "value": signals_val + "\n\U0001f3af  " + bias.get("target_detail", "No clear target"), "inline": False},
            {"name": "\u26a1  1H iFVGs \xb1" + str(IFVG_RANGE_PTS) + "pts", "value": ifvg_val + "\n" + disp["icon"] + "  **15M:** " + disp["detail"], "inline": False},
        ],
        "footer": {"text": "Smokey Bias Bot  •  Not financial advice."},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return embed


def build_discord_nyo(current_price, bias, midnight_open,
                      asia_high, asia_low, london_high, london_low, pdh, pdl, ifvgs):
    """Build a polished Discord embed for the NYO update."""
    date_str  = datetime.now(ET).strftime("%a %b %d")
    direction = bias["direction"]
    mo        = midnight_open

    if "BULLISH" in bias["overall"]:
        color     = 0x22c55e
        bias_icon = "🟢"
    elif "BEARISH" in bias["overall"]:
        color     = 0xe74c3c
        bias_icon = "🔴"
    else:
        color     = 0x95a5a6
        bias_icon = "⚪"

    if direction == "bullish":
        respecting = current_price > mo
        status     = "✅ **Bias respected** — price holding above MO" if respecting else "⚠️ **Bias challenged** — price below MO"
    elif direction == "bearish":
        respecting = current_price < mo
        status     = "✅ **Bias respected** — price holding below MO" if respecting else "⚠️ **Bias challenged** — price above MO"
    else:
        status = "⚪ **Neutral** — no directional expectation"

    def dist_label(price, level, name):
        diff  = price - level
        arrow = "↑" if diff > 0 else "↓"
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
            if z["relation"] == "below":
                zone_icon = "🟩"
                side      = "Support ↑"
            else:
                zone_icon = "🟥"
                side      = "Resistance ↓"
            ifvg_val += zone_icon + " **" + fmt(z["bottom"]) + " – " + fmt(z["top"]) + "** " + side + "  *(" + str(round(z["dist"])) + "pts away)*\n"
        ifvg_val = ifvg_val.strip()

    fields = [
        {"name": "📋  Status", "value": status, "inline": False},
        {"name": "📍  Price vs Key Levels", "value": levels_val, "inline": False},
    ]
    if ifvg_val:
        fields.append({"name": "⚡  1H iFVGs ±" + str(IFVG_RANGE_PTS) + "pts", "value": ifvg_val, "inline": False})
    fields.append({"name": "⏰  NY Kill Zone", "value": "**7:00 – 10:00 AM ET** — trade carefully", "inline": False})

    embed = {
        "title": "🔔  NYO Update  |  " + date_str,
        "description": bias_icon + " **" + bias["overall"] + "**   📍 **" + fmt(current_price) + "**",
        "color": color,
        "fields": fields,
        "footer": {"text": "Smokey Bias Bot  •  Not financial advice."},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return embed


def send_discord(message, image_path=None):
    """Legacy - converts HTML and sends. Used for text-only messages."""
    if not DISCORD_WEBHOOK:
        return
    try:
        discord_msg = strip_html(message)
        if len(discord_msg) > 2000:
            discord_msg = discord_msg[:1997] + "..."
        if image_path and Path(image_path).exists() and Path(image_path).stat().st_size > 1000:
            with open(image_path, "rb") as img:
                requests.post(DISCORD_WEBHOOK, data={"content": discord_msg},
                    files={"file": ("chart.jpg", img, "image/jpeg")}, timeout=30)
        else:
            requests.post(DISCORD_WEBHOOK, json={"content": discord_msg}, timeout=10)
        print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Discord sent.")
    except Exception as e:
        print("  -> Discord send error: " + str(e))


def send_tweet(text):
    """Send draft tweet to #x-drafts Discord channel for easy copy-paste posting."""
    if DISCORD_WEBHOOK_XDRAFTS:
        try:
            draft_msg = "**\U0001f426 X Draft \u2014 ready to copy & post:**\n" + "```" + "\n" + text + "\n" + "```"
            requests.post(DISCORD_WEBHOOK_XDRAFTS, json={"content": draft_msg}, timeout=10)
            print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] X draft posted to Discord.")
        except Exception as e:
            print("  -> X draft error: " + str(e))



def build_bias_tweet(current_price, midnight_open, asia_high, asia_low,
                     london_high, london_low, bias, ifvgs, vix):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    score_str = ("+" if bias["score"] > 0 else "") + str(bias["score"]) + "/3"
    grade     = bias.get("grade", "C")
    if grade == "A" and ifvgs:
        grade = "A+"
    bias_icon = "\U0001f7e2" if "BULLISH" in bias["overall"] else "\U0001f534" if "BEARISH" in bias["overall"] else "\u26aa"
    london_signal = bias["signals"].get("london_break", (" 0", "NEUT", "London inside Asia range"))
    import re
    why_line = re.sub(r"\s*\([^)]*\)", "", london_signal[2]).strip()

    lines = []
    lines.append("\U0001f4ca NQ Bias | " + date_str)
    lines.append("")
    lines.append(bias_icon + " " + bias["overall"] + " | " + score_str + " | Grade: " + grade)
    lines.append("Why: " + why_line)
    if vix and vix >= 25:
        lines.append("")
        lines.append("\U0001f321 VIX " + str(vix) + " \u2014 High vol, size down")
    elif vix and vix >= 18:
        lines.append("")
        lines.append("\U0001f321 VIX " + str(vix) + " \u2014 Elevated vol, watch news")
    lines.append("")
    lines.append("\U0001f55b MO: " + fmt(midnight_open, 0) + "  \U0001f4cd Price: " + fmt(current_price, 0))
    lines.append("\U0001f30f Asia: " + fmt(asia_high, 0) + " / " + fmt(asia_low, 0))
    lines.append("\U0001f30d London: " + fmt(london_high, 0) + " / " + fmt(london_low, 0))
    if ifvgs:
        z = ifvgs[0]
        direction = "Buyside above" if z["relation"] == "below" else "Sellside below"
        lines.append("\U0001f3af " + direction + " " + fmt(z["top"] if z["relation"] == "below" else z["bottom"], 0))
    lines.append("")
    lines.append("Full analysis \u2192 @SmokeyNQ")
    lines.append("#NQ")
    tweet = "\n".join(lines)
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet
def build_nyo_tweet(current_price, bias, midnight_open, ifvgs):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    bias_icon = "\U0001f7e2" if "BULLISH" in bias["overall"] else "\U0001f534" if "BEARISH" in bias["overall"] else "\u26aa"
    direction = bias["direction"]
    mo        = midnight_open
    pts       = str(round(abs(current_price - mo)))

    if direction == "bullish":
        respected = current_price > mo
        status_icon = "\u2705" if respected else "\u26a0\ufe0f"
        status_line = "Price holding " + pts + "pts above MO \u2014 bias respected" if respected else "Price below MO \u2014 bias challenged"
    elif direction == "bearish":
        respected = current_price < mo
        status_icon = "\u2705" if respected else "\u26a0\ufe0f"
        status_line = "Price holding " + pts + "pts below MO \u2014 bias respected" if respected else "Price above MO \u2014 bias challenged"
    else:
        status_icon = "\u26aa"
        status_line = "Neutral \u2014 no directional expectation"

    lines = []
    lines.append("\U0001f514 NYO Update | NQ " + fmt(current_price, 0) + " | " + date_str)
    lines.append("")
    lines.append(bias_icon + " " + bias["overall"] + " bias")
    lines.append(status_icon + " " + status_line)
    if ifvgs:
        z = ifvgs[0]
        side = "resistance" if z["relation"] == "above" else "support"
        lines.append("\u26a1 iFVG " + side + " at " + fmt(z["top"] if z["relation"] == "above" else z["bottom"], 0) + " (" + str(round(z["dist"])) + "pts away)")
    lines.append("")
    lines.append("\u23f0 NY Kill Zone: 7\u201310 AM ET")
    lines.append("Full levels \u2192 @SmokeyNQ")
    lines.append("#NQ")
    tweet = "\n".join(lines)
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet
def build_eod_tweet(bias_direction, result_type, current_price, midnight_open, price_diff, winrate_data):
    date_str = datetime.now(ET).strftime("%a %b %d")
    wins     = winrate_data["wins"]
    losses   = winrate_data["losses"]
    neutrals = winrate_data["neutrals"]
    streak   = "".join(r["result"] for r in winrate_data["history"][-8:])
    bias_icon = "\U0001f7e2" if bias_direction == "bullish" else "\U0001f534" if bias_direction == "bearish" else "\u26aa"

    if result_type == "win":
        result_icon = "\u2705 DELIVERED"
        move_line   = "NQ moved " + str(round(abs(price_diff))) + "pts in bias direction"
    elif result_type == "failed":
        result_icon = "\u274c FAILED"
        move_line   = "NQ moved against bias by " + str(round(abs(price_diff))) + "pts"
    else:
        result_icon = "\u26aa CHOPPY"
        move_line   = "NQ stayed within 75pts of MO"

    streak_visual = " \u00b7 ".join(list(streak)) if streak else "Building..."

    lines = []
    lines.append("\U0001f4cb EOD Score | " + date_str)
    lines.append("")
    lines.append(bias_icon + " " + bias_direction.upper() + " \u2192 " + result_icon)
    lines.append(move_line)
    lines.append("")
    lines.append("\U0001f4c8 Track Record:")
    lines.append(streak_visual)
    lines.append(str(wins) + "W  " + str(losses) + "L  " + str(neutrals) + "C")
    lines.append("")
    lines.append("Follow the streak \u2192 @SmokeyNQ")
    lines.append("#NQ")
    tweet = "\n".join(lines)
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet

def send_tweet(text):
    """Send draft tweet to #x-drafts Discord channel for easy copy-paste posting."""
    if DISCORD_WEBHOOK_XDRAFTS:
        try:
            draft_msg = "**\U0001f426 X Draft \u2014 ready to copy & post:**\n" + "```" + "\n" + text + "\n" + "```"
            requests.post(DISCORD_WEBHOOK_XDRAFTS, json={"content": draft_msg}, timeout=10)
            print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] X draft posted to Discord.")
        except Exception as e:
            print("  -> X draft error: " + str(e))



def build_bias_tweet(current_price, midnight_open, asia_high, asia_low,
                     london_high, london_low, bias, ifvgs, vix):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    score_str = ("+" if bias["score"] > 0 else "") + str(bias["score"]) + "/3"
    grade     = bias.get("grade", "C")
    if grade == "A" and ifvgs:
        grade = "A+"
    bias_icon = "\U0001f7e2" if "BULLISH" in bias["overall"] else "\U0001f534" if "BEARISH" in bias["overall"] else "\u26aa"
    london_signal = bias["signals"].get("london_break", (" 0", "NEUT", "London inside Asia range"))
    import re
    why_line = re.sub(r"\s*\([^)]*\)", "", london_signal[2]).strip()

    lines = []
    lines.append("\U0001f4ca NQ Bias | " + date_str)
    lines.append("")
    lines.append(bias_icon + " " + bias["overall"] + " | " + score_str + " | Grade: " + grade)
    lines.append("Why: " + why_line)
    if vix and vix >= 25:
        lines.append("")
        lines.append("\U0001f321 VIX " + str(vix) + " \u2014 High vol, size down")
    elif vix and vix >= 18:
        lines.append("")
        lines.append("\U0001f321 VIX " + str(vix) + " \u2014 Elevated vol, watch news")
    lines.append("")
    lines.append("\U0001f55b MO: " + fmt(midnight_open, 0) + "  \U0001f4cd Price: " + fmt(current_price, 0))
    lines.append("\U0001f30f Asia: " + fmt(asia_high, 0) + " / " + fmt(asia_low, 0))
    lines.append("\U0001f30d London: " + fmt(london_high, 0) + " / " + fmt(london_low, 0))
    if ifvgs:
        z = ifvgs[0]
        direction = "Buyside above" if z["relation"] == "below" else "Sellside below"
        lines.append("\U0001f3af " + direction + " " + fmt(z["top"] if z["relation"] == "below" else z["bottom"], 0))
    lines.append("")
    lines.append("Full analysis \u2192 @SmokeyNQ")
    lines.append("#NQ")
    tweet = "\n".join(lines)
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet
def build_nyo_tweet(current_price, bias, midnight_open, ifvgs):
    date_str  = datetime.now(ET).strftime("%a %b %d")
    bias_icon = "\U0001f7e2" if "BULLISH" in bias["overall"] else "\U0001f534" if "BEARISH" in bias["overall"] else "\u26aa"
    direction = bias["direction"]
    mo        = midnight_open
    pts       = str(round(abs(current_price - mo)))

    if direction == "bullish":
        respected = current_price > mo
        status_icon = "\u2705" if respected else "\u26a0\ufe0f"
        status_line = "Price holding " + pts + "pts above MO \u2014 bias respected" if respected else "Price below MO \u2014 bias challenged"
    elif direction == "bearish":
        respected = current_price < mo
        status_icon = "\u2705" if respected else "\u26a0\ufe0f"
        status_line = "Price holding " + pts + "pts below MO \u2014 bias respected" if respected else "Price above MO \u2014 bias challenged"
    else:
        status_icon = "\u26aa"
        status_line = "Neutral \u2014 no directional expectation"

    lines = []
    lines.append("\U0001f514 NYO Update | NQ " + fmt(current_price, 0) + " | " + date_str)
    lines.append("")
    lines.append(bias_icon + " " + bias["overall"] + " bias")
    lines.append(status_icon + " " + status_line)
    if ifvgs:
        z = ifvgs[0]
        side = "resistance" if z["relation"] == "above" else "support"
        lines.append("\u26a1 iFVG " + side + " at " + fmt(z["top"] if z["relation"] == "above" else z["bottom"], 0) + " (" + str(round(z["dist"])) + "pts away)")
    lines.append("")
    lines.append("\u23f0 NY Kill Zone: 7\u201310 AM ET")
    lines.append("Full levels \u2192 @SmokeyNQ")
    lines.append("#NQ")
    tweet = "\n".join(lines)
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet
def build_eod_tweet(bias_direction, result_type, current_price, midnight_open, price_diff, winrate_data):
    date_str = datetime.now(ET).strftime("%a %b %d")
    wins     = winrate_data["wins"]
    losses   = winrate_data["losses"]
    neutrals = winrate_data["neutrals"]
    streak   = "".join(r["result"] for r in winrate_data["history"][-8:])
    bias_icon = "\U0001f7e2" if bias_direction == "bullish" else "\U0001f534" if bias_direction == "bearish" else "\u26aa"

    if result_type == "win":
        result_icon = "\u2705 DELIVERED"
        move_line   = "NQ moved " + str(round(abs(price_diff))) + "pts in bias direction"
    elif result_type == "failed":
        result_icon = "\u274c FAILED"
        move_line   = "NQ moved against bias by " + str(round(abs(price_diff))) + "pts"
    else:
        result_icon = "\u26aa CHOPPY"
        move_line   = "NQ stayed within 75pts of MO \u2014 no clear delivery"

    streak_visual = " \u00b7 ".join(list(streak)) if streak else "Building..."

    lines = []
    lines.append("\U0001f4cb EOD Score | " + date_str)
    lines.append("")
    lines.append(bias_icon + " " + bias_direction.upper() + " \u2192 " + result_icon)
    lines.append(move_line)
    lines.append("")
    lines.append("\U0001f4c8 Bias Track Record:")
    lines.append(streak_visual)
    lines.append(str(wins) + "W  " + str(losses) + "L  " + str(neutrals) + "C")
    lines.append("")
    lines.append("Calling direction daily \u2014 follow to track the streak \U0001f447")
    lines.append("\u2014 @SmokeyNQ | NQ Bias Daily | Not financial advice")
    lines.append("")
    lines.append("#NQ #Futures")
    tweet = "\n".join(lines)
    if len(tweet) > 280:
        tweet = tweet[:277] + "..."
    return tweet



# JOBS

def run_morning_bias():
    if job_already_ran("morning"):
        print("  -> Morning bias already ran today, skipping")
        return
    mark_job_ran("morning")
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running morning bias job...")
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
            _             = None
        else:
            print("  -> No TV webhook levels found, using Yahoo Finance")
            midnight_open = get_midnight_open(windows["midnight_open_utc"])
            asia_high, asia_low, _ = get_session_hl(windows["asia_start_utc"], windows["asia_end_utc"])
            london_high, london_low, london_close = get_session_hl(windows["london_start_utc"], windows["london_end_utc"])
        pdh, pdl = get_previous_day_hl()
        current_price = get_current_price() or midnight_open
        screenshot = take_chart_screenshot()

        missing = []
        if not midnight_open: missing.append("midnight_open")
        if not asia_high: missing.append("asia_high")
        if not asia_low: missing.append("asia_low")
        if not london_high: missing.append("london_high")
        if not london_low: missing.append("london_low")
        if not current_price: missing.append("current_price")

        if missing:
            print("  -> Missing data: " + str(missing))

        critical_missing = not midnight_open or not current_price or (not asia_high and not london_high)
        if critical_missing:
            caption = "NQ Bias Bot: Missing session data - " + str(missing)
            if screenshot and screenshot.exists():
                send_telegram_photo(screenshot, caption)
            else:
                send_telegram_text(caption)
            return

        if not asia_high and london_high:
            asia_high = london_high
            asia_low  = london_low
        if not london_high and asia_high:
            london_high = asia_high
            london_low  = asia_low

        london_sweep = detect_london_displacement(
            windows["london_start_utc"], windows["london_end_utc"], asia_high, asia_low)
        print("  -> London sweep: " + str(london_sweep.get("detail", "N/A")))
        bias = compute_bias(midnight_open, current_price, asia_high, asia_low,
                            london_high, london_low, london_close, london_sweep=london_sweep)
        ifvgs = detect_ifvgs(current_price)
        disp  = detect_15m_displacement(midnight_open)

        # ── Opus 4.7 vision verification ────────────────────────────────────
        # Independent chart read; can upgrade grade on confirmation or flag/demote on disagreement.
        if VISION_AVAILABLE and screenshot and screenshot.exists():
            print("  -> Running vision verification against screenshot...")
            verification = verify_bias(
                screenshot_path=screenshot,
                system_bias=bias["direction"],
                system_grade=bias.get("grade", "C"),
                asia_high=asia_high,
                asia_low=asia_low,
                london_high=london_high,
                london_low=london_low,
                midnight_open=midnight_open,
                current_price=current_price,
            )
            final_bias, final_grade, vision_flag = apply_vision_adjustment(
                original_bias=bias["direction"],
                original_grade=bias.get("grade", "C"),
                verification=verification,
            )
            if verification:
                print("  -> Vision read: " + str(verification.get("chart_read", "?")) +
                      " | agrees=" + str(verification.get("agrees_with_system", "?")) +
                      " | conf=" + str(verification.get("confidence", "?")))
                if vision_flag:
                    print("  -> Vision flag: " + vision_flag)
                # Apply adjustments
                bias["direction"] = final_bias
                bias["grade"] = final_grade
                # Keep `overall` display string consistent with the (possibly changed) direction
                if final_bias == "bullish":
                    bias["overall"] = "BULLISH"
                elif final_bias == "bearish":
                    bias["overall"] = "BEARISH"
                else:
                    bias["overall"] = "NEUTRAL / NO TRADE"
                if vision_flag:
                    bias["vision_flag"] = vision_flag
                # Persist verification log to /data for later calibration review
                try:
                    vlog = Path("/data/vision_verifications.jsonl")
                    with open(vlog, "a") as _vf:
                        _vf.write(json.dumps({
                            "ts": datetime.now(UTC).isoformat(),
                            "date_et": datetime.now(ET).strftime("%Y-%m-%d"),
                            "system_bias_before": verification.get("_system_bias_before", None),
                            "system_grade_before": verification.get("_system_grade_before", None),
                            "final_bias": final_bias,
                            "final_grade": final_grade,
                            "verification": verification,
                            "flag": vision_flag,
                        }) + "\n")
                except Exception as _le:
                    print("  -> Vision log write failed: " + str(_le))
            else:
                print("  -> Vision verification unavailable, keeping original bias")
        else:
            if not VISION_AVAILABLE:
                pass  # Module import failed at startup; already logged
            elif not screenshot:
                print("  -> No screenshot to verify against, skipping vision check")

        today_state.update({
            "bias": bias["direction"], "score": bias["score"],
            "midnight_open": midnight_open,
            "asia_high": asia_high, "asia_low": asia_low,
            "london_high": london_high, "london_low": london_low,
            "pdh": pdh, "pdl": pdl,
            "date": datetime.now(ET).strftime("%Y-%m-%d"),
        })
        save_today_state()

        caption = build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                                        london_high, london_low, pdh, pdl, bias, ifvgs)
        caption += "\n--------------------\n"
        caption += "\U0001f56f <b>15M Confirmation:</b>\n"
        caption += disp["icon"] + " <i>" + disp["detail"] + "</i>"

        # Vision verification note (from Opus 4.7)
        if bias.get("vision_flag"):
            caption += "\n\n<b>Vision Check:</b> " + bias["vision_flag"]

        grade = bias.get("grade", "C")
        if grade == "A" and ifvgs:
            grade = "A+"
        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, caption)
        else:
            caption += "\nChart screenshot unavailable."
            send_telegram_text(caption)

        discord_msg = build_discord_morning(current_price, midnight_open, asia_high, asia_low,
                                            london_high, london_low, pdh, pdl, bias, ifvgs)
        if screenshot and screenshot.exists():
            send_discord_embed(discord_msg, screenshot, webhook=DISCORD_WEBHOOK_BIAS, avatar_url=AVATAR_BIAS)
        else:
            send_discord_embed(discord_msg, webhook=DISCORD_WEBHOOK_BIAS, avatar_url=AVATAR_BIAS)

        # X/Twitter
        tweet = build_bias_tweet(current_price, midnight_open, asia_high, asia_low,
                                 london_high, london_low, bias, ifvgs, get_vix())
        send_tweet(tweet)

    except Exception as e:
        try:
            send_telegram_text("<b>Morning Bias Error:</b> " + str(e))
        except Exception:
            pass


def run_nyo_update():
    if job_already_ran("nyo"):
        print("  -> NYO already ran today, skipping")
        return
    mark_job_ran("nyo")
    load_today_state()  # reload in case of redeploy
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running NYO update...")
    try:
        current_price = get_current_price()
        if not current_price or not today_state["midnight_open"]:
            send_telegram_text("NYO Update: No data available.")
            return
        bias = {
            "overall": "BULLISH" if today_state["bias"] == "bullish" else "BEARISH" if today_state["bias"] == "bearish" else "NEUTRAL",
            "direction": today_state["bias"],
            "score": today_state["score"],
        }
        nyo_ifvgs = detect_ifvgs(current_price)
        msg = build_nyo_message_with_ifvgs(
            current_price, bias,
            today_state["midnight_open"],
            today_state["asia_high"],   today_state["asia_low"],
            today_state["london_high"], today_state["london_low"],
            today_state["pdh"],         today_state["pdl"],
            nyo_ifvgs,
        )
        screenshot = take_chart_screenshot()

        # ── Opus 4.7 NYO vision check: is the morning bias still valid? ──
        nyo_vision_note = None
        if VISION_AVAILABLE and screenshot and screenshot.exists():
            print("  -> Running NYO vision check...")
            nyo_verification = verify_nyo_bias(
                screenshot_path=screenshot,
                morning_bias=today_state["bias"],
                current_price=current_price,
                asia_high=today_state["asia_high"],
                asia_low=today_state["asia_low"],
                london_high=today_state["london_high"],
                london_low=today_state["london_low"],
                midnight_open=today_state["midnight_open"],
                pdh=today_state["pdh"],
                pdl=today_state["pdl"],
            )
            if nyo_verification:
                print("  -> NYO Vision status: " + str(nyo_verification.get("status", "?")) +
                      " | valid=" + str(nyo_verification.get("still_valid", "?")) +
                      " | conf=" + str(nyo_verification.get("confidence", "?")))
                nyo_vision_note = format_nyo_vision_note(nyo_verification)
                # Log for calibration
                try:
                    vlog = Path("/data/vision_verifications.jsonl")
                    with open(vlog, "a") as _vf:
                        _vf.write(json.dumps({
                            "ts": datetime.now(UTC).isoformat(),
                            "date_et": datetime.now(ET).strftime("%Y-%m-%d"),
                            "source": "nyo",
                            "morning_bias": today_state["bias"],
                            "current_price": current_price,
                            "verification": nyo_verification,
                            "note": nyo_vision_note,
                        }) + "\n")
                except Exception as _le:
                    print("  -> NYO Vision log write failed: " + str(_le))

        # Attach vision note to the message if present
        if nyo_vision_note:
            msg += "\n\n" + nyo_vision_note

        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, msg)
        else:
            send_telegram_text(msg)

        discord_nyo = build_discord_nyo(
            current_price, bias,
            today_state["midnight_open"],
            today_state["asia_high"],   today_state["asia_low"],
            today_state["london_high"], today_state["london_low"],
            today_state["pdh"],         today_state["pdl"],
            nyo_ifvgs,
        )
        # Append vision note to Discord too
        if nyo_vision_note and isinstance(discord_nyo, dict) and discord_nyo.get("description"):
            discord_nyo["description"] += "\n\n" + nyo_vision_note
        if screenshot and screenshot.exists():
            send_discord_embed(discord_nyo, screenshot, webhook=DISCORD_WEBHOOK_NYO, avatar_url=AVATAR_NYO)
        else:
            send_discord_embed(discord_nyo, webhook=DISCORD_WEBHOOK_NYO, avatar_url=AVATAR_NYO)

        # X/Twitter
        nyo_tweet = build_nyo_tweet(current_price, bias, today_state["midnight_open"], nyo_ifvgs)
        send_tweet(nyo_tweet)
    except Exception as e:
        try:
            send_telegram_text("<b>NYO Update Error:</b> " + str(e))
        except Exception:
            pass



def build_discord_eod(bias_direction, result_type, current_price, midnight_open, price_diff, winrate_data):
    """Build a Discord embed for the EOD score."""
    date_str = datetime.now(ET).strftime("%a %b %d")
    wins     = winrate_data["wins"]
    losses   = winrate_data["losses"]
    neutrals = winrate_data["neutrals"]
    total    = wins + losses
    streak   = "".join(r["result"] for r in winrate_data["history"][-10:])

    if result_type == "win":
        verdict     = "DELIVERED"
        result_icon = "\u2705"
        color       = 0x22c55e
    elif result_type == "failed":
        verdict     = "FAILED"
        result_icon = "\u274c"
        color       = 0xe74c3c
    else:
        verdict     = "CHOPPY DAY"
        result_icon = "\u26aa"
        color       = 0x95a5a6

    bias_icon    = "\U0001f7e2" if bias_direction == "bullish" else "\U0001f534" if bias_direction == "bearish" else "\u26aa"
    direction_arrow = "\u2191" if price_diff > 0 else "\u2193"
    diff_str     = str(round(abs(price_diff))) + "pts " + direction_arrow + " from MO"

    if result_type == "choppy":
        reason = "Price stayed within 75pts of MO \u2014 no clear delivery"
    elif result_type == "failed":
        reason = "Price moved against bias direction"
    else:
        reason = "Price moved " + str(round(abs(price_diff))) + "pts in bias direction \u2714"

    # Win rate field
    if total >= 10:
        pct = round(wins / total * 100)
        wr_val = "**" + str(pct) + "%** accuracy (" + str(total) + " directional days)\n"
        wr_val += "`" + str(wins) + "W` `" + str(losses) + "L` `" + str(neutrals) + "C`"
    else:
        remaining = 10 - total
        wr_val = "`" + str(wins) + "W` `" + str(losses) + "L` `" + str(neutrals) + "C`\n"
        wr_val += "*" + str(remaining) + " more days to unlock win rate %*"

    streak_display = " ".join(list(streak)) if streak else "\u2014"

    embed = {
        "title": "\U0001f4cb  EOD Score  |  " + date_str,
        "description": bias_icon + " **" + bias_direction.upper() + "** \u2192 " + result_icon + " **" + verdict + "**",
        "color": color,
        "fields": [
            {"name": "\U0001f4cd  Price Action", "value": "`Close` **" + fmt(current_price) + "**\n`MO   ` **" + fmt(midnight_open) + "**\n" + diff_str, "inline": True},
            {"name": "\U0001f4ac  Verdict",      "value": reason, "inline": False},
            {"name": "\U0001f3c6  Win Rate",      "value": wr_val, "inline": True},
            {"name": "\U0001f4c8  Last 10",       "value": streak_display if streak_display != "\u2014" else "*Building...*", "inline": True},
        ],
        "footer": {"text": "Smokey Bias Bot  \u2022  Not financial advice.  \u2022  W=Win  C=Chop  L=Loss"},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return embed


def run_eod_score():
    if job_already_ran("eod"):
        print("  -> EOD already ran today, skipping")
        return
    mark_job_ran("eod")
    load_today_state()  # reload in case of redeploy
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running EOD score...")
    try:
        current_price = get_current_price()
        mo = today_state["midnight_open"]
        direction = today_state["bias"]
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
        # Telegram (HTML)
        tg_msg = build_eod_message_v2(direction, result_type, current_price, mo, price_diff, winrate_data)
        send_telegram_text(tg_msg)
        # Discord (embed)
        eod_embed = build_discord_eod(direction, result_type, current_price, mo, price_diff, winrate_data)
        send_discord_embed(eod_embed, webhook=DISCORD_WEBHOOK_EOD, avatar_url=AVATAR_EOD)

        # X/Twitter
        eod_tweet = build_eod_tweet(direction, result_type, current_price, mo, price_diff, winrate_data)
        send_tweet(eod_tweet)
    except Exception as e:
        try:
            send_telegram_text("<b>EOD Score Error:</b> " + str(e))
        except Exception:
            pass


def send_welcome_message(chat_id):
    """Send welcome message to new group members."""
    msg  = "--------------------\n"
    msg += "👋 <b>Welcome to Smokey Bias!</b>\n"
    msg += "--------------------\n"
    msg += "Here is what you will receive every trading day:\n\n"
    msg += "🕖 <b>7:00 AM ET - Macro Calendar</b>\n"
    msg += "High and medium impact USD news for today and the next 2 days. Kill zone events are flagged.\n\n"
    msg += "📊 <b>8:00 AM ET - Daily Bias</b>\n"
    msg += "NQ1! bias based on Midnight Open, Asia H/L, London H/L, and 1H iFVGs. Includes a chart screenshot and confidence grade (A+/A/B/C/D).\n\n"
    msg += "🔔 <b>9:00 AM ET - NYO Update</b>\n"
    msg += "Is price respecting the bias? Live price vs all key levels heading into the NY Kill Zone.\n\n"
    msg += "📋 <b>4:00 PM ET - EOD Score</b>\n"
    msg += "Did the bias deliver? Win rate tracker updated daily.\n\n"
    msg += "--------------------\n"
    msg += "<b>Grade System:</b>\n"
    msg += "A+ = All 3 signals + iFVG in zone (best setup)\n"
    msg += "A  = All 3 signals agree\n"
    msg += "B  = 2/3 signals agree\n"
    msg += "C  = 1/3 signals\n"
    msg += "D  = Mixed/Neutral\n\n"
    msg += "<b>EOD Scoring:</b>\n"
    msg += "W = Price moved 100+ pts in bias direction\n"
    msg += "C = Choppy - price closed within 75pts of MO\n"
    msg += "L = Price moved 100+ pts against bias\n"
    msg += "--------------------\n"
    msg += "<i>Not financial advice. Always trade your own plan.</i>"

    url = "https://api.telegram.org/bot" + TELEGRAM_BOT_TOKEN + "/sendMessage"
    requests.post(url, json={
        "chat_id": chat_id,
        "text": msg,
        "parse_mode": "HTML",
    }, timeout=10)


def build_discord_weekend_recap(week_wins, week_losses, week_chops, week_streak, wins, losses, neutrals, total):
    """Discord embed for Saturday weekend recap."""
    date_str = datetime.now(ET).strftime("%a %b %d")
    streak_display = " ".join(list(week_streak)) if week_streak else "\u2014"

    # Overall win rate field
    if total >= 10:
        pct = round(wins / total * 100)
        wr_val = "**" + str(pct) + "%** accuracy (" + str(total) + " days)\n"
        wr_val += "`" + str(wins) + "W` `" + str(losses) + "L` `" + str(neutrals) + "C`"
    else:
        remaining = 10 - total
        wr_val = "`" + str(wins) + "W` `" + str(losses) + "L` `" + str(neutrals) + "C`\n"
        wr_val += "*" + str(remaining) + " more days to unlock win rate %*"

    week_val = "`" + str(week_wins) + "W` `" + str(week_losses) + "L` `" + str(week_chops) + "C`"
    if week_streak:
        week_val += "\nStreak: `" + week_streak + "`"
    else:
        week_val += "\n*No trades recorded this week*"

    embed = {
        "title": "\U0001f4c5  Weekly Recap  |  " + week_range_str,
        "description": "Here's how the bias performed this week, and what to watch next.",
        "color": 0x5865f2,  # Discord blurple
        "fields": [
            {"name": "\U0001f4ca  This Week",   "value": week_val, "inline": True},
            {"name": "\U0001f3c6  Overall",     "value": wr_val,   "inline": True},
            {"name": "\U0001f50d  Next Week",   "value": "\u2022 Sunday 6 PM ET \u2014 NQ opens, watch for NWOG\n\u2022 Check Forex Factory for high-impact events\n\u2022 Mark this week's high/low as liquidity targets", "inline": False},
        ],
        "footer": {"text": "Smokey Bias Bot  \u2022  Have a great weekend  \u2022  Not financial advice."},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return embed


def run_weekend_recap():
    """Saturday morning - weekly recap and what to watch next week."""
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running weekend recap...")
    try:
        data = load_winrate()
        wins     = data["wins"]
        losses   = data["losses"]
        neutrals = data["neutrals"]
        total    = wins + losses

        week_history = data["history"][-5:] if data["history"] else []
        week_wins   = sum(1 for r in week_history if r["result"] == "W")
        week_losses = sum(1 for r in week_history if r["result"] == "L")
        week_chops  = sum(1 for r in week_history if r["result"] == "C")
        week_streak = "".join(r["result"] for r in week_history) if week_history else ""

        now_et   = datetime.now(ET)
        date_str = now_et.strftime("%a %b %d")

        msg  = "--------------------\n"
        msg += "📅 <b>Weekly Recap | " + week_range_str + "</b>\n"
        msg += "--------------------\n"
        msg += "<b>This Week:</b>\n"
        msg += str(week_wins) + "W  " + str(week_losses) + "L  " + str(week_chops) + "C\n"
        if week_streak:
            msg += "Streak: " + week_streak + "\n"
        else:
            msg += "No trades recorded this week\n"
        msg += "\n"

        if total >= 10:
            pct = round(wins / total * 100)
            msg += "<b>Overall Win Rate: " + str(pct) + "%</b> (" + str(total) + " days)\n"
            msg += str(wins) + "W  " + str(losses) + "L  " + str(neutrals) + "C\n"
        else:
            remaining = 10 - total
            msg += "<i>" + str(remaining) + " more days to unlock win rate %</i>\n"

        msg += "--------------------\n"
        msg += "<b>What to Watch Next Week:</b>\n"
        msg += "- Sunday 6 PM ET - NQ opens, watch for NWOG\n"
        msg += "- Check Forex Factory for high impact events\n"
        msg += "- Note this week high/low as liquidity targets\n"
        msg += "--------------------\n"
        msg += "Have a great weekend! 🏖\n"
        msg += "<i>Not financial advice.</i>"

        # Telegram
        send_telegram_text(msg)

        # Discord — #end-of-day-results
        try:
            recap_embed = build_discord_weekend_recap(
                week_wins, week_losses, week_chops, week_streak,
                wins, losses, neutrals, total,
            )
            send_discord_embed(recap_embed, webhook=DISCORD_WEBHOOK_EOD, avatar_url=AVATAR_EOD)
        except Exception as _de:
            print("  -> Discord weekend recap failed: " + str(_de))

    except Exception as e:
        try:
            send_telegram_text("<b>Weekend Recap Error:</b> " + str(e))
        except Exception:
            pass


def build_weekly_performance_post():
    """Sunday - clean performance summary for social media."""
    data = load_winrate()
    wins     = data["wins"]
    losses   = data["losses"]
    neutrals = data["neutrals"]
    total    = wins + losses
    week_history = data["history"][-5:] if data["history"] else []
    week_wins   = sum(1 for r in week_history if r["result"] == "W")
    week_losses = sum(1 for r in week_history if r["result"] == "L")
    week_chops  = sum(1 for r in week_history if r["result"] == "C")
    week_streak = "".join(r["result"] for r in week_history)

    date_str = datetime.now(ET).strftime("%b %d, %Y")
    week_range_str = _week_range_str()
    week_range_str = _week_range_str()

    msg  = "📊 <b>Smokey Bias - Weekly Performance</b>\n"
    msg += "Week of " + week_range_str + "\n"
    msg += "--------------------\n"
    msg += "<b>This Week:</b>  " + str(week_wins) + "W  " + str(week_losses) + "L  " + str(week_chops) + "C\n"
    if week_streak:
        msg += "Streak: " + week_streak + "\n"
    msg += "\n"
    if total >= 10:
        pct = round(wins / total * 100)
        msg += "<b>Overall Accuracy: " + str(pct) + "%</b> (" + str(total) + " trading days)\n"
    else:
        msg += "<i>Building track record...</i>\n"
    msg += "--------------------\n"
    msg += "Daily bias alerts for NQ1! futures\n"
    msg += "Midnight Open + Asia/London sessions + 1H iFVGs\n"
    msg += "--------------------\n"
    msg += "Join free: @SmokeyNQBot\n"
    msg += "<i>Not financial advice.</i>"
    return msg


def run_weekly_performance():
    """Sunday 10 AM ET - post weekly performance to all channels."""
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running weekly performance post...")
    try:
        msg = build_weekly_performance_post()
        send_telegram_text(msg)
    except Exception as e:
        try:
            send_telegram_text("<b>Weekly Performance Error:</b> " + str(e))
        except Exception:
            pass


def run_monthly_report():
    """1st of month - full breakdown of last month's performance."""
    now_et = datetime.now(ET)
    if now_et.day != 1:
        return

    print("\n[" + now_et.strftime("%Y-%m-%d %H:%M ET") + "] Running monthly report...")
    try:
        data = load_winrate()
        wins     = data["wins"]
        losses   = data["losses"]
        neutrals = data["neutrals"]
        total    = wins + losses
        history  = data["history"][-22:] if data["history"] else []

        month_wins   = sum(1 for r in history if r["result"] == "W")
        month_losses = sum(1 for r in history if r["result"] == "L")
        month_chops  = sum(1 for r in history if r["result"] == "C")
        month_total  = month_wins + month_losses
        month_pct    = round(month_wins / month_total * 100) if month_total > 0 else 0
        month_streak = "".join(r["result"] for r in history)

        bull_wins = sum(1 for r in history if r.get("bias") == "bullish" and r["result"] == "W")
        bear_wins = sum(1 for r in history if r.get("bias") == "bearish" and r["result"] == "W")
        bull_total = sum(1 for r in history if r.get("bias") == "bullish" and r["result"] in ["W","L"])
        bear_total = sum(1 for r in history if r.get("bias") == "bearish" and r["result"] in ["W","L"])
        bull_pct = round(bull_wins / bull_total * 100) if bull_total > 0 else 0
        bear_pct = round(bear_wins / bear_total * 100) if bear_total > 0 else 0

        prev_month = (now_et.replace(day=1) - timedelta(days=1)).strftime("%B %Y")
        msg  = "📋 <b>Monthly Report | " + prev_month + "</b>\n"
        msg += "--------------------\n"
        msg += "<b>Results:</b>\n"
        msg += str(month_wins) + "W  " + str(month_losses) + "L  " + str(month_chops) + "C\n"
        msg += "<b>Accuracy: " + str(month_pct) + "%</b> (" + str(month_total) + " directional days)\n"
        msg += "Streak: " + month_streak + "\n\n"
        msg += "<b>By Direction:</b>\n"
        msg += "Bullish bias: " + str(bull_pct) + "% (" + str(bull_wins) + "/" + str(bull_total) + ")\n"
        msg += "Bearish bias: " + str(bear_pct) + "% (" + str(bear_wins) + "/" + str(bear_total) + ")\n"
        msg += "--------------------\n"
        if total >= 10:
            overall_pct = round(wins / total * 100)
            msg += "<b>All-Time Win Rate: " + str(overall_pct) + "%</b> (" + str(total) + " days)\n"
        msg += "--------------------\n"
        msg += "<i>Not financial advice.</i>"

        send_telegram_text(msg)

    except Exception as e:
        try:
            send_telegram_text("<b>Monthly Report Error:</b> " + str(e))
        except Exception:
            pass


def build_discord_bias_of_week(wins_this_week, week_wins, week_losses, week_chops):
    """Discord embed for Friday Bias of the Week."""
    date_str = datetime.now(ET).strftime("%b %d")

    if not wins_this_week:
        headline = "No winning biases this week"
        body = "Chop week — market was indecisive"
        color = 0x95a5a6
    else:
        n = len(wins_this_week)
        plural = "es" if n > 1 else ""
        headline = str(n) + " bias" + plural + " delivered this week"
        body = "\n".join(
            "\u2705 `" + r.get("date", "") + "` — **" + r.get("bias", "").upper() + "** delivered"
            for r in wins_this_week
        )
        color = 0xf1c40f  # gold

    week_line = "`" + str(week_wins) + "W` `" + str(week_losses) + "L` `" + str(week_chops) + "C`"

    embed = {
        "title": "\U0001f3c6  Bias of the Week  |  " + week_range_str,
        "description": "**" + headline + "**",
        "color": color,
        "fields": [
            {"name": "\u2728  Winners",     "value": body,       "inline": False},
            {"name": "\U0001f4ca  Week",    "value": week_line,  "inline": True},
        ],
        "footer": {"text": "Smokey Bias Bot  \u2022  Join: @SmokeyNQBot  \u2022  Not financial advice."},
        "timestamp": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    return embed


def _week_range_str(now_et=None):
    """Return Mon-Fri date range string for current week."""
    from datetime import timedelta
    if now_et is None:
        now_et = datetime.now(ET)
    # Find Monday of current week
    days_since_monday = now_et.weekday()
    monday = now_et - timedelta(days=days_since_monday)
    friday = monday + timedelta(days=4)
    if monday.month == friday.month:
        return monday.strftime("%b %d") + " – " + friday.strftime("%d")
    return monday.strftime("%b %d") + " – " + friday.strftime("%b %d")

def run_trade_of_week():
    """Friday EOD - highlight the best bias delivery of the week."""
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running trade of the week...")
    try:
        data = load_winrate()
        week_history = data["history"][-5:] if data["history"] else []
        wins_this_week = [r for r in week_history if r["result"] == "W"]

        date_str = datetime.now(ET).strftime("%b %d")
    week_range_str = _week_range_str()
        msg  = "🏆 <b>Bias of the Week | " + week_range_str + "</b>\n"
        msg += "--------------------\n"

        if not wins_this_week:
            msg += "No winning biases this week\n"
            msg += "Chop week - market was indecisive\n"
        else:
            msg += str(len(wins_this_week)) + " bias" + ("es" if len(wins_this_week) > 1 else "") + " delivered this week\n\n"
            for r in wins_this_week:
                msg += "✅ " + r.get("date", "") + " - " + r.get("bias", "").upper() + " delivered\n"

        msg += "--------------------\n"
        week_wins   = len(wins_this_week)
        week_losses = sum(1 for r in week_history if r["result"] == "L")
        week_chops  = sum(1 for r in week_history if r["result"] == "C")
        msg += "Week: " + str(week_wins) + "W  " + str(week_losses) + "L  " + str(week_chops) + "C\n"
        msg += "--------------------\n"
        msg += "Follow for daily NQ bias alerts\n"
        msg += "Join: @SmokeyNQBot\n"
        msg += "<i>Not financial advice.</i>"

        # Telegram
        send_telegram_text(msg)

        # Discord — #end-of-day-results
        try:
            botw_embed = build_discord_bias_of_week(wins_this_week, week_wins, week_losses, week_chops)
            send_discord_embed(botw_embed, webhook=DISCORD_WEBHOOK_EOD, avatar_url=AVATAR_EOD)
        except Exception as _de:
            print("  -> Discord bias-of-week failed: " + str(_de))

    except Exception as e:
        try:
            send_telegram_text("<b>Trade of Week Error:</b> " + str(e))
        except Exception:
            pass


# ── STARTUP CATCHUP ──────────────────────────────────────────────────────────

def run_catchup():
    """
    On startup, run any jobs that should have already fired today but haven't yet.
    Uses a jobs_ran state file so redeployments never double-post.
    """
    now_utc = datetime.now(UTC)
    now_et  = now_utc.astimezone(ET)
    dow     = now_et.strftime("%A")
    is_weekday = dow in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

    now_utc_mins = now_utc.hour * 60 + now_utc.minute

    print("\n[CATCHUP] Bot started at " + now_et.strftime("%Y-%m-%d %H:%M ET") + " (" + str(now_utc.hour) + ":" + str(now_utc.minute).zfill(2) + " UTC)")

    if not is_weekday:
        print("[CATCHUP] Weekend - skipping weekday job catchup\n")
        return

    # (scheduled UTC minutes, grace buffer mins, job name, function)
    catchup_jobs = [
        (11 * 60,       5,  "news",    run_news_job),
        (12 * 60 + 30,  5,  "morning", run_morning_bias),
        (13 * 60,       5,  "nyo",     run_nyo_update),
        (20 * 60,       5,  "eod",     run_eod_score),
    ]

    ran_any = False
    for sched_mins, grace, job_name, job_fn in catchup_jobs:
        fire_after = sched_mins + grace
        if now_utc_mins >= fire_after:
            if job_already_ran(job_name):
                print("[CATCHUP] ✓ " + job_name + " already ran today at " + load_jobs_ran().get(job_name, "?") + " - skipping")
            else:
                print("[CATCHUP] ⚡ Running missed job: " + job_name + " (scheduled " + str(sched_mins // 60) + ":" + str(sched_mins % 60).zfill(2) + " UTC)")
                try:
                    job_fn()
                    ran_any = True
                    time.sleep(30)  # 30s gap so today_state saves before next job
                except Exception as e:
                    print("[CATCHUP] Error in " + job_name + ": " + str(e))
        else:
            print("[CATCHUP] ✓ " + job_name + " not yet due - will run at scheduled time")

    if not ran_any:
        print("[CATCHUP] No missed jobs to run")
    print("[CATCHUP] Done.\n")


# SCHEDULER

def clear_jobs_ran_for_today():
    """Clear today's jobs_ran so catchup always fires missed jobs on restart."""
    try:
        data = load_winrate()
        data["jobs_ran"] = {}
        save_winrate(data)
        print("[STARTUP] Cleared jobs_ran - catchup will fire all missed jobs")
    except Exception as e:
        print("[STARTUP] Failed to clear jobs_ran: " + str(e))


# ── X REPLY DRAFTER ──────────────────────────────────────────────────────────
# Given a tweet pasted into Discord, generate 3 reply options via Groq.

SMOKEY_REPLY_SYSTEM_PROMPT = """You are Smokey (@SmokeyNQ), an NQ futures trader
trading the NY session (9-11am ET) using ICT methodology. iFVGs, Midnight
Open (MO), liquidity sweeps, displacement.

Your job: write THREE reply options to the tweet below. Each must engage
the ACTUAL argument of the tweet — not just drop trading jargon around it.
The reply should make sense even to someone who didn't read the tweet.

THE THREE REPLIES:

1. Analytical — Take the tweet's claim seriously and add a technical angle
   or fact the author missed. If the tweet isn't about trading, skip ICT
   references entirely and just engage the idea.

2. Contrarian — Disagree with the tweet's core claim and say why. Must be
   a clean logical pushback, not a snarky comeback. If you can't honestly
   disagree, write "skip — I'd agree with this tweet" instead.

3. Level Call — ONLY use this angle if the tweet is about current market
   direction or price. If the tweet is philosophical / meta / community
   drama / not about price, write "skip — tweet isn't about levels" here.
   When it applies: name a specific price level NQ has to hold/break today.

HARD RULES (the drafts break these and I will hate you):
- Under 270 chars each.
- NEVER use these phrases: "at the end of the day", "in my opinion",
  "not taking the bait", "just my take", "food for thought", "results
  matter", "edge is", "focus on".
- No hashtags. No emojis unless the tweet has them first.
- Don't start replies with "Not" or "It's not" — that's weak framing.
- Don't stack ICT buzzwords (iFVG, sweep, displacement, MO) unless the
  tweet is specifically about chart structure. On non-chart tweets, drop
  them entirely.
- Every reply must pass this test: read it without the tweet above it.
  Does it still make a point? If no, rewrite.
- Better to write "skip" than to write filler. Only reply if there's
  something real to say.

FORMAT your response EXACTLY like this, no preamble:

**1. Analytical**
[reply]

**2. Contrarian**
[reply]

**3. Level Call**
[reply]
"""

def _call_groq(system_prompt, user_content, max_tokens=800, temperature=0.8):
    """Shared Groq caller. Returns response text or error string."""
    if not GROQ_API_KEY:
        return "GROQ_API_KEY not set in Railway env vars."
    try:
        resp = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={
                "Authorization": "Bearer " + GROQ_API_KEY,
                "Content-Type": "application/json",
            },
            json={
                "model": "llama-3.3-70b-versatile",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return "Groq error: " + str(e)


def generate_reply_drafts(tweet_text):
    """3 reply options to a tweet."""
    return _call_groq(SMOKEY_REPLY_SYSTEM_PROMPT, "Tweet to reply to:\n\n" + tweet_text, max_tokens=600)


SMOKEY_TWEET_PROMPT = """You are Smokey (@SmokeyNQ), an NQ futures trader using ICT methodology.

SMOKEY'S VOICE — match this exactly:
- lowercase casual. short sentences. no fluff.
- honest and self-aware. calls out his own mistakes.
- says "yall", "tbh", "bro", "onto the next one"
- doesn't lecture. just shares what happened or what he thinks.
- never hype or guru talk. grounded.
- examples of how he actually writes:
  "one win and one loss. ending semi break even on the day."
  "should've held the second trade for longer but felt like today was more of a seek and destroy type of day during ny open."
  "in hindsight the 3m and 5m fvg did not get closed above so this wasn't even a valid trade."
  "took a break from this for a few days but this is where the account is sitting at right now"
  "happy i ended up taking 1R on the long"
  "huge improvement bro! break-even is a way better result than having to buy new accounts."
  "started a $1,000 -> $10,000 / looking good so far"
  "big things coming to the discord soon / excited to announce!"

Your job: write THREE original tweet options on the topic below. Each option
should take a different angle:

1. Analysis — a direct take or observation based on structure/data.
2. Hot take — a provocative or contrarian angle others wouldn't say.
3. Question — an open question to the audience that drives engagement.

HARD RULES:
- Under 270 chars each.
- No hashtags.
- No emojis unless one genuinely adds meaning (max one per tweet).
- Never start with "Just" or "So" or "Honestly".
- NEVER use: "at the end of the day", "results matter", "food for thought",
  "in my opinion", "just my take".
- Write like a trader talking to traders, not like a coach or guru.
- Don't explain basics (iFVG, MO, sweep) — audience already knows them.
- If the topic is about a milestone (followers, account wins, community
  growth), write in a grounded way, not hype/humblebrag.

FORMAT, nothing else:

**1. Analysis**
[tweet]

**2. Hot Take**
[tweet]

**3. Question**
[tweet]
"""


def generate_tweet_drafts(topic):
    """3 original tweet options on a topic."""
    return _call_groq(SMOKEY_TWEET_PROMPT, "Topic:\n\n" + topic, max_tokens=700)


SMOKEY_THREAD_PROMPT = """You are Smokey (@SmokeyNQ), an NQ futures trader using ICT methodology.

Your job: write ONE thread of 6-8 tweets on the topic below.

SMOKEY'S VOICE — match this exactly:
- lowercase casual. short sentences. no fluff.
- honest and self-aware. calls out his own mistakes.
- says "yall", "tbh", "bro", "onto the next one"
- doesn't lecture. just shares what happened or what he thinks.
- never hype or guru talk. grounded.
- examples of how he actually writes:
  "one win and one loss. ending semi break even on the day."
  "should've held the second trade for longer but felt like today was more of a seek and destroy type of day during ny open."
  "in hindsight the 3m and 5m fvg did not get closed above so this wasn't even a valid trade."
  "took a break from this for a few days but this is where the account is sitting at right now"
  "happy i ended up taking 1R on the long"
  "huge improvement bro! break-even is a way better result than having to buy new accounts."
  "started a $1,000 -> $10,000 / looking good so far"
  "big things coming to the discord soon / excited to announce!"

STRUCTURE:
- Tweet 1 (Hook): One or two lines. Specific and concrete. Makes someone stop scrolling. No "thread below", no arrows, no hype.
- Tweets 2-6 (Body): One real point per tweet. Build on each other. Short. Write like you're talking to a trader who already knows the basics — don't explain iFVG, MO, sweep. Just use them.
- Tweet 7-8 (Payoff): A real takeaway or honest conclusion. Something that sticks. No "follow me for more" — just end on something worth saying.

HARD RULES:
- Each tweet can be up to 400 chars. Use the space — don't cut short just to be brief.
- Each body tweet must include at least one specific detail: a level, a concept (iFVG, MO, sweep, displacement), a result in pts, or a concrete mistake. No vague statements.
- No hashtags. No "1/" style numbering.
- No filler tweets. Every tweet has to earn its place.
- No "let's dive in", "here we go", "this is important", "thread below".
- Write in lowercase where it fits Smokey's voice.
- Don't moralize. Don't lecture. Just share what's real.

FORMAT, nothing else:

**Tweet 1 (Hook)**
[text]

**Tweet 2**
[text]

**Tweet 3**
[text]

**Tweet 4**
[text]

**Tweet 5**
[text]

**Tweet 6**
[text]

**Tweet 7**
[text]

**Tweet 8 (Payoff)**
[text]
"""


def generate_thread(topic):
    """A 4-6 tweet thread on a topic."""
    return _call_groq(SMOKEY_THREAD_PROMPT, "Thread topic:\n\n" + topic, max_tokens=2500)


SMOKEY_HOOK_PROMPT = """You are Smokey (@SmokeyNQ), an NQ futures trader. You
write opening lines (hooks) for tweets and threads.

A hook's ONLY job is to make someone stop scrolling. It should:
- Be specific (numbers, names, concrete claims)
- Create curiosity or disagreement
- Fit in one line (under 200 chars ideally)
- Work without context

Your job: generate FIVE hook options for the topic below. Each one should use
a different hook pattern.

PATTERNS to vary across the 5 options:
- Contrarian claim ("Most traders believe X. They're wrong.")
- Specific number/result ("I took 47 trades last month. Only 8 were on my plan.")
- Confession/vulnerability ("I blew 3 accounts before this clicked.")
- Direct question ("Why do 90% of NQ traders lose in the first hour?")
- Promise with payoff ("Here's the one level that decides my bias every day.")

HARD RULES:
- Each hook is standalone (one line, no follow-up).
- No hashtags, no emojis.
- Never start with "So" or "Just" or "Honestly".
- NEVER use: "thread below", "a thread", "here's what I learned", "let me
  explain".

FORMAT, nothing else:

**1. [Pattern name]**
[hook]

**2. [Pattern name]**
[hook]

(through 5)
"""


def generate_hooks(topic):
    """5 hook options for a topic."""
    return _call_groq(SMOKEY_HOOK_PROMPT, "Hook topic:\n\n" + topic, max_tokens=800)


SMOKEY_ROAST_PROMPT = """You are an honest, experienced editor reviewing tweets
for Smokey (@SmokeyNQ), an NQ futures trader. He's about to post the tweet
below. Your job is to critique it HONESTLY before he posts.

Be direct. Don't cushion. He wants real feedback, not encouragement.

Assess it on these criteria:
1. HOOK — Does the first line grab attention? Specific? Or generic?
2. CLARITY — Can a reader understand it in 2 seconds? Or confusing?
3. VALUE — Does it say something worth saying? Or empty filler?
4. VOICE — Does it sound like a real trader? Or AI-generated / guru-speak?
5. LENGTH — Is any part bloated? Could it be shorter?

Then give ONE specific suggested rewrite (or say "post it as is" if it's
actually good — don't force changes that aren't needed).

HARD RULES:
- Be brutally honest but not mean. Focus on the tweet, not the person.
- If the tweet is actually good, say so. Don't invent problems.
- If you suggest a rewrite, keep it the same length or shorter than the
  original. Don't add fluff.

FORMAT:

**Verdict:** [one sentence: "post it", "almost there", or "needs work"]

**What works:**
- [specific thing]

**What doesn't:**
- [specific thing]
- [specific thing if applicable]

**Suggested rewrite:**
[rewritten tweet, or "post as is"]
"""


def generate_roast(tweet_text):
    """Critique a draft tweet."""
    return _call_groq(SMOKEY_ROAST_PROMPT, "Tweet to critique:\n\n" + tweet_text, max_tokens=800, temperature=0.5)


# ============================================================================
# !bias - Morning bias tweet generator
# ============================================================================
SMOKEY_BIAS_PROMPT = """You are Smokey (@SmokeyNQ), an NQ futures trader using
ICT methodology. You post a pre-market bias call on X/Twitter before NY Open.

Your voice:
- Direct, specific, confident but not arrogant
- Uses ICT terminology naturally (Midnight Open/MO, iFVG, liquidity sweeps, PDH/PDL)
- Short and punchy - NQ traders respect brevity
- Never uses hashtags, never uses emojis unless they genuinely fit, never uses guru language
- Writes like someone who actually trades, not like someone selling a course

You will be given bias data for today's NY Open session. Generate THREE distinct
tweet drafts:

1. ANALYTICAL - Level-based, clinical. States the bias, key levels, and target.
   Example tone: "NQ bullish above 26,800. MO at 26,750. Targeting sweep of overnight high at 27,000."

2. CONVICTION - First-person, confident. Shares the read with personality.
   Example tone: "Long bias today. iFVG held on the reclaim, MO is my line in the sand. If we tag 27K I'm done."

3. CONTRARIAN-HOOK - Opens with a reply-bait take, then explains.
   Example tone: "Everyone's bearish on this gap-down but MO says otherwise. Looking long above 26,750, targeting the overnight high."

Rules for ALL three drafts:
- Under 280 characters
- Include the specific levels provided
- No hashtags, no emojis, no rocket/chart emojis
- Natural line breaks for readability
- Sound like a trader, not a guru

Output format (strict):
1. [analytical draft]

2. [conviction draft]

3. [contrarian-hook draft]

No preamble, no explanation, no labels beyond the numbers.
"""


def generate_bias_tweets(bias_data):
    """3 morning bias tweet options from structured bias data."""
    return _call_groq(SMOKEY_BIAS_PROMPT, "Today's bias data:\n\n" + bias_data, max_tokens=900, temperature=0.8)


# ============================================================================
# !recap - Post-trade recap tweet generator
# ============================================================================
SMOKEY_RECAP_PROMPT = """You are Smokey (@SmokeyNQ), an NQ futures trader posting
an end-of-session trade recap on X/Twitter.

Your voice:
- Honest and reflective, not braggy
- Shares wins AND losses with equal weight - this is your trust-building signal
- Uses ICT terminology naturally (MO, iFVG, sweeps)
- Never celebrates with emojis, never uses "LFG" or guru language
- On losses: owns them without being dramatic, often includes "what I'd do differently"
- On wins: states them plainly, often tied to a specific setup that worked

You will be given structured recap data: wins, losses, total P&L, and optional notes.
Generate THREE distinct tweet drafts:

1. STRAIGHT RECAP - Clean summary of the day's trades and result. No fluff.
   Example: "2 trades. 1W 1L. +$420 on the day. Short off the 9:45 sweep worked clean, long at MO retest got stopped before the move. Back at it Monday."

2. LESSON-FOCUSED - Leads with what was learned or what you'd do differently. Honest.
   Example: "Green day but should've sized up the short - had full conviction and took half risk. Lesson: when the read is clean, trust it. +$420."

3. PROCESS-FOCUSED - Frames the day in terms of discipline and process over outcome.
   Example: "Followed the plan. 1W 1L, +$420. The long stop-out was a valid setup that didn't work, not a mistake. That's the game. Onto Monday."

Rules for ALL three drafts:
- Under 280 characters
- If it was a losing day, be honest about it - don't spin it
- Always include the P&L number exactly as given
- No hashtags, no emojis, no guru language
- Natural, reflective, trader-voice
- Reference specific setups from the notes when provided

Output format (strict):
1. [straight recap]

2. [lesson-focused]

3. [process-focused]

No preamble, no explanation, no labels beyond the numbers.
"""


def generate_recap_tweets(recap_data):
    """3 trade recap tweet options from structured trade data."""
    return _call_groq(SMOKEY_RECAP_PROMPT, "Today's trade data:\n\n" + recap_data, max_tokens=900, temperature=0.75)


# ============================================================================
# !replybait - Reply-bait post generator
# ============================================================================
SMOKEY_REPLYBAIT_PROMPT = """You are Smokey (@SmokeyNQ), an NQ futures trader on
X/Twitter. Your task is to generate posts designed to spark conversation and
replies - not to flex results, but to get your audience to engage and share
their own views.

Your voice:
- Confident but curious, never preachy
- Writes like a trader who has opinions, not a content creator chasing engagement
- Uses ICT terminology naturally when relevant
- Never uses clickbait hooks like "Thread" or "Read this before you trade"
- No emojis unless they genuinely fit the sentiment
- Keeps posts short (under 280 chars) - the shorter and sharper, the more replies

You will optionally be given a topic. Generate FIVE distinct reply-bait post
options, one from each category below. Each post should feel natural and
opinionated, not manufactured.

1. UNPOPULAR OPINION - States a take that goes against the common wisdom.
   Example: "Unpopular opinion: most people obsessing over iFVGs would make more money just trading the MO reaction and closing by 10:30."

2. GENUINE QUESTION - Asks the audience something you actually want to know.
   Example: "How many of you actually journal every trade vs just the ones that went wrong? Be honest."

3. CONTRARIAN OBSERVATION - Points out something most traders do wrong or miss.
   Example: "The traders I see failing evals aren't bad at reading charts. They're bad at doing nothing when there's no setup."

4. PRO-VS-BEGINNER CONTRAST - Compares what experienced traders do vs beginners.
   Example: "Beginners check their P&L every 30 seconds. Pros check it at the end of the session. The difference is everything."

5. INDUSTRY CRITIQUE - Calls out something broken or misleading in the space.
   Example: "Half the 'prop firm payout' screenshots on this app are from the smallest allocation because the big ones are still in drawdown. Nobody posts those."

Rules for ALL five posts:
- Under 280 characters each
- Must feel authentic, not designed-to-engage
- No hashtags, minimal/zero emojis
- No clickbait openings ("Listen...", "Hot take:", etc. - the content IS the hook)
- If a topic is given, make the posts relevant to that topic; if no topic, cover
  NQ/ICT/prop-firm/trading-psychology territory broadly

Output format (strict):
1. [unpopular opinion]

2. [genuine question]

3. [contrarian observation]

4. [pro-vs-beginner contrast]

5. [industry critique]

No preamble, no labels beyond the numbers.
"""


def generate_replybait_posts(topic):
    """5 reply-bait post options, optionally focused on a topic."""
    if topic and topic.strip():
        user_msg = "Topic: " + topic.strip() + "\n\nGenerate the 5 reply-bait posts as specified."
    else:
        user_msg = "No specific topic - generate 5 reply-bait posts covering NQ trading, ICT methodology, prop firms, and trading psychology."
    return _call_groq(SMOKEY_REPLYBAIT_PROMPT, user_msg, max_tokens=1200, temperature=0.9)


# ============================================================================
# Scheduled morning bias reminder (weekdays 8:30am ET = 12:30 UTC)
# ============================================================================
def run_bias_reminder():
    """Post a reminder in #x-drafts every weekday morning to run !bias."""
    if not DISCORD_WEBHOOK_XDRAFTS:
        print("[bias_reminder] DISCORD_WEBHOOK_XDRAFTS not set - skipping reminder")
        return
    try:
        reminder_msg = (
            "**Morning bias time**\n\n"
            "NY Open in 30 minutes. Run `!bias` with today's read:\n\n"
            "`!bias direction:long mo:XXXXX ifvg:XXXXX target:XXXXX notes:your read`\n\n"
            "Post the draft you pick to X before 9am ET for max engagement."
        )
        requests.post(DISCORD_WEBHOOK_XDRAFTS, json={"content": reminder_msg}, timeout=10)
        print("[bias_reminder] Morning reminder sent")
    except Exception as e:
        print("[bias_reminder] Error: " + str(e))


# If DISCORD_BOT_TOKEN is set, listen for test commands in Discord.
# Commands: !testrecap, !testbotw, !testbias, !testnyo, !testeod, !testnews
# Safe: all test commands bypass `fired_today` so you can re-run the same day.

def start_command_listener():
    """Spawn a daemon thread running a discord.py bot for test commands."""
    if not DISCORD_BOT_TOKEN:
        print("[COMMANDS] DISCORD_BOT_TOKEN not set - skipping command listener")
        return

    try:
        import discord
        from discord.ext import commands
    except ImportError:
        print("[COMMANDS] discord.py not installed - skipping command listener")
        return

    import threading
    import asyncio

    def run_bot():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        intents = discord.Intents.default()
        intents.message_content = True
        bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

        @bot.event
        async def on_ready():
            print("[COMMANDS] Listener online as " + str(bot.user))

        async def fire_job(ctx, job_fn, label):
            await ctx.send("Firing " + label + "...")
            try:
                await asyncio.get_event_loop().run_in_executor(None, job_fn)
                await ctx.send("Done: " + label)
            except Exception as e:
                await ctx.send("Error in " + label + ": " + str(e)[:500])
                print("[COMMANDS] " + label + " error: " + str(e))

        @bot.command(name="testrecap")
        async def testrecap(ctx):
            await fire_job(ctx, run_weekend_recap, "Weekly Recap")

        @bot.command(name="testbotw")
        async def testbotw(ctx):
            await fire_job(ctx, run_trade_of_week, "Bias of the Week")

        @bot.command(name="testbias")
        async def testbias(ctx):
            try:
                _clear_job_flag("morning")
            except Exception:
                pass
            await fire_job(ctx, run_morning_bias, "Morning Bias")

        @bot.command(name="testnyo")
        async def testnyo(ctx):
            try:
                _clear_job_flag("nyo")
            except Exception:
                pass
            await fire_job(ctx, run_nyo_update, "NYO Update")

        @bot.command(name="testeod")
        async def testeod(ctx):
            try:
                _clear_job_flag("eod")
            except Exception:
                pass
            await fire_job(ctx, run_eod_score, "EOD Score")

        @bot.command(name="testnews")
        async def testnews(ctx):
            await fire_job(ctx, run_news_job, "Macro News")

        @bot.command(name="draftreply")
        async def draftreply(ctx, *, tweet: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!draftreply"):
                tweet = raw_content[len("!draftreply"):].strip()
            if not tweet or len(tweet.strip()) < 10:
                await ctx.send("Usage: !draftreply <paste the tweet text>")
                return
            tweet_lower = tweet.strip().lower()
            if tweet_lower.startswith("http://") or tweet_lower.startswith("https://") or tweet_lower.startswith("www.") or tweet_lower.startswith("x.com/") or tweet_lower.startswith("twitter.com/"):
                await ctx.send("That looks like a URL. Paste the actual tweet text instead.")
                return
            await ctx.send("Drafting 3 replies...")
            try:
                drafts = await asyncio.get_event_loop().run_in_executor(None, generate_reply_drafts, tweet)
                preview = tweet if len(tweet) < 280 else tweet[:277] + "..."
                response = "**Source tweet:**\n> " + preview + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one, edit, post._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Draft error: " + str(e)[:500])
                print("[COMMANDS] draftreply error: " + str(e))

        @bot.command(name="tweet")
        async def tweetcmd(ctx, *, topic: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!tweet"):
                topic = raw_content[len("!tweet"):].strip()
            if not topic or len(topic.strip()) < 5:
                await ctx.send("Usage: !tweet <what you want to tweet about>\nExample: !tweet NQ swept Asia high and ripped 200pts")
                return
            await ctx.send("Drafting 3 tweet options...")
            try:
                drafts = await asyncio.get_event_loop().run_in_executor(None, generate_tweet_drafts, topic)
                preview = topic if len(topic) < 280 else topic[:277] + "..."
                response = "**Topic:** " + preview + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one, edit, post._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Tweet error: " + str(e)[:500])
                print("[COMMANDS] tweet error: " + str(e))

        @bot.command(name="makethread")
        async def threadcmd(ctx, *, topic: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!thread"):
                topic = raw_content[len("!thread"):].strip()
            if not topic or len(topic.strip()) < 5:
                await ctx.send("Usage: !makethread <thread topic>\nExample: !makethread how iFVGs form and why they matter")
                return
            await ctx.send("Drafting a thread... (this takes a few seconds)")
            try:
                thread = await asyncio.get_event_loop().run_in_executor(None, generate_thread, topic)
                response = "**Thread topic:** " + topic + "\n\n" + thread + "\n\n_Copy each tweet separately. Post one at a time, reply-chain them on X._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    # Split across messages
                    chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                    for chunk in chunks:
                        await ctx.send(chunk)
            except Exception as e:
                await ctx.send("Thread error: " + str(e)[:500])
                print("[COMMANDS] thread error: " + str(e))

        @bot.command(name="hook")
        async def hookcmd(ctx, *, topic: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!hook"):
                topic = raw_content[len("!hook"):].strip()
            if not topic or len(topic.strip()) < 5:
                await ctx.send("Usage: !hook <what the tweet/thread is about>\nExample: !hook losing 3 accounts before profitability")
                return
            await ctx.send("Drafting 5 hook options...")
            try:
                hooks = await asyncio.get_event_loop().run_in_executor(None, generate_hooks, topic)
                response = "**Hook topic:** " + topic + "\n\n**Options:**\n" + hooks + "\n\n_Pick the strongest. Build the tweet/thread from there._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Hook error: " + str(e)[:500])
                print("[COMMANDS] hook error: " + str(e))

        @bot.command(name="roast")
        async def roastcmd(ctx, *, tweet: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!roast"):
                tweet = raw_content[len("!roast"):].strip()
            if not tweet or len(tweet.strip()) < 10:
                await ctx.send("Usage: !roast <the tweet you're about to post>\nExample: !roast NQ bullish above 26800, targeting buyside liquidity")
                return
            await ctx.send("Roasting...")
            try:
                roast = await asyncio.get_event_loop().run_in_executor(None, generate_roast, tweet)
                preview = tweet if len(tweet) < 280 else tweet[:277] + "..."
                response = "**Your tweet:**\n> " + preview + "\n\n" + roast
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Roast error: " + str(e)[:500])
                print("[COMMANDS] roast error: " + str(e))

            await ctx.send("Drafting 3 replies...")
            try:
                drafts = await asyncio.get_event_loop().run_in_executor(None, generate_reply_drafts, tweet)
                preview = tweet if len(tweet) < 280 else tweet[:277] + "..."
                response = "**Source tweet:**\n> " + preview + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one, edit, post._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Draft error: " + str(e)[:500])
                print("[COMMANDS] draftreply error: " + str(e))

        @bot.command(name="bias")
        async def biascmd(ctx, *, args: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!bias"):
                args = raw_content[len("!bias"):].strip()
            if not args or len(args.strip()) < 5:
                await ctx.send(
                    "**Usage:** `!bias direction:long mo:26800 ifvg:26750 target:27000 notes:your read`\n\n"
                    "**Example:**\n"
                    "`!bias direction:long mo:26750 ifvg:26720 target:27000 notes:sweep of overnight low then reclaim of MO`\n\n"
                    "All fields optional. More detail = better drafts."
                )
                return
            await ctx.send("Drafting 3 bias options...")
            try:
                drafts = await asyncio.get_event_loop().run_in_executor(None, generate_bias_tweets, args)
                response = "**Bias input:** " + args + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one, post before 9am ET._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Bias error: " + str(e)[:500])
                print("[COMMANDS] bias error: " + str(e))

        @bot.command(name="recap")
        async def recapcmd(ctx, *, args: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!recap"):
                args = raw_content[len("!recap"):].strip()
            if not args or len(args.strip()) < 5:
                await ctx.send(
                    "**Usage:** `!recap wins:1 losses:1 pnl:+420 notes:short off 9:45 sweep worked`\n\n"
                    "**Example:**\n"
                    "`!recap wins:2 losses:0 pnl:+850 notes:both longs from iFVG reclaim, clean day`\n\n"
                    "Fields: `wins`, `losses`, `pnl`, `notes` (all optional but more = better)."
                )
                return
            await ctx.send("Drafting 3 recap options...")
            try:
                drafts = await asyncio.get_event_loop().run_in_executor(None, generate_recap_tweets, args)
                response = "**Trade data:** " + args + "\n\n**Drafts:**\n" + drafts + "\n\n_Attach your P&L screenshot when you post._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Recap error: " + str(e)[:500])
                print("[COMMANDS] recap error: " + str(e))

        @bot.command(name="replybait")
        async def replybaitcmd(ctx, *, topic: str = None):
            raw_content = ctx.message.content
            if raw_content.startswith("!replybait"):
                topic = raw_content[len("!replybait"):].strip()
            await ctx.send("Drafting 5 reply-bait options" + (" on: " + topic if topic else "") + "...")
            try:
                posts = await asyncio.get_event_loop().run_in_executor(None, generate_replybait_posts, topic or "")
                header = "**Topic:** " + topic + "\n\n" if topic else ""
                response = header + "**Options:**\n" + posts + "\n\n_Pick the one that feels most like something you'd actually say._"
                if len(response) <= 2000:
                    await ctx.send(response)
                else:
                    await ctx.send(response[:1997] + "...")
                    await ctx.send(response[1997:])
            except Exception as e:
                await ctx.send("Replybait error: " + str(e)[:500])
                print("[COMMANDS] replybait error: " + str(e))


        def send_alert_embed(webhook_url, title, color, description, ctx_author):
            """Send a formatted trade alert embed to a Discord webhook."""
            if not webhook_url:
                return False
            now = datetime.now(ET).strftime("%m/%d/%y • %I:%M %p ET")
            embed = {
                "embeds": [{
                    "color": color,
                    "fields": [
                        {"name": title, "value": description, "inline": False},
                    ],
                    "footer": {
                        "text": now + "\nSmokeyNQ\nNot financial advice"
                    }
                }]
            }
            try:
                requests.post(webhook_url, json=embed, timeout=10)
                return True
            except Exception as e:
                print("  -> Alert embed error: " + str(e))
                return False

        @bot.command(name="entry")
        async def alert_entry(ctx, *, text: str = ""):
            """!entry <details> — post a trade entry alert to #smokey"""
            if not text:
                await ctx.send("Usage: `!entry NQ long 25280, stop 25255, target 25430`")
                return
            ok = send_alert_embed(DISCORD_WEBHOOK_SMOKEY, "ENTRY", 0x57f287, text, ctx.author)
            await ctx.message.delete()
            if not ok:
                await ctx.send("DISCORD_WEBHOOK_SMOKEY not set in Railway.")

        @bot.command(name="trim")
        async def alert_trim(ctx, *, text: str = ""):
            """!trim <details> — post a trim/partial exit alert to #smokey"""
            if not text:
                await ctx.send("Usage: `!trim +75pts, moving stop to BE`")
                return
            ok = send_alert_embed(DISCORD_WEBHOOK_SMOKEY, "TRIM", 0xfee75c, text, ctx.author)
            await ctx.message.delete()
            if not ok:
                await ctx.send("DISCORD_WEBHOOK_SMOKEY not set in Railway.")

        @bot.command(name="exit")
        async def alert_exit(ctx, *, text: str = ""):
            """!exit <details> — post a full exit alert to #smokey"""
            if not text:
                await ctx.send("Usage: `!exit full exit at 25418, +138pts`")
                return
            ok = send_alert_embed(DISCORD_WEBHOOK_SMOKEY, "EXIT", 0xed4245, text, ctx.author)
            await ctx.message.delete()
            if not ok:
                await ctx.send("DISCORD_WEBHOOK_SMOKEY not set in Railway.")

        @bot.command(name="comment")
        async def alert_comment(ctx, *, text: str = ""):
            """!comment <text> — post market commentary to #smokey"""
            if not text:
                await ctx.send("Usage: `!comment clean sweep of Asia Low into NY open`")
                return
            ok = send_alert_embed(DISCORD_WEBHOOK_SMOKEY, "COMMENTARY", 0x949ba4, text, ctx.author)
            await ctx.message.delete()
            if not ok:
                await ctx.send("DISCORD_WEBHOOK_SMOKEY not set in Railway.")

        @bot.command(name="win")
        async def alert_win(ctx, *, text: str = ""):
            """!win <text> — post a milestone or achievement to #smokey"""
            if not text:
                await ctx.send("Usage: `!win passed the LucidPro 50K eval`")
                return
            ok = send_alert_embed(DISCORD_WEBHOOK_SMOKEY, "WIN", 0xf1c40f, text, ctx.author)
            await ctx.message.delete()
            if not ok:
                await ctx.send("DISCORD_WEBHOOK_SMOKEY not set in Railway.")

        @bot.command(name="smokeyhelp")
        async def smokeyhelp(ctx):
            msg = (
                "**Smokey Bias Bot Commands**\n\n"
                "**Bot triggers (test the scheduled posts)**\n"
                "`!testbias` - fire morning bias now\n"
                "`!testnyo` - fire NYO update now\n"
                "`!testeod` - fire EOD score now\n"
                "`!testnews` - fire macro news now\n"
                "`!testbotw` - fire Bias of the Week\n"
                "`!testrecap` - fire Weekly Recap\n\n"
                "**Trade alerts (posts to #smokey)**\n"
                "`!entry <details>` - post entry alert\n"
                "`!trim <details>` - post trim alert\n"
                "`!exit <details>` - post exit alert\n"
                "`!comment <text>` - post market commentary\n"
                "`!win <text>` - post milestone/achievement\n\n"
                "**Tweet helpers**\n"
                "`!draftreply <tweet text>` - 3 reply options to someone else's tweet\n"
                "`!tweet <topic>` - 3 original tweet drafts\n"
                "`!makethread <topic>` - draft a 4-6 tweet thread\n"
                "`!hook <topic>` - 5 opening-line options\n"
                "`!roast <your tweet>` - honest critique before you post\n"
                "`!bias <direction:long mo:X ifvg:Y target:Z notes:...>` - 3 morning bias drafts\n"
                "`!recap <wins:N losses:N pnl:+X notes:...>` - 3 end-of-day recap drafts\n"
                "`!replybait [optional topic]` - 5 engagement-focused post ideas\n"
            )
            await ctx.send(msg)

        try:
            bot.run(DISCORD_BOT_TOKEN, log_handler=None)
        except Exception as e:
            print("[COMMANDS] Bot crashed: " + str(e))

    t = threading.Thread(target=run_bot, daemon=True, name="DiscordCommandListener")
    t.start()
    print("[COMMANDS] Discord command listener thread started")

def _clear_job_flag(job_key):
    """Remove a single job from today's jobs_ran so it can re-run on demand.
    Jobs are tracked inside the winrate file under data['jobs_ran']['ran'].
    """
    try:
        data = load_winrate()
        today = datetime.now(ET).strftime("%Y-%m-%d")
        jr = data.get("jobs_ran", {})
        if jr.get("date") == today and job_key in jr.get("ran", {}):
            del jr["ran"][job_key]
            data["jobs_ran"] = jr
            save_winrate(data)
            print("[COMMANDS] Cleared " + job_key + " flag for re-run")
    except Exception as e:
        print("[COMMANDS] Could not clear " + job_key + " flag: " + str(e))


def main():
    # Load today's state from disk in case of restart
    load_today_state()

    # Ensure persistent data directory exists
    import os as _os
    _os.makedirs("/data", exist_ok=True)
    print("Smokey Bias Bot - scheduled daily:")
    print("  11:00 UTC (07:00 ET) - Macro news")
    print("  12:00 UTC (08:00 ET) - Morning bias + chart")
    print("  13:00 UTC (09:00 ET) - NYO update + chart")
    print("  20:00 UTC (16:00 ET) - EOD score + win rate")

    # ── Uncomment to test any job immediately on startup ─────────────────────
    # run_news_job()
    # run_morning_bias()
    # run_nyo_update()
    # run_eod_score()
    # ─────────────────────────────────────────────────────────────────────────

    # Catchup disabled - scheduler loop fires missed jobs automatically
    # run_catchup()

    # Start Discord command listener (daemon thread, no-op if no token)
    start_command_listener()

    # Jobs fired by exact UTC time check every 30 seconds
    # Format: (utc_hour, utc_minute, job_key, function, weekday_only)
    fired_today = set()  # in-memory guard against double-firing
    JOBS = [
        (11,  0,  "news",    run_news_job,          True),
        (12, 30,  "biasrmd", run_bias_reminder,     True),  # 8:30am ET weekday reminder to run !bias
        (12, 30,  "morning", run_morning_bias,       True),
        (13,  0,  "nyo",     run_nyo_update,         True),
        (20,  0,  "eod",     run_eod_score,          True),
        (21,  0,  "totw",    run_trade_of_week,      False),  # Friday only checked inside
        (14,  0,  "recap",   run_weekend_recap,      False),  # Saturday only
        (14,  0,  "weekly",  run_weekly_performance, False),  # Sunday only
        (12, 30,  "monthly", run_monthly_report,     False),  # checks day=1 inside
    ]

    print("[SCHEDULER] Running tight time-check loop (checks every 30s)")

    while True:
        now_utc = datetime.now(UTC)
        now_et  = now_utc.astimezone(ET)
        dow     = now_et.strftime("%A")
        is_weekday = dow in ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]

        # Skip all jobs on market holidays
        if is_market_holiday():
            time.sleep(3600)  # sleep 1hr then check again
            continue

        for utc_h, utc_m, job_key, job_fn, weekday_only in JOBS:
            if now_utc.hour == utc_h and now_utc.minute == utc_m:
                if weekday_only and not is_weekday:
                    continue
                if job_key == "recap" and dow != "Saturday":
                    continue
                if job_key == "weekly" and dow != "Sunday":
                    continue
                if job_key == "totw" and dow != "Friday":
                    continue
                fire_key = job_key + "_" + now_et.strftime("%Y-%m-%d")
                if fire_key not in fired_today:
                    fired_today.add(fire_key)
                    print("[SCHEDULER] Firing: " + job_key)
                    try:
                        job_fn()
                    except Exception as e:
                        print("[SCHEDULER] Error in " + job_key + ": " + str(e))

        time.sleep(30)


if __name__ == "__main__":
    import sys
    print("Python version: " + sys.version)
    print("Starting Smokey Bias Bot...")
    try:
        main()
    except Exception as e:
        import traceback
        print("FATAL STARTUP ERROR: " + str(e))
        traceback.print_exc()
        sys.exit(1)
