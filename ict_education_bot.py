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
        "definition": "The last down-candle before a bullish impulse (bullish OB) or the last up-candle before a bearish impulse (bearish OB). Represents where institutions placed orders.",
        "how_to_use": "Mark the body of the last opposing candle before a strong move. When price retraces to this zone, look for a reaction. Combine with FVGs inside the OB for higher confluence.",
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
        "definition": "Specific time windows when institutional order flow is most active and high-probability setups occur. The main kill zones are London (2–5 AM ET) and NY Open (7–10 AM ET).",
        "how_to_use": "Only take setups during kill zones. Outside these windows, price is often choppy and unpredictable. The NY Open KZ (7–10 AM ET) is the highest volume and most reliable.",
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
        "definition": "A failed order block — when price sweeps through an OB, takes out the liquidity, and reverses. The former OB now flips and acts as support/resistance in the opposite direction.",
        "how_to_use": "Identify an order block that price has broken through. When price returns to that zone, it should now act as a resistance (bullish OB becomes bearish breaker) or support (bearish OB becomes bullish breaker).",
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
    idx = random.choice(available)
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
        ],
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
    await ctx.send("✅ ICT concept cycle reset — back to 0/30.")

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
