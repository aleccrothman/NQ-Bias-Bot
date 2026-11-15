import os
import json
import random
import asyncio
import aiohttp
import discord
from discord.ext import commands
from datetime import datetime, time
import pytz
import redis

_version = "smokesignals-ict2022-v1"

# ── Config ────────────────────────────────────────────────────────────────────
DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
STRATEGY_WEBHOOK_URL = os.environ["STRATEGY_WEBHOOK_URL"]  # #smoke-signals webhook
POST_DAYS = {0, 3}  # Monday=0, Thursday=3
POST_TIME = time(18, 0)  # 6:00 PM ET
TIMEZONE = pytz.timezone("America/New_York")

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL = os.environ["REDIS_URL"]
r = redis.from_url(REDIS_URL, decode_responses=True)
REDIS_KEY = "smokesignals:state"

# ── ICT Concepts Library ───────────────────────────────────────────────────────
ICT_CONCEPTS = [
    {
        "title": "🕯️ Fair Value Gap (FVG)",
        "category": "Price Delivery",
        "color": 0x00BFFF,
        "definition": "A 3-candle imbalance where the wicks of candle 1 and candle 3 do not overlap, leaving a gap in price that the market tends to revisit.",
        "how_to_use": "Mark the gap between the high of candle 1 and the low of candle 3 (bullish FVG) or the low of candle 1 and high of candle 3 (bearish FVG). Look for price to return and react from the 50% equilibrium of the gap.",
        "nq_tip": "On NQ, FVGs on the 5m and 15m during the NY Open are high-probability entry zones when aligned with HTF bias.",
        "timeframes": "5m · 15m · 1H",
        "type": "Entry Model",
    },
    {
        "title": "🌙 Midnight Open (MNO)",
        "category": "Key Levels",
        "color": 0x9B59B6,
        "definition": "The price level at exactly 12:00 AM New York time. ICT considers this a significant reference point for intraday price delivery.",
        "how_to_use": "Mark the Midnight Open as a horizontal line. Price often uses it as a magnet, support, or resistance. A displacement above/below MNO signals directional intent for the session.",
        "nq_tip": "If NQ opens the NY session above the Midnight Open, bias is bullish. Below = bearish. Combine with the daily bias for confluence.",
        "timeframes": "1m · 5m · 15m",
        "type": "Reference Level",
    },
    {
        "title": "💧 Liquidity Sweep",
        "category": "Market Structure",
        "color": 0x1ABC9C,
        "definition": "A move that briefly exceeds a significant high or low (where stop losses and orders cluster) before reversing sharply. Also called a stop hunt.",
        "how_to_use": "Identify swing highs/lows where retail traders place stops. Wait for price to sweep beyond that level with a wick, then look for a displacement candle confirming reversal.",
        "nq_tip": "The London session frequently sweeps Asia highs/lows on NQ. A London sweep of the Asia High followed by displacement is the core of the SmokeyNQ bias model.",
        "timeframes": "15m · 1H · 4H",
        "type": "Setup Trigger",
    },
    {
        "title": "📍 Optimal Trade Entry (OTE)",
        "category": "Entry Model",
        "color": 0xF39C12,
        "definition": "A Fibonacci-based entry zone between the 61.8% and 79% retracement of a swing move. ICT considers this the highest-probability entry after displacement.",
        "how_to_use": "After a confirmed displacement and market structure shift, draw Fibonacci from the swing low to swing high (bullish) or vice versa. Enter between 61.8–79% retracement.",
        "nq_tip": "On a bullish NQ setup, wait for price to displace up, then pull back into the OTE zone (61.8–79%) before targeting the swing high or higher.",
        "timeframes": "5m · 15m · 1H",
        "type": "Entry Model",
    },
    {
        "title": "🏛️ Order Block (OB)",
        "category": "Smart Money Concepts",
        "color": 0xE74C3C,
        "definition": "The down-close candle(s) right before a surge higher that leaves an imbalance (bullish OB), or the up-close candle(s) before a displacement lower (bearish OB). ICT calls it a change in the state of delivery, not simply the last opposing candle (2022 Mentorship, Ep 9, 12 & 18).",
        "how_to_use": "Only mark it when the move away displaced and left an FVG. Watch three levels: the open, the mean threshold (50% of the candle), and the far extreme. For a bearish OB, the high is the least likely level to be traded to.",
        "nq_tip": "Bullish order blocks on the 15m during the NY Open that align with HTF bullish bias are among the strongest setups on NQ.",
        "timeframes": "15m · 1H · 4H",
        "type": "Entry Zone",
    },
    {
        "title": "📊 Market Structure Shift (MSS)",
        "category": "Market Structure",
        "color": 0x2ECC71,
        "definition": "A change in the prevailing swing structure — a bearish MSS breaks a prior swing low in a bullish trend; a bullish MSS breaks a prior swing high in a bearish trend.",
        "how_to_use": "In a downtrend, wait for a bullish MSS (break of a swing high) on the entry timeframe to confirm a reversal. This is your signal to look for longs using OTE or FVG.",
        "nq_tip": "A bullish MSS on the 5m after a liquidity sweep of a session low is a textbook SmokeyNQ long setup during the NY Open.",
        "timeframes": "1m · 5m · 15m",
        "type": "Confirmation Signal",
    },
    {
        "title": "⚖️ Equilibrium (EQ)",
        "category": "Price Delivery",
        "color": 0x3498DB,
        "definition": "The 50% midpoint of any price range — a swing, a candle, a gap, or a dealing range. ICT views price as constantly seeking equilibrium before continuing.",
        "how_to_use": "Mark the 50% level of FVGs, order blocks, or weekly ranges. Price often reacts at EQ before continuing in the trend direction. Use it to fine-tune entries within a zone.",
        "nq_tip": "When NQ trades into a bullish FVG, the 50% of the gap (EQ) is the ideal entry point with the tightest stop and best R:R.",
        "timeframes": "All timeframes",
        "type": "Reference Level",
    },
    {
        "title": "🗓️ Power of 3 (PO3)",
        "category": "Price Delivery",
        "color": 0xE67E22,
        "definition": "ICT's framework describing how price moves in 3 phases: Accumulation (range), Manipulation (false move/sweep), and Distribution (true directional move).",
        "how_to_use": "In the NY session, expect an early manipulation move (sweep of a key level) followed by the true trend direction. Don't chase the first move — wait for the manipulation to complete.",
        "nq_tip": "The first 15–30 minutes of the NY Open on NQ is often the manipulation phase. The real move begins after 9:30–10:00 AM ET once the sweep is confirmed.",
        "timeframes": "Daily · 4H · 1H",
        "type": "Framework",
    },
    {
        "title": "🕐 Kill Zone (KZ)",
        "category": "Time & Price",
        "color": 0xC0392B,
        "definition": "Specific time windows when institutional order flow is most active and high-probability setups occur. ICT frames London as 2–5 AM ET, and in the 2022 Mentorship he hunts NY index setups from 8:30 to 11:00 AM ET, with a second window after lunch (1:30–4 PM).",
        "how_to_use": "Only take setups inside your window. Outside it, price is often choppy. ICT: no new entries during NY lunch (12–1 PM), and expect at most 2 setups in the morning and 2 in the afternoon (2022 Mentorship, Ep 3 & 16).",
        "nq_tip": "SmokeyNQ trades the NY Open Kill Zone (9–11 AM ET). This is when NQ delivers its cleanest moves off key levels with the most follow-through.",
        "timeframes": "Intraday",
        "type": "Time Filter",
    },
    {
        "title": "📈 Premium & Discount Arrays",
        "category": "Price Delivery",
        "color": 0x8E44AD,
        "definition": "Price above the 50% equilibrium of a range is Premium (expensive — look to sell). Price below 50% is Discount (cheap — look to buy). Smart money buys discount and sells premium.",
        "how_to_use": "Define your dealing range (weekly, daily, or session). Draw the 50% level. In a bullish bias, only look for longs when price is in Discount. In bearish bias, only shorts from Premium.",
        "nq_tip": "If NQ is bullish on the day but price is in Premium (above the daily 50%), wait for a pullback to Discount before entering. Don't chase premium entries.",
        "timeframes": "Daily · 4H · 1H",
        "type": "Framework",
    },
    {
        "title": "🔄 Breaker Block",
        "category": "Smart Money Concepts",
        "color": 0x16A085,
        "definition": "A swing pattern where the opposing liquidity is taken first, e.g. a high, a low, then a higher high that runs buy stops before a break lower. The candle at the middle swing becomes the breaker when price returns to it (2022 Mentorship, Ep 10 & 37).",
        "how_to_use": "When price trades back into the breaker, look for a reaction in the new direction. ICT expects price to mostly respect the near half of the breaker candle, and places his stop just beyond the candle.",
        "nq_tip": "Breaker blocks on NQ's 15m are powerful because they represent a trap — retail traders expect the OB to hold, but smart money has already flipped it.",
        "timeframes": "15m · 1H · 4H",
        "type": "Entry Zone",
    },
    {
        "title": "📉 Inversion Fair Value Gap (iFVG)",
        "category": "Price Delivery",
        "color": 0xD35400,
        "definition": "A Fair Value Gap that price has fully traded through and closed beyond. Once violated, the gap inverts and acts as support (formerly bearish FVG) or resistance (formerly bullish FVG).",
        "how_to_use": "Mark FVGs on your chart. When price closes fully beyond an FVG, label it as an iFVG. On a retest of the iFVG zone, look for a reaction in the direction of the new trend.",
        "nq_tip": "iFVGs are a core level in the SmokeyNQ confluence indicator. A bullish iFVG on the 15m that holds during a pullback is a strong long entry during the NY session.",
        "timeframes": "5m · 15m · 1H",
        "type": "Entry Zone",
    },
    {
        "title": "🏔️ Previous Day High/Low (PDH/PDL)",
        "category": "Key Levels",
        "color": 0x7F8C8D,
        "definition": "The high and low of the previous trading day. These are critical reference levels that act as liquidity pools — resting orders and stops accumulate above PDH and below PDL.",
        "how_to_use": "Mark PDH and PDL every morning before the session. A sweep of PDH/PDL followed by a rejection is a high-probability reversal setup. A clean breakout with displacement signals continuation.",
        "nq_tip": "A sweep of PDH during the NY Open followed by a bearish FVG is a textbook short setup on NQ. Conversely, a PDL sweep with a bullish MSS = long.",
        "timeframes": "Daily · 1H · 15m",
        "type": "Reference Level",
    },
    {
        "title": "🌍 Asia Range",
        "category": "Session Levels",
        "color": 0x27AE60,
        "definition": "The high and low formed during the Asian trading session (roughly 8 PM – 2 AM ET). This range defines where liquidity is resting for London and NY to target.",
        "how_to_use": "Mark the Asia High and Asia Low every day. Expect London or NY to sweep one of these levels before the true directional move begins. The swept side tells you the direction.",
        "nq_tip": "If London sweeps the Asia Low on NQ and then displaces bullish, that's your confirmation for a long bias going into the NY Open. This is the foundation of the daily SmokeyNQ bias model.",
        "timeframes": "15m · 1H",
        "type": "Reference Level",
    },
    {
        "title": "🎯 Liquidity Pools",
        "category": "Market Structure",
        "color": 0x2980B9,
        "definition": "Areas where a high concentration of stop orders rest — above swing highs (buy stops) and below swing lows (sell stops). Smart money targets these pools to fill large orders.",
        "how_to_use": "Identify equal highs, equal lows, trendline touches, and obvious swing points. These are liquidity pools. Expect price to raid these levels before reversing. Trade WITH the raid, not before it.",
        "nq_tip": "Equal highs on NQ's 15m chart are a magnet. Don't place your long stop just below equal lows — that's exactly where price will sweep before going higher.",
        "timeframes": "15m · 1H · 4H",
        "type": "Framework",
    },
    {
        "title": "📐 Dealing Range",
        "category": "Price Delivery",
        "color": 0x00CED1,
        "definition": "A defined price range between a significant high and low used to determine Premium vs Discount zones. Can be weekly, daily, or session-based.",
        "how_to_use": "Define your range each session (or use weekly range). Split at 50% EQ. Only buy in Discount, only sell in Premium, aligned with HTF bias.",
        "nq_tip": "Use Monday's high-to-low as the weekly dealing range for NQ. If Tuesday opens in Discount and bias is bullish, look for longs all week.",
        "timeframes": "Weekly · Daily · 4H",
        "type": "Framework",
    },
    {
        "title": "🧲 Consequent Encroachment (CE)",
        "category": "Price Delivery",
        "color": 0xFF6B6B,
        "definition": "The 50% midpoint of a Fair Value Gap. Price often draws directly to this exact level before continuing. It is the equilibrium within the imbalance.",
        "how_to_use": "Mark the exact 50% of any FVG. Use CE as your limit order entry within the gap rather than the full gap range for a tighter, more precise entry.",
        "nq_tip": "On NQ, entering at the CE of a 15m bullish FVG instead of the gap top gives you better R:R and a smaller stop loss.",
        "timeframes": "5m · 15m · 1H",
        "type": "Reference Level",
    },
    {
        "title": "⚡ Displacement",
        "category": "Market Structure",
        "color": 0xF1C40F,
        "definition": "A strong, impulsive candle (or series of candles) that moves price decisively in one direction, breaking structure and leaving FVGs behind. The hallmark of institutional entry.",
        "how_to_use": "Look for a large-bodied candle with little wick that closes beyond a key level. This signals institutional participation and validates your directional bias.",
        "nq_tip": "A bullish displacement candle on the 5m breaking above Asia High during London confirms the bias for NQ long during the NY Open.",
        "timeframes": "1m · 5m · 15m",
        "type": "Confirmation Signal",
    },
    {
        "title": "🔁 Mitigation Block",
        "category": "Smart Money Concepts",
        "color": 0xA569BD,
        "definition": "A candle or group of candles that originated a move that later created a liquidity void. When price returns to mitigate (fill) that inefficiency, it often reacts strongly.",
        "how_to_use": "Identify where a strong move originated. Mark that origin candle. When price returns to mitigate the move, look for entry signals aligned with HTF bias.",
        "nq_tip": "On NQ, mitigation blocks from the previous day's impulse moves often act as strong support/resistance when revisited during the following session.",
        "timeframes": "15m · 1H · 4H",
        "type": "Entry Zone",
    },
    {
        "title": "📏 Standard Deviation (SD)",
        "category": "Price Delivery",
        "color": 0x48C9B0,
        "definition": "ICT uses standard deviation projections to forecast price targets. -1SD, +1SD, and +2SD from a range midpoint often align with key turning points and target levels.",
        "how_to_use": "Mark the range midpoint, then project standard deviation levels above and below. Use these as target levels or reversal zones rather than arbitrary TP levels.",
        "nq_tip": "After a bullish displacement from Discount on NQ, the +1SD projection often targets the Premium zone — giving a clean, measured target for the trade.",
        "timeframes": "All timeframes",
        "type": "Reference Level",
    },
    {
        "title": "🌊 HTF Bias",
        "category": "Market Structure",
        "color": 0x5DADE2,
        "definition": "The directional bias established on the Daily, 4H, or 1H chart that defines which direction you trade on lower timeframes. You only take trades aligned with HTF bias.",
        "how_to_use": "Each morning, analyze the Daily and 4H chart. Determine if price is in HTF Premium or Discount and whether structure is bullish or bearish. Only trade in that direction.",
        "nq_tip": "SmokeyNQ establishes HTF bias every morning by checking if NQ is above/below MNO and key weekly levels before taking any 5m entry during the NY Open.",
        "timeframes": "Daily · 4H · 1H",
        "type": "Framework",
    },
    {
        "title": "🔍 IPDA",
        "category": "Price Delivery",
        "color": 0xF0B27A,
        "definition": "Interbank Price Delivery Algorithm — ICT's theory that price is algorithmically driven to target specific liquidity pools in a predictable 20/40/60 day cycle.",
        "how_to_use": "Study 20-day, 40-day, and 60-day lookback periods. IPDA cycles through these periods targeting old highs/lows as liquidity. Mark prior range highs/lows accordingly.",
        "nq_tip": "NQ's 20-day high/low are key IPDA reference levels. A sweep of the 20-day low followed by a bounce is a high-probability algorithmic reversal point.",
        "timeframes": "Daily · Weekly",
        "type": "Framework",
    },
    {
        "title": "📆 Weekly Profile",
        "category": "Time & Price",
        "color": 0x82E0AA,
        "definition": "ICT's model for how a weekly candle typically forms: Monday sets direction, Tuesday extends or reverses, Wednesday is the pivot, Thursday retraces, Friday delivers.",
        "how_to_use": "Use the weekly profile to anticipate what price should do each day. Monday's low is often the week's low in a bullish week. Don't fade Monday's move on Tuesday.",
        "nq_tip": "If NQ forms a bullish Monday, look for Tuesday continuation or a brief Wednesday dip before Thursday's push to weekly highs — classic bullish weekly profile.",
        "timeframes": "Daily · Weekly",
        "type": "Framework",
    },
    {
        "title": "🎪 Judas Swing",
        "category": "Market Structure",
        "color": 0xEC407A,
        "definition": "A false move at the open of a session designed to trap retail traders in the wrong direction before the true move begins. A deliberate manipulation move.",
        "how_to_use": "At the NY Open, if price initially spikes against the HTF bias, wait for it to reverse. This initial false move is the Judas Swing — trade the reversal, not the initial move.",
        "nq_tip": "NQ often drops the first 5–10 minutes of the 9:30 AM open to sweep stops before reversing in the true direction. Wait for the sweep and displacement.",
        "timeframes": "1m · 5m · 15m",
        "type": "Setup Trigger",
    },
    {
        "title": "🏁 New Week Opening Gap (NWOG)",
        "category": "Key Levels",
        "color": 0x26C6DA,
        "definition": "The gap between Friday's closing price and Sunday's opening price in futures markets. ICT treats this as a significant reference level price gravitates toward.",
        "how_to_use": "Mark the NWOG every Sunday night. It often acts as a magnet during the week — price frequently returns to close the gap before continuing its trend.",
        "nq_tip": "NQ futures gap Sunday evening. Mark the gap open and Friday close. A bullish week often fills the NWOG early before pushing to weekly highs.",
        "timeframes": "Daily · 4H",
        "type": "Reference Level",
    },
    {
        "title": "📌 Session High / Session Low",
        "category": "Session Levels",
        "color": 0xB0BEC5,
        "definition": "The highest and lowest price reached during a specific session (Asia, London, NY). These levels act as liquidity targets for the subsequent session.",
        "how_to_use": "Mark the high and low of each session as it closes. The next session frequently targets one of these levels for a sweep before establishing its true direction.",
        "nq_tip": "The NY session low is often the target for Asia to sweep overnight, setting up a bullish London/NY move the following day. Mark it before you close your charts.",
        "timeframes": "15m · 1H",
        "type": "Reference Level",
    },
    {
        "title": "🧩 Turtle Soup",
        "category": "Market Structure",
        "color": 0xA5D6A7,
        "definition": "A reversal pattern where price sweeps just beyond a 20-day or key swing high/low (trapping breakout traders) before sharply reversing back.",
        "how_to_use": "Identify a significant 20-day high or low. When price breaks just beyond it with thin follow-through and reverses, that's the Turtle Soup. Enter on the reversal candle.",
        "nq_tip": "A Turtle Soup on NQ's 20-day high forming during the NY Open kill zone with a bearish FVG is a high R:R short opportunity.",
        "timeframes": "Daily · 4H · 1H",
        "type": "Setup Trigger",
    },
    {
        "title": "🎯 BSL / SSL",
        "category": "Market Structure",
        "color": 0x80CBC4,
        "definition": "Buy Side Liquidity (BSL) = resting buy stops above old highs. Sell Side Liquidity (SSL) = resting sell stops below old lows. Price is always seeking one of these pools.",
        "how_to_use": "Each trade should have a clear BSL or SSL target. Mark all old highs (BSL) and old lows (SSL). Your TP should sit just above BSL or just below SSL.",
        "nq_tip": "On a bullish NQ trade, your target is the nearest BSL — equal highs, PDH, or a swing high. Don't exit at random; let the algorithm target liquidity.",
        "timeframes": "All timeframes",
        "type": "Framework",
    },
    {
        "title": "🌀 Reaccumulation vs Distribution",
        "category": "Market Structure",
        "color": 0xCE93D8,
        "definition": "Reaccumulation = a pause/consolidation within an uptrend before continuation. Distribution = a pause before reversal. Identifying which one prevents being trapped.",
        "how_to_use": "In an uptrend, tight consolidation near highs without a liquidity sweep below = likely reaccumulation. A sweep of lows + failure to make new highs = distribution.",
        "nq_tip": "When NQ ranges for 30–60 minutes mid-session, determine if it's reaccumulating (bullish continuation) or distributing (reversal incoming) before adding positions.",
        "timeframes": "5m · 15m · 1H",
        "type": "Framework",
    },
    # ── ICT 2022 Mentorship series (paraphrased from the free YouTube mentorship) ──
    {
        "title": "🧭 The ICT 2022 Model — Full Sequence",
        "category": "ICT 2022 Mentorship",
        "color": 0x00BFFF,
        "definition": "The one model ICT teaches across the 2022 Mentorship: know the draw on liquidity, wait for price to run a pool of stops, then a market structure shift with displacement that leaves a fair value gap.",
        "how_to_use": "1) Mark buy-side and sell-side liquidity. 2) Wait for one side to get swept. 3) Look for displacement through the short-term swing (MSS). 4) Enter on the retrace into the FVG left behind. 5) Target the opposite liquidity.",
        "nq_tip": "SmokeyNQ uses the same building blocks (sweep, displacement, FVG). His trigger is the iFVG, price closing through an FVG and flipping it, framed inside a higher-timeframe FVG during the 9–11 AM ET window.",
        "timeframes": "15m bias · 5m–1m entry",
        "type": "Entry Model",
        "source": "ICT 2022 Mentorship · Ep 2, 3, 6, 12",
    },
    {
        "title": "⏰ NY Session Windows & the Lunch Rule",
        "category": "ICT 2022 Mentorship",
        "color": 0xC0392B,
        "definition": "ICT splits the index day in two: a morning session (8:30 AM–noon, best before 11), NY lunch (12–1 PM), and an afternoon session (1:30–4 PM). Time of day comes before price.",
        "how_to_use": "No new entries during lunch. You can take profits or let a resting limit fill. Expect at most 2 setups in the AM and 2 in the PM, and don't force a fifth. Be positioned before 11 and ride into lunch.",
        "nq_tip": "SmokeyNQ keeps it tighter: 9–11 AM ET only, one focused window, then done for the day. Same idea, less screen time and fewer chances to overtrade.",
        "timeframes": "Intraday",
        "type": "Time Filter",
        "source": "ICT 2022 Mentorship · Ep 2, 3, 5, 16",
    },
    {
        "title": "🧠 Daily Bias = Range Expansion From the Open",
        "category": "ICT 2022 Mentorship",
        "color": 0x5DADE2,
        "definition": "ICT's answer to the most-asked question: bias is simply whether today's daily range is more likely to expand higher or lower than the opening price. You don't need to predict the close.",
        "how_to_use": "Start with the weekly candle (higher or lower?), then use daily swing highs and lows to find the draw on liquidity. Hunt only the bias side, and stay with it until a key level is clearly taken against you.",
        "nq_tip": "Bias is a filter, not a guarantee. If the NY open gives you nothing on your side, the right trade is no trade.",
        "timeframes": "Weekly · Daily",
        "type": "Framework",
        "source": "ICT 2022 Mentorship · Ep 2, 7, 10, 18",
    },
    {
        "title": "🔺 3-Candle Swing Points",
        "category": "ICT 2022 Mentorship",
        "color": 0x7F8C8D,
        "definition": "A swing high is a candle whose high is above both the candle before and the candle after it; a swing low is the mirror. Just three candles.",
        "how_to_use": "Use 3-candle swings to mark short-term highs and lows, where the stops sit. ICT says skip 5-candle fractal indicators, because by the time they print you've missed the move.",
        "nq_tip": "The short-term swing that formed right before the sweep is the one displacement needs to break for a valid shift.",
        "timeframes": "All timeframes",
        "type": "Reference Level",
        "source": "ICT 2022 Mentorship · Ep 10, 16",
    },
    {
        "title": "🎯 Internal vs External Range Liquidity",
        "category": "ICT 2022 Mentorship",
        "color": 0x1ABC9C,
        "definition": "External range liquidity means the stops beyond a range's high or low. Internal range liquidity means the imbalances (FVGs) inside the range. Price tends to travel from one to the other.",
        "how_to_use": "After a run on external liquidity, expect price to reach for an internal FVG, and vice versa. On a trade, take the first partial at the internal target and hold the runner for the external one.",
        "nq_tip": "Short from premium: first target is the move back into discount or the nearest FVG; runner aims at equal lows or the previous day's low.",
        "timeframes": "15m · 1H",
        "type": "Framework",
        "source": "ICT 2022 Mentorship · Ep 3, 6",
    },
    {
        "title": "🪤 Relative Equal Highs & Lows",
        "category": "ICT 2022 Mentorship",
        "color": 0x2980B9,
        "definition": "Two or more highs (or lows) at nearly the same price. Retail traders read them as strong resistance or support and park stops just beyond them, so ICT treats them as engineered liquidity.",
        "how_to_use": "Mark them on the 15m. Expect them to get run before the real move. If equal highs sit above an older single high, use the equal highs as the target.",
        "nq_tip": "Never put your own stop just past equal highs or lows. That's exactly where the sweep happens.",
        "timeframes": "15m · 1H · Daily",
        "type": "Setup Trigger",
        "source": "ICT 2022 Mentorship · Ep 2, 3, 5",
    },
    {
        "title": "🏗️ Short, Intermediate & Long-Term Highs",
        "category": "ICT 2022 Mentorship",
        "color": 0x2ECC71,
        "definition": "ICT's 'precision' market structure: an intermediate-term high sits between two short-term highs, and these tend to form when price rebalances an FVG. It replaces simple higher-high/higher-low thinking.",
        "how_to_use": "If an intermediate-term high is not higher than the short-term highs around it, the market is weak. If the key swing your idea depends on gets violated, cancel the idea and don't re-force it.",
        "nq_tip": "Ask ICT's two questions before every session: is price going up for stops or to fill an imbalance, or down for stops or to fill an imbalance?",
        "timeframes": "1H · 15m",
        "type": "Framework",
        "source": "ICT 2022 Mentorship · Ep 12",
    },
    {
        "title": "🎚️ Mean Threshold",
        "category": "ICT 2022 Mentorship",
        "color": 0xE74C3C,
        "definition": "The 50% level of an order block candle. Together with the candle's open and its far extreme, it's one of the three sensitive levels ICT watches.",
        "how_to_use": "Run a fib across the order block candle. A reaction at the open or mean threshold keeps the block valid. Price trading through the far extreme invalidates it.",
        "nq_tip": "Use it like CE for order blocks: a tighter, more precise reference than the whole candle.",
        "timeframes": "15m · 1H · Daily",
        "type": "Reference Level",
        "source": "ICT 2022 Mentorship · Ep 21, 35",
    },
    {
        "title": "🔀 SMT Divergence (NQ vs ES)",
        "category": "ICT 2022 Mentorship",
        "color": 0x9B59B6,
        "definition": "When correlated indices disagree at a swing. Example: NQ makes a lower low but ES doesn't, which hints that the stronger index is being accumulated.",
        "how_to_use": "Overlay ES on NQ and compare the swing lows (or highs). ICT warns these show up around 8:30, 9:30 and news, then vanish as the markets resync, so SMT only helps if you already know the draw.",
        "nq_tip": "Use it as confirmation at your level during the open, never as a stand-alone entry.",
        "timeframes": "1m · 5m · 15m",
        "type": "Confirmation Signal",
        "source": "ICT 2022 Mentorship · Ep 35, 38",
    },
    {
        "title": "📰 8:30 News & the Economic Calendar",
        "category": "ICT 2022 Mentorship",
        "color": 0xF39C12,
        "definition": "At 8:30 AM ET the news embargo lifts and the algorithm starts seeking liquidity, sometimes waiting until the 9:30 open to hit it. ICT checks ForexFactory daily: red is high impact.",
        "how_to_use": "Know what's on the calendar before you trade. Expect a build-up before the number and the real move after. ICT tells students to sit out FOMC and NFP and study them in hindsight instead.",
        "nq_tip": "If a red-folder event blows up your read, close the charts and come back later. Forcing trades after an invalidated news read is how accounts get hurt.",
        "timeframes": "Intraday",
        "type": "Time Filter",
        "source": "ICT 2022 Mentorship · Ep 10, 23, 25, 41",
    },
    {
        "title": "🌓 Midnight Open & the Judas Move",
        "category": "ICT 2022 Mentorship",
        "color": 0x8E44AD,
        "definition": "ICT frames the day off the NY midnight opening price. Bearish days ideally rally above the midnight open first (the Judas move) and then sell off; bullish days dip below it to form the low, then rally.",
        "how_to_use": "Mark the midnight open. On a bearish bias, wait for the rally above it to fail; on a bullish bias, wait for the dip below it to reverse. If price can't even get back to the opening price, the bias side is very strong.",
        "nq_tip": "This is the 'why' behind SmokeyNQ's Midnight Open tool: premium above it is where shorts get built, discount below it is where longs get built.",
        "timeframes": "1m · 5m · 15m",
        "type": "Reference Level",
        "source": "ICT 2022 Mentorship · Ep 18, 21, 25, 38",
    },
    {
        "title": "🍽️ Lunch Lows & the PM Continuation",
        "category": "ICT 2022 Mentorship",
        "color": 0x16A085,
        "definition": "On a bullish day that consolidates through NY lunch, the lunch lows often get swept before the afternoon continuation higher (and the mirror when bearish). Around 3 PM the algorithm often pushes toward the remaining draw.",
        "how_to_use": "Mark the 12–1 PM range. Wait for the sweep of the side against your bias after 1:30, then look for the shift and the FVG entry. ICT also says that after a big overnight move, skip the morning and wait for this.",
        "nq_tip": "SmokeyNQ doesn't trade the PM; he's done by 11. This is ICT's extra window, worth knowing even if it isn't part of your routine.",
        "timeframes": "5m · 15m",
        "type": "Setup Trigger",
        "source": "ICT 2022 Mentorship · Ep 9, 30",
    },
    {
        "title": "🥞 Stacked FVGs",
        "category": "ICT 2022 Mentorship",
        "color": 0xD35400,
        "definition": "When two fair value gaps sit one above the other, ICT enters on the one closer to price but sizes his stop so a spike into the second gap won't take him out.",
        "how_to_use": "Note both gaps before entering. Price will often overrun a small FVG to reach a larger one, so if the near gap fails, the bigger gap is the next likely reaction.",
        "nq_tip": "Before you place the limit, ask: if it overshoots into the next gap, does my stop survive? If not, size down or pass.",
        "timeframes": "1m · 5m · 15m",
        "type": "Entry Zone",
        "source": "ICT 2022 Mentorship · Ep 21, 41",
    },
    {
        "title": "📐 Fib Projection Targets",
        "category": "ICT 2022 Mentorship",
        "color": 0x48C9B0,
        "definition": "ICT's swing-target method: measure the leg and project the same distance from the fulcrum swing to find a measured-move objective.",
        "how_to_use": "Anchor the fib on the highest body (open or close, not the wick) of the leg and drag to the low, then project that distance below the fulcrum low for shorts (mirror for longs).",
        "nq_tip": "Use projections as a runner target only after the first partial is banked at a liquidity level.",
        "timeframes": "15m · 1H",
        "type": "Reference Level",
        "source": "ICT 2022 Mentorship · Ep 16",
    },
    {
        "title": "🧮 Position Sizing the ICT Way",
        "category": "ICT 2022 Mentorship",
        "color": 0x3498DB,
        "definition": "Size from the stop, not the other way around. ICT's example: $10,000 × 1% = $100 risk. With a 9-point stop that's about $11 a point, too small for an ES mini ($50/pt), so 2 micros ($5/pt each) = $90 risk.",
        "how_to_use": "Risk ÷ stop distance in points = dollars per point you can afford, then divide by the contract multiplier. NQ mini is $20/pt, MNQ is $2/pt. Round down, never up.",
        "nq_tip": "While learning, ICT says to risk well under 1% (about 0.25–0.5%). On prop accounts, size off your drawdown limit, not the account size.",
        "timeframes": "Every trade",
        "type": "Risk Management",
        "source": "ICT 2022 Mentorship · Ep 7, 41",
    },
    {
        "title": "🛡️ After a Loss: Cut Risk in Half",
        "category": "ICT 2022 Mentorship",
        "color": 0xC0392B,
        "definition": "ICT's drawdown rule: after a loss, halve your risk (1% to 0.5%). After another loss, halve again (0.25%). Only go back to full risk once you've made back 50% of what you lost.",
        "how_to_use": "Three straight losses then cost about 1.75% instead of 3%+ from doubling up. ICT calls revenge trading the loser's cycle, and says to treat drawdown like a loan you'll collect interest on.",
        "nq_tip": "SmokeyNQ's own rule stacks on top: max 2 losses a day, only 1 if the loss came on an A+ setup. A loss is a business expense, not something to win back today.",
        "timeframes": "Every session",
        "type": "Risk Management",
        "source": "ICT 2022 Mentorship · Ep 41",
    },
    {
        "title": "🔒 When to Move Your Stop (50/75 Rule)",
        "category": "ICT 2022 Mentorship",
        "color": 0x27AE60,
        "definition": "ICT's systematic stop management: when price reaches 50% of the distance to your target, trim the stop's risk by 25%. At 75% of the way, move the stop to breakeven. Not before.",
        "how_to_use": "Jamming the stop to breakeven early gets you wicked out of good trades. Instead, keep checking: is price still reaching for the objective, and are FVGs and opposite-color candles still supporting it?",
        "nq_tip": "Pair it with partials: bank the first piece at the internal target, then let the stop rules manage the runner.",
        "timeframes": "Every trade",
        "type": "Risk Management",
        "source": "ICT 2022 Mentorship · Ep 41",
    },
    {
        "title": "📓 The Study Journal",
        "category": "ICT 2022 Mentorship",
        "color": 0x82E0AA,
        "definition": "ICT's core homework: build a journal of screenshot examples of the setup, marked up the same way every time.",
        "how_to_use": "For each example, note how far price ran, how long it took, and how much drawdown an entry would have taken. Re-read it when nothing feels like it's working; seeing the pattern repeat rebuilds conviction.",
        "nq_tip": "Backtest first, then demo, then live. ICT is blunt that watching videos isn't learning; marking up your own charts is.",
        "timeframes": "Weekends",
        "type": "Mindset",
        "source": "ICT 2022 Mentorship · Ep 3, 18, 24",
    },
]

# ── State Management (Redis) ──────────────────────────────────────────────────
def load_state():
    data = r.get(REDIS_KEY)
    if data:
        return json.loads(data)
    return {"used_indices": [], "last_post_date": None}

def save_state(state):
    r.set(REDIS_KEY, json.dumps(state))

def get_next_concept():
    state = load_state()
    used = state.get("used_indices", [])
    if len(used) >= len(ICT_CONCEPTS):
        used = []
    available = [i for i in range(len(ICT_CONCEPTS)) if i not in used]
    # Roll out the ICT 2022 Mentorship series first, then mix back into the full library.
    mentorship = [i for i in available if ICT_CONCEPTS[i].get("category") == "ICT 2022 Mentorship"]
    idx = random.choice(mentorship or available)
    used.append(idx)
    state["used_indices"] = used
    state["last_post_date"] = datetime.now(TIMEZONE).isoformat()
    save_state(state)
    return ICT_CONCEPTS[idx], len(used), len(ICT_CONCEPTS)

# ── Discord Webhook Post ───────────────────────────────────────────────────────
async def post_ict_concept():
    concept, count, total = get_next_concept()
    now = datetime.now(TIMEZONE)
    date_str = now.strftime("%A, %B %d %Y")

    embed = {
        "title": concept["title"],
        "description": f"**{concept['category']}  ·  {concept['type']}**",
        "color": concept["color"],
        "fields": [
            {"name": "📖 Definition", "value": concept["definition"], "inline": False},
            {"name": "⚙️ How To Use It", "value": concept["how_to_use"], "inline": False},
            {"name": "🖥️ NQ Application", "value": concept["nq_tip"], "inline": False},
            {"name": "⏱️ Best Timeframes", "value": concept["timeframes"], "inline": True},
            {"name": "📅 Posted", "value": date_str, "inline": True},
        ] + ([{"name": "🎥 Source", "value": concept["source"], "inline": False}] if concept.get("source") else []),
        "footer": {"text": f"SmokeyNQ Education  ·  Concept {count}/{total}  ·  ICT Methodology"},
    }

    payload = {
        "username": "Smokey EDU",
        "avatar_url": "https://i.imgur.com/1TepzcE.jpeg",
        "content": "📚 **ICT Concept of the Week** — Study this, apply it, master it.",
        "embeds": [embed],
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(STRATEGY_WEBHOOK_URL, json=payload) as resp:
            if resp.status in (200, 204):
                print(f"[✓] Posted: {concept['title']}")
            else:
                print(f"[✗] Failed: {resp.status} - {await resp.text()}")

# ── Discord Bot (for !testict command) ────────────────────────────────────────
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"[✓] SmokeSignals bot online as {bot.user}")

@bot.command(name="testict")
@commands.has_permissions(administrator=True)
async def test_ict(ctx):
    await ctx.send("🔄 Firing ICT concept to #strategy...")
    await post_ict_concept()
    await ctx.send("✅ Done! Check #strategy.")

@bot.command(name="resetict")
@commands.has_permissions(administrator=True)
async def reset_ict(ctx):
    r.delete(REDIS_KEY)
    await ctx.send(f"✅ ICT concept cycle reset — back to 0/{len(ICT_CONCEPTS)}.")

# ── Scheduler ─────────────────────────────────────────────────────────────────
async def scheduler():
    await bot.wait_until_ready()
    print("[*] Scheduler running — Mon & Thu 6:00 PM ET")
    while not bot.is_closed():
        now = datetime.now(TIMEZONE)
        if now.weekday() in POST_DAYS and now.hour == POST_TIME.hour and now.minute == POST_TIME.minute:
            state = load_state()
            last = state.get("last_post_date")
            if last:
                last_dt = datetime.fromisoformat(last)
                if (now - last_dt).total_seconds() < 60:
                    await asyncio.sleep(30)
                    continue
            await post_ict_concept()
        await asyncio.sleep(30)

async def main():
    async with bot:
        bot.loop.create_task(scheduler())
        await bot.start(DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(main())
