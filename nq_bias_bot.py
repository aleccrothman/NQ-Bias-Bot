"""
Smokey Bias Bot - Final
Schedule (UTC times for Railway):
  11:00 UTC (07:00 ET) - Macro news from Forex Factory
  12:00 UTC (08:00 ET) - Morning bias + chart screenshot
  13:00 UTC (09:00 ET) - NYO update + chart screenshot
  20:00 UTC (16:00 ET) - EOD score + win rate
"""

import os
import json
import time
import requests
import schedule
import yfinance as yf
from datetime import datetime, timedelta
from pathlib import Path
from bs4 import BeautifulSoup
import pytz

# CONFIG
TELEGRAM_BOT_TOKEN  = "8757455017:AAFuZgFN5ml3xNCVVE3ww8DyzWThtQrTMos"
TELEGRAM_CHAT_ID    = "5048230949"
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID", "-1003726448503")
TELEGRAM_FREE_CHANNEL = os.getenv("TELEGRAM_FREE_CHANNEL", "")  # Optional free/public channel for teasers

TV_USERNAME  = os.getenv("TV_USERNAME", "")
TV_PASSWORD  = os.getenv("TV_PASSWORD", "")
TV_CHART_URL = "https://www.tradingview.com/chart/hcbriKzA/"  # Your saved 15m NQ chart

DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK", "")

SYMBOL          = "NQ=F"
IFVG_RANGE_PTS  = 100
IFVG_LOOKBACK_H = 48

ET  = pytz.timezone("America/New_York")
UTC = pytz.utc

SCREENSHOT_PATH = Path("/tmp/nq_chart.png")
WINRATE_FILE    = Path("/tmp/nq_winrate.json")
LEVELS_FILE     = Path("/tmp/tv_levels.json")


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
    msg += "Close: <b>" + str(round(current_price, 2)) + "</b>  (" + diff_str + ")\n"
    msg += "MO:    <b>" + str(round(midnight_open, 2)) + "</b>\n"
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


def run_news_job():
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running macro news job...")
    try:
        all_events = get_forex_factory_news(days=3)
        msg = build_news_message(all_events)
        send_telegram_text(msg)
    except Exception as e:
        try:
            send_telegram_text("<b>News Error:</b> " + str(e))
        except Exception:
            pass


# DATA FETCHING

def fetch_candles_yf(start_utc, end_utc, interval="1m"):
    ticker = yf.Ticker(SYMBOL)
    df = ticker.history(start=start_utc, end=end_utc, interval=interval)
    if df.empty:
        return []
    df = df.reset_index()
    candles = []
    for _, row in df.iterrows():
        candles.append({
            "open": float(row["Open"]), "high": float(row["High"]),
            "low": float(row["Low"]), "close": float(row["Close"]),
        })
    return candles

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
    # Try progressively wider windows to find the midnight open
    for interval, hours in [("1m", 0.5), ("1m", 1), ("5m", 1), ("5m", 2)]:
        candles = fetch_candles_yf(midnight_utc, midnight_utc + timedelta(hours=hours), interval)
        if candles:
            print("  -> Midnight open found using " + interval + " interval")
            return candles[0]["open"]
    return None

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
    now_et = datetime.now(ET)
    today_et = now_et.date()
    midnight = ET.localize(datetime(today_et.year, today_et.month, today_et.day, 0, 0))
    prev_open = (midnight - timedelta(hours=30)).astimezone(UTC)
    prev_close = (midnight - timedelta(hours=1)).astimezone(UTC)
    candles = fetch_candles_yf(prev_open, prev_close, "60m")
    if not candles:
        return None, None
    return max(c["high"] for c in candles), min(c["low"] for c in candles)


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

def compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low, london_close=None):
    signals, score = {}, 0

    if current_price > midnight_open:
        signals["midnight_open"] = ("+1", "BULL", "Price " + str(round(current_price, 2)) + " &gt; MO " + str(round(midnight_open, 2)))
        score += 1
    elif current_price < midnight_open:
        signals["midnight_open"] = ("-1", "BEAR", "Price " + str(round(current_price, 2)) + " &lt; MO " + str(round(midnight_open, 2)))
        score -= 1
    else:
        signals["midnight_open"] = (" 0", "NEUT", "Price at MO " + str(round(midnight_open, 2)))

    if current_price > asia_high:
        signals["asia_range"] = ("+1", "BULL", "Above Asia High " + str(round(asia_high, 2)))
        score += 1
    elif current_price < asia_low:
        signals["asia_range"] = ("-1", "BEAR", "Below Asia Low " + str(round(asia_low, 2)))
        score -= 1
    else:
        signals["asia_range"] = (" 0", "NEUT", "Inside Asia Range")

    if london_high > asia_high:
        if london_close is not None and london_close < asia_high:
            # Swept Asia High but closed back inside = bearish trap/reversal = BEARISH signal
            signals["london_break"] = ("-1", "BEAR", "London swept Asia High (" + str(round(london_high, 2)) + ") then closed back below - bearish trap")
            score -= 1
        else:
            # Broke above and held = BULLISH
            signals["london_break"] = ("+1", "BULL", "London broke above Asia High (" + str(round(london_high, 2)) + ")")
            score += 1
    elif london_low < asia_low:
        if london_close is not None and london_close > asia_low:
            # Swept Asia Low but closed back inside = bullish trap/reversal = BULLISH signal
            signals["london_break"] = ("+1", "BULL", "London swept Asia Low (" + str(round(london_low, 2)) + ") then closed back above - bullish reversal")
            score += 1
        else:
            # Broke below and held = BEARISH
            signals["london_break"] = ("-1", "BEAR", "London broke below Asia Low (" + str(round(london_low, 2)) + ")")
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

    # Confidence grade (DodgyDD A+ setup logic)
    # A+ = all 3 signals agree AND iFVG in zone (checked later)
    # A  = all 3 signals agree
    # B  = 2/3 signals agree
    # C  = 1/3 or mixed
    abs_score = abs(score)
    if abs_score == 3:
        grade = "A"   # upgraded to A+ if iFVG present (done in build_morning_caption)
    elif abs_score == 2:
        grade = "B"
    elif abs_score == 1:
        grade = "C"
    else:
        grade = "D"

    return {"overall": overall, "score": score, "signals": signals, "direction": direction, "grade": grade}


# MESSAGE BUILDERS

def build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                          london_high, london_low, pdh, pdl, bias, ifvgs):
    date_str = datetime.now(ET).strftime("%a %b %d")
    score_str = ("+" if bias["score"] > 0 else "") + str(bias["score"]) + "/3"

    # Upgrade to A+ if all 3 signals agree AND iFVG nearby
    grade = bias.get("grade", "C")
    if grade == "A" and ifvgs:
        grade = "A+"

    # Day of week context
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
    msg += "📍 Price:   <b>" + str(round(current_price, 2)) + "</b>\n"
    msg += "🕛 MO:      <b>" + str(round(midnight_open, 2)) + "</b>\n"
    if pdh and pdl:
        msg += "📅 PDH:     <b>" + str(round(pdh, 2)) + "</b>   PDL: <b>" + str(round(pdl, 2)) + "</b>\n"
    msg += "🌏 Asia:    H <b>" + str(round(asia_high, 2)) + "</b>  L <b>" + str(round(asia_low, 2)) + "</b>\n"
    msg += "🌍 London:  H <b>" + str(round(london_high, 2)) + "</b>  L <b>" + str(round(london_low, 2)) + "</b>\n"
    msg += "--------------------\n"
    msg += "<b>Signal Breakdown:</b>\n"
    labels = {"midnight_open": "MO     ", "asia_range": "Asia   ", "london_break": "London "}
    for key, (vote, direction, detail) in bias["signals"].items():
        icon = vote_icons.get(vote.strip(), "⚪")
        msg += icon + " " + labels[key] + " <i>" + detail + "</i>\n"
    msg += "--------------------\n"
    msg += "<b>1H iFVGs +/-" + str(IFVG_RANGE_PTS) + "pts:</b>\n"
    if not ifvgs:
        msg += "• None nearby\n"
    else:
        for z in ifvgs:
            zone_icon = "🟩" if z["relation"] == "below" else "🟥"
            side = "Support (up)" if z["relation"] == "below" else "Resistance (down)"
            msg += zone_icon + " " + str(round(z["bottom"], 2)) + " - " + str(round(z["top"], 2)) + "  " + side + "  (" + str(round(z["dist"])) + "pts)\n"
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
        return name + ": " + str(round(level, 2)) + " (" + str(round(abs(diff))) + "pts " + arrow + ")"

    bias_icon = "🟢" if "BULLISH" in bias["overall"] else "🔴" if "BEARISH" in bias["overall"] else "⚪"
    status_icon = "✅" if "respected" in status else "⚠️" if "challenged" in status else "⚪"

    msg  = "--------------------\n"
    msg += "🔔 <b>NYO Update | " + date_str + "</b>\n"
    msg += "--------------------\n"
    msg += bias_icon + " <b>" + bias["overall"] + "</b>  |  📍 <b>" + str(round(current_price, 2)) + "</b>\n"
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

    # Insert iFVG section before the last two lines
    ifvg_section = "--------------------\n"
    ifvg_section += "<b>1H iFVGs +/-" + str(IFVG_RANGE_PTS) + "pts:</b>\n"
    for z in ifvgs:
        zone_icon = "🟩" if z["relation"] == "below" else "🟥"
        side = "Support (up)" if z["relation"] == "below" else "Resistance (down)"
        ifvg_section += zone_icon + " " + str(round(z["bottom"], 2)) + " - " + str(round(z["top"], 2)) + "  " + side + "  (" + str(round(z["dist"])) + "pts)\n"
        ifvg_section += "   " + z["target"] + "\n"

    # Insert before the last kill zone line
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
    msg += "Close: <b>" + str(round(current_price, 2)) + "</b>  MO: <b>" + str(round(midnight_open, 2)) + "</b>\n"
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

        # Add watermark
        try:
            draw = ImageDraw.Draw(img)
            watermark = "Smokey Bias | t.me/SmokeyNQBot"
            # Use default font
            font_size = max(16, img.width // 50)
            try:
                font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
            except Exception:
                font = ImageFont.load_default()

            # Get text size
            bbox = draw.textbbox((0, 0), watermark, font=font)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]

            # Position bottom right with padding
            x = img.width - text_w - 15
            y = img.height - text_h - 15

            # Draw shadow
            draw.text((x+2, y+2), watermark, font=font, fill=(0, 0, 0, 180))
            # Draw text
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
    # Verify file exists and has content
    if not image_path or not image_path.exists():
        print("  -> No screenshot file found, sending text only")
        send_telegram_text(caption)
        return
    if image_path.stat().st_size < 1000:
        print("  -> Screenshot file too small (" + str(image_path.stat().st_size) + " bytes), sending text only")
        send_telegram_text(caption)
        return

    compressed = compress_screenshot(image_path)

    # Verify compressed file
    if not compressed.exists() or compressed.stat().st_size < 1000:
        print("  -> Compressed file invalid, sending text only")
        send_telegram_text(caption)
        return

    # Clean caption of any problematic characters
    safe_caption = caption.replace("\\", "").replace('\"', '"')
    # Telegram caption max is 1024 chars
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
                    # Try without HTML parsing
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
    send_discord(safe_caption, compressed)

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
    send_discord(message)


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
    # Convert bold
    text = re.sub(r"<b>(.*?)</b>", r"****", text, flags=re.DOTALL)
    # Convert italic
    text = re.sub(r"<i>(.*?)</i>", r"**", text, flags=re.DOTALL)
    # Convert HTML entities
    text = text.replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    # Remove any remaining HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Clean up extra blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def send_discord(message, image_path=None):
    """Send message to Discord webhook."""
    if not DISCORD_WEBHOOK:
        return
    try:
        # Convert HTML to Discord markdown
        discord_msg = strip_html(message)
        # Discord has 2000 char limit
        if len(discord_msg) > 2000:
            discord_msg = discord_msg[:1997] + "..."

        if image_path and image_path.exists() and image_path.stat().st_size > 1000:
            # Send with image
            with open(image_path, "rb") as img:
                requests.post(DISCORD_WEBHOOK, data={
                    "content": discord_msg,
                }, files={"file": ("chart.jpg", img, "image/jpeg")}, timeout=30)
        else:
            # Send text only
            requests.post(DISCORD_WEBHOOK, json={
                "content": discord_msg,
            }, timeout=10)
        print("[" + datetime.now(ET).strftime("%H:%M:%S ET") + "] Discord sent.")
    except Exception as e:
        print("  -> Discord send error: " + str(e))


# JOBS

def run_morning_bias():
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running morning bias job...")
    windows = get_session_windows()
    try:
        # Try TradingView webhook levels first (accurate), fall back to Yahoo Finance
        tv = load_tv_levels()
        if tv.get("midnight_open") and tv.get("asia_high") and tv.get("london_high"):
            print("  -> Using TradingView webhook levels")
            midnight_open = tv["midnight_open"]
            asia_high     = tv["asia_high"]
            asia_low      = tv["asia_low"]
            london_high   = tv["london_high"]
            london_low    = tv["london_low"]
            london_close  = london_low  # approximate
            _             = None
        else:
            print("  -> No TV webhook levels found, using Yahoo Finance")
            midnight_open = get_midnight_open(windows["midnight_open_utc"])
            asia_high, asia_low, _ = get_session_hl(windows["asia_start_utc"], windows["asia_end_utc"])
            london_high, london_low, london_close = get_session_hl(windows["london_start_utc"], windows["london_end_utc"])
        pdh, pdl = get_previous_day_hl()
        current_price = get_current_price() or midnight_open
        screenshot = take_chart_screenshot()

        # Log what we have
        missing = []
        if not midnight_open: missing.append("midnight_open")
        if not asia_high: missing.append("asia_high")
        if not asia_low: missing.append("asia_low")
        if not london_high: missing.append("london_high")
        if not london_low: missing.append("london_low")
        if not current_price: missing.append("current_price")

        if missing:
            print("  -> Missing data: " + str(missing))

        # Only abort if we are missing critical levels (midnight open + at least one session)
        critical_missing = not midnight_open or not current_price or (not asia_high and not london_high)
        if critical_missing:
            caption = "NQ Bias Bot: Missing session data - " + str(missing)
            if screenshot and screenshot.exists():
                send_telegram_photo(screenshot, caption)
            else:
                send_telegram_text(caption)
            return

        # Fill any missing values with approximations
        if not asia_high and london_high:
            asia_high = london_high
            asia_low  = london_low
        if not london_high and asia_high:
            london_high = asia_high
            london_low  = asia_low

        bias = compute_bias(midnight_open, current_price, asia_high, asia_low, london_high, london_low, london_close)
        ifvgs = detect_ifvgs(current_price)

        today_state.update({
            "bias": bias["direction"], "score": bias["score"],
            "midnight_open": midnight_open,
            "asia_high": asia_high, "asia_low": asia_low,
            "london_high": london_high, "london_low": london_low,
            "pdh": pdh, "pdl": pdl,
            "date": datetime.now(ET).strftime("%Y-%m-%d"),
        })

        caption = build_morning_caption(current_price, midnight_open, asia_high, asia_low,
                                        london_high, london_low, pdh, pdl, bias, ifvgs)

        # Send teaser to free channel
        grade = bias.get("grade", "C")
        if grade == "A" and ifvgs:
            grade = "A+"
        send_teaser(bias["overall"], grade, datetime.now(ET).strftime("%a %b %d"))
        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, caption)
        else:
            caption += "\nChart screenshot unavailable."
            send_telegram_text(caption)

    except Exception as e:
        try:
            send_telegram_text("<b>Morning Bias Error:</b> " + str(e))
        except Exception:
            pass


def run_nyo_update():
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
        if screenshot and screenshot.exists():
            send_telegram_photo(screenshot, msg)
        else:
            send_telegram_text(msg)
    except Exception as e:
        try:
            send_telegram_text("<b>NYO Update Error:</b> " + str(e))
        except Exception:
            pass
def run_eod_score():
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running EOD score...")
    try:
        current_price = get_current_price()
        mo = today_state["midnight_open"]
        direction = today_state["bias"]
        if not current_price or not mo or not direction:
            send_telegram_text("EOD Score: No bias data for today.")
            return

        price_diff = current_price - mo  # positive = above MO, negative = below MO
        abs_diff   = abs(price_diff)

        # Scoring logic:
        # CHOPPY  - price closed within 75pts of MO either direction
        # WIN     - price moved 100+ pts in bias direction
        # FAILED  - price moved 100+ pts against bias direction
        if abs_diff <= 75:
            result_type = "choppy"
        elif direction == "bullish":
            result_type = "win" if price_diff >= 100 else "failed"
        elif direction == "bearish":
            result_type = "win" if price_diff <= -100 else "failed"
        else:
            result_type = "choppy"

        winrate_data = record_result_v2(direction, result_type)
        msg = build_eod_message_v2(direction, result_type, current_price, mo, price_diff, winrate_data)
        send_telegram_text(msg)
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


def run_weekend_recap():
    """Saturday morning - weekly recap and what to watch next week."""
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running weekend recap...")
    try:
        data = load_winrate()
        wins     = data["wins"]
        losses   = data["losses"]
        neutrals = data["neutrals"]
        total    = wins + losses

        # Get this week's history (last 5 entries)
        week_history = data["history"][-5:] if data["history"] else []
        week_wins   = sum(1 for r in week_history if r["result"] == "W")
        week_losses = sum(1 for r in week_history if r["result"] == "L")
        week_chops  = sum(1 for r in week_history if r["result"] == "C")
        week_streak = "".join(r["result"] for r in week_history) if week_history else ""

        now_et   = datetime.now(ET)
        date_str = now_et.strftime("%a %b %d")

        msg  = "--------------------\n"
        msg += "📅 <b>Weekly Recap | " + date_str + "</b>\n"
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

        send_telegram_text(msg)

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

    msg  = "📊 <b>Smokey Bias - Weekly Performance</b>\n"
    msg += "Week ending " + date_str + "\n"
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
    # Only run on 1st of month
    if now_et.day != 1:
        return

    print("\n[" + now_et.strftime("%Y-%m-%d %H:%M ET") + "] Running monthly report...")
    try:
        data = load_winrate()
        wins     = data["wins"]
        losses   = data["losses"]
        neutrals = data["neutrals"]
        total    = wins + losses
        history  = data["history"][-22:] if data["history"] else []  # ~1 month

        # Count results
        month_wins   = sum(1 for r in history if r["result"] == "W")
        month_losses = sum(1 for r in history if r["result"] == "L")
        month_chops  = sum(1 for r in history if r["result"] == "C")
        month_total  = month_wins + month_losses
        month_pct    = round(month_wins / month_total * 100) if month_total > 0 else 0
        month_streak = "".join(r["result"] for r in history)

        # Best bias direction
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


def run_trade_of_week():
    """Friday EOD - highlight the best bias delivery of the week."""
    print("\n[" + datetime.now(ET).strftime("%Y-%m-%d %H:%M ET") + "] Running trade of the week...")
    try:
        data = load_winrate()
        week_history = data["history"][-5:] if data["history"] else []
        wins_this_week = [r for r in week_history if r["result"] == "W"]

        date_str = datetime.now(ET).strftime("%b %d")
        msg  = "🏆 <b>Bias of the Week | " + date_str + "</b>\n"
        msg += "--------------------\n"

        if not wins_this_week:
            msg += "No winning biases this week\n"
            msg += "Chop week - market was indecisive\n"
        else:
            # Show the wins
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

        send_telegram_text(msg)

    except Exception as e:
        try:
            send_telegram_text("<b>Trade of Week Error:</b> " + str(e))
        except Exception:
            pass

# SCHEDULER

def main():
    print("Smokey Bias Bot - scheduled daily:")
    print("  11:00 UTC (07:00 ET) - Macro news")
    print("  12:00 UTC (08:00 ET) - Morning bias + chart")
    print("  13:00 UTC (09:00 ET) - NYO update + chart")
    print("  20:00 UTC (16:00 ET) - EOD score + win rate")

    # Weekday only jobs
    for day in [schedule.every().monday, schedule.every().tuesday, schedule.every().wednesday,
                schedule.every().thursday, schedule.every().friday]:
        day.at("11:00").do(run_news_job)
        day.at("12:30").do(run_morning_bias)
        day.at("13:00").do(run_nyo_update)
        day.at("20:00").do(run_eod_score)

    # Weekend jobs
    schedule.every().friday.at("21:00").do(run_trade_of_week)
    schedule.every().saturday.at("14:00").do(run_weekend_recap)
    schedule.every().sunday.at("14:00").do(run_weekly_performance)

    # Monthly report - runs daily but checks if 1st of month
    schedule.every().day.at("12:30").do(run_monthly_report)
    # Uncomment to test immediately
    # run_news_job()
    # run_morning_bias()
    # run_nyo_update()
    # run_eod_score()

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
