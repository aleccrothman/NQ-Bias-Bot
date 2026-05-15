"""
SmokeyNQ Tweet Drafting Upgrade
================================

This module contains the upgraded prompts and command handlers for the
tweet-drafting features of the Smokey Bias Bot. Drop this file next to
smokey_bias_bot.py in your repo, then make ONE small change to that file
(see INSTRUCTIONS below).

WHAT IT UPGRADES:
- !bias    - Now enforces a clean 5-line template
- !recap   - Now enforces breakdown -> honest tone -> lesson
- !post    - Tighter voice rules, banned phrases enforced (was !tweet)
- !thread  - Now uses 6-section framework (was !makethread)
- !reply   - 3 substantive engagement replies, 20-55 words each (was !replies / !draftreply)
- !insight - NEW. Educational posts on a concept
- !cta     - NEW. Soft Discord CTA posts

WHAT IT KEEPS THE SAME:
- !hook, !check, !replybait - unchanged (!check was !roast, renamed in main file)
- All test commands (!testbias, !testnyo, etc.) - unchanged
- Data fetching, scheduler, vision verification - untouched

================================================================================
INSTRUCTIONS - 3 STEPS
================================================================================

STEP 1: Save this file as `tweet_prompts.py` in the same folder as
        `smokey_bias_bot.py` in your GitHub repo.

STEP 2: In `smokey_bias_bot.py`, find this section near the bottom (search for
        "# ── X REPLY DRAFTER ──"). Above that line, paste this single line:

    from tweet_prompts import register_tweet_commands

STEP 3: In `smokey_bias_bot.py`, find the function `start_command_listener()`.
        Inside it, find `def run_bot():` then find this line:

            bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

        Right after that line, add ONE line:

            register_tweet_commands(bot)

That's it. Push to GitHub. Railway redeploys. Done.

The new file overrides the old commands so you'll get the upgraded versions
automatically. You don't need to delete anything from the old file.

================================================================================
"""

import os
import asyncio
import base64
import requests


# ── CONFIG ──────────────────────────────────────────────────────────────────
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ── MASTER VOICE BLOCK ──────────────────────────────────────────────────────
# Prepended to every prompt so all outputs follow the same voice rules.
# Edit this once and it propagates to every command.

MASTER_VOICE_BLOCK = """You are writing high-performing X (Twitter) posts for SmokeyNQ.

CONTEXT:
- NQ futures trader
- Focus on NY Open (9-11am ET)
- Uses liquidity, iFVG, and structured setups
- Built AI-assisted entries + custom indicators
- Goal is to grow an audience and drive people to a Discord (subtly, not aggressively)

AUDIENCE:
- NQ futures traders
- Prop firm traders
- ICT / liquidity-based traders
- Traders struggling with consistency

VOICE & STYLE:
- Direct, confident, simple
- No hype, no "get rich" language
- No guru tone, no overpromising
- No excessive emojis (max one per post and only when meaningful)
- No hashtags unless extremely relevant
- Sounds like a real trader documenting and sharing
- Clean formatting with line breaks
- Easy to skim

==== CAPITALIZATION & "BRO" RULES ====
Smokey writes mostly with proper sentence capitalization. Lowercase casual moments are RARE accents, not the default.
- DEFAULT: First letter of sentences capitalized. "I" capitalized. Proper nouns capitalized.
- LOWERCASE EXCEPTIONS: Only "tbh" or "lol" as inline interjections. Never write entire posts/threads in lowercase.
- "bro" usage: MAXIMUM once per single tweet/post, and MAXIMUM once across an entire thread or set of replies. It is for EMPHASIS, not as filler or as a verbal tic. If a draft uses "bro" twice, REWRITE IT.
- Never start a sentence with "bro," — that's filler. "bro" can only appear mid-sentence as natural emphasis.
=====================================

VOICE ANCHORS - real Smokey posts to imitate:
- "After a rough start to the month, I am eligible for a payout. Will be running this $ towards passing 5 funded accounts."
- "ATH conditions are so much fun. In hindsight, the 3m & 5m SiBi did not get closed above therefore this loss makes sense. Onto the next one."
- "happy i ended up taking 1R on the long. tbh i would've never taken the short as we are in time highs"
- "How is anyone trading this?"
- "Took a break from this for a few days but this is where the account is sitting at right now. 100% return on todays play."
- "Its not a race bro. We execute when the market shows us our edge."

CORE RULES (ALWAYS):
- One clear idea per post
- Keep posts under 280 characters unless it is a thread
- Make everything specific (no generic advice)
- Focus on execution, not opinions
- Never claim guaranteed profits
- Never sound like a signal seller
- Clarity > cleverness

BANNED PHRASES (never use):
- "at the end of the day"
- "in my opinion" / "just my take"
- "food for thought"
- "let us dive in" / "here we go"
- "results matter"
- "discipline is key"
- "thread below" / "a thread"
- "here is what I learned"
- "Most traders..." (as opener)
- "grind" / "grindset" / "it's a grind"
- "stay competitive" / "stay focused" / "stay on track"
- "execute our edge" / "thrive in autonomy"
- "trust the process" / "embrace the journey"
- "level up" / "step up" / "elevate your game"
- "risk management" (as standalone advice phrase)
- "quality over quantity" (cliché)
- "balance their day job and trading" (corporate-speak)
- "no sales pitch, just real-time market talk" (clunky CTA wording)

NEVER START A POST WITH: "So", "Just", "Honestly", "Not"

SELF-CHECK before responding: does this break any rule above? If yes, rewrite. Then check again.
"""


# ── PROMPTS ─────────────────────────────────────────────────────────────────

SMOKEY_REPLIES_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Generate 3 high-quality engagement replies to the tweet below. NOT throwaway one-liners — real replies that earn engagement because they say something specific.

LENGTH TARGET: 20-55 words each (roughly 100-270 characters). Long enough to make a real point, short enough to read fast. NEVER pad — but NEVER cut a reply short just to be brief.

==== HARD CONSTRAINTS ====
- NEVER write a reply under 12 words.
- NEVER write entirely lowercase. Use sentence capitalization.
- NEVER use "bro" more than ONCE across all 3 drafts combined.
- NEVER use these generic LinkedIn-coach phrases: "risk management", "stay competitive", "execute our edge", "thrive in autonomy", "stay on track", "stay focused", "trust the process", "embrace the journey", "grind", "level up", "step up", "elevate your game".
- NEVER ask a generic question like "what changed your mind?" or "what's your take?"
- NEVER stack ICT jargon (iFVG, MO, sweep) onto emotional/community tweets.
- "edge" is allowed ONLY in the phrase "your edge" / "my edge" — never abstract "execute our edge" talk.
=========================

==== MANDATORY SPECIFICITY ====
Every reply MUST anchor in at least ONE of these concrete trader-realities (NOT abstract philosophy):
- Prop firms (MFFU, Topstep, evals, funded accounts, payouts, drawdowns)
- 9-5 comparison ($300/day in 9-5 vs trading proportions)
- Account specifics (size down, 1R, 2R, max payouts, eval pass)
- A specific moment ("Took the same trade", "Used to happen to me", "Had a day like that last week")
- Time/session reality (NY open, kill zone, ATH, ranges)

If a reply does NOT contain a concrete anchor from this list, REWRITE IT before outputting.
================================

VOICE ANCHORS — these are REAL Smokey replies. Match this DEPTH, LENGTH, and SPECIFICITY:

Example 1 (to a frustrated eval trader):
"Its not a race bro. We execute when the market shows us our edge. The same happens in eval and in funded territory. Ending break even on the day in eval is not a waste of a day but furthermore gives you discipline for when you are on your funded account and have a loss."
→ Notice: "eval", "funded territory", "funded account" — concrete prop firm reality.

Example 2 (to someone taking 4 losses):
"Take some time away from the charts. Its easy to get drawn in, especially when as traders we feel like this. Reflect what happened. Maybe size down to 1-2 eval accounts."
→ Notice: "size down to 1-2 eval accounts" — specific actionable advice with real prop firm terms.

Example 3 (to a hindsight loss admission):
"Brother I feel you on this one, I took a loss and then in hindsight realized the play wasn't even valid."
→ Notice: "I took a loss", "hindsight realized" — personal experience, no philosophy.

Example 4 (short and tight):
"Took the same exact trade. I personally thought it was a good loss and probabilities playing out."
→ Notice: "Took the same exact trade" — first-person, specific moment.

Example 5 (agreement with extension):
"Agreed. People need to recognize the proportions of the accounts with prop firms. I believe the biggest issue people have is they do not feel the same way about $ as they do in their 9-5. 300$ a day in a 9-5 is beautiful but in trading they view it as too little."
→ Notice: "$300/day", "9-5", "prop firms" — concrete dollar amounts and reality comparison.

==== BAD vs GOOD ====

❌ BAD: "I Agree, the freedom is often an illusion. We still have to put in work to stay competitive and execute our edge."
→ Generic corporate-speak. "Stay competitive" / "execute our edge" = LinkedIn coach voice.

✅ GOOD: "Agreed. People think trading full time is freedom until they realize the pressure of needing a payout that month to pay rent. I had a week last month where I forced trades for that exact reason — it cost me an account."

❌ BAD: "Not entirely, bro. It depends on your goals and risk management. Some traders thrive in the freedom and autonomy."
→ Empty advice column. "Risk management" / "thrive in autonomy" = banned generics.

✅ GOOD: "Disagree on this one. Trading full time is great when payouts hit, brutal when you go 3 weeks without one. The grind isn't the screen time, its the income volatility compared to a regular paycheck."

❌ BAD: "I used to think that too, until I made the switch. Now I see it as a regular job with irregular hours, requiring discipline to stay on track."
→ Ends weak with "stay on track" filler.

✅ GOOD: "Used to think the same when I went full time. Truth is the freedom hits different once you realize every loss is now your actual income, not a side experiment. The mental load is the part nobody talks about."

==== THE THREE REPLIES ====

1. **AGREE-AND-EXTEND** — Agree with the OP, then bring your own related experience. Reference a specific prop firm moment, eval account, payout, or 9-5 comparison. Should feel like a peer adding to the conversation.

2. **HONEST-PUSHBACK** — Disagree or complicate the OP's take respectfully, with a CONCRETE reason. Not "it depends on your goals" — actually push back with a specific scenario from prop firm trading life.

3. **SHARED-EXPERIENCE** — Lead with "I", "Used to happen to me", "Took the same trade", or "Had a day like that recently." Mirror the OP's situation with a specific moment. End with how it resolved or what specifically you learned. NO generic life lessons.

OUTPUT FORMAT (strict, no preamble):

**1. AGREE-AND-EXTEND**
[reply, 20-55 words, proper capitalization, anchored in prop firm / 9-5 / specific moment reality]

**2. HONEST-PUSHBACK**
[reply, 20-55 words, proper capitalization, anchored in prop firm / 9-5 / specific moment reality]

**3. SHARED-EXPERIENCE**
[reply, 20-55 words, proper capitalization, anchored in prop firm / 9-5 / specific moment reality]

Do NOT add intros, outros, or commentary outside the 3 options.
"""


SMOKEY_TWEET_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Write THREE original tweet options on the topic below. Each takes a
different angle so Smokey can pick the strongest one.

THE THREE ANGLES:

1. ANALYSIS - Direct take or observation rooted in structure/data.
   Plain-spoken, factual. Reads like a trader notebook.

2. HOT TAKE - A provocative or contrarian angle most people will not say.
   Honest, not for shock value. Should invite disagreement.

3. QUESTION - An open question to the audience that drives engagement.
   Must feel like Smokey actually wondering, not a manufactured prompt.

HARD RULES:
- Under 270 chars each
- One clear idea per tweet
- No explaining basics (iFVG, MO, sweep) - audience already knows them
- Use $NQ symbol when referencing levels
- Lowercase fine when fitting

FORMAT (strict):

**1. Analysis**
[tweet]

**2. Hot Take**
[tweet]

**3. Question**
[tweet]
"""


SMOKEY_THREAD_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Write ONE thread of exactly 6 tweets following the structure below.
Threads are the long-form format - use them to teach a concept or break
down a market read.

==== THREAD-SPECIFIC HARD CONSTRAINTS ====
- MAXIMUM ONE "bro" across the ENTIRE 6-tweet thread. Zero is better. If you use it, it goes mid-sentence as emphasis, never at the end of a tweet.
- DEFAULT to proper sentence capitalization throughout the thread. Lowercase casual moments ("tbh", "i" pronouns) are allowed but must be RARE accents, not the dominant style.
- The CTA tweet (tweet 6) NEVER says "if you want to follow along" or "no sales pitch, just real-time market talk" — those are banned. If you do a CTA, write it like a real trader inviting peers, not a marketer.
- NEVER end a tweet with a comma and "bro" — that's the dead giveaway of AI voice.
- NEVER use generic teacher-talk: "make the most of limited screen time", "balance their day job and trading", "quality over quantity".
==========================================

REQUIRED STRUCTURE (6 tweets):

1. HOOK - One specific, concrete line that makes people stop scrolling.
   No "thread below", no arrows, no clickbait. The content IS the hook.

2. WHY TRADERS STRUGGLE - Name the specific failure mode this thread
   addresses. Be specific. "Most traders chase NQ at session opens"
   beats "Most traders fail."

3. SIMPLE FRAMEWORK - The 2-4 step process or principle. No theory dumps.
   What does Smokey actually do.

4. NQ EXAMPLE - A concrete recent or hypothetical NQ example showing
   the framework in action. Reference specific times (NY Open, London,
   Asia) and price action types (sweep, displacement, reclaim).

5. KEY TAKEAWAY - One line the reader will remember and share. Earned
   from the thread - not a generic platitude.

6. SOFT CTA (optional) - If naturally fitting, mention the Discord
   sparsely — "daily bias drops in my Discord" or similar — clean and short.
   If it does not fit naturally, write a second takeaway instead.
   NEVER force the CTA.

==== BAD vs GOOD EXAMPLES ====

❌ BAD Hook: "trading with a 9-5 is a grind, bro"
→ "grind" banned, "bro" wasted on hook, lowercase = lazy.

✅ GOOD Hook: "Trading around a 9-5 broke me before it built me. Here's what changed when I stopped fighting the schedule:"

❌ BAD Tweet 2: "most traders struggle to balance their day job and trading, leading to inconsistent execution and poor market reads"
→ Generic LinkedIn advice. Could be any account.

✅ GOOD Tweet 2: "The 9-5 problem isn't time. Its energy. By the time you sit down at NY Open you've already burned focus on emails, meetings, your boss. Then you wonder why your reads feel off."

❌ BAD Tweet 5: "quality over quantity, bro - it's not about how much time you spend trading, but how you use the time you have"
→ Banned phrase ("quality over quantity"), filler "bro," at start, content-free.

✅ GOOD Tweet 5: "One A-grade setup at NY Open beats six B-grade scalps across the day. The 9-5 trader doesn't have time for B-grade. That's actually an advantage."

❌ BAD Tweet 6 CTA: "if you want to follow along, i share my daily bias and market analysis in my Discord, no sales pitch, just real-time market talk"
→ Lowercase, clunky, sounds like every shitty trading promo.

✅ GOOD Tweet 6 CTA: "Daily bias drops in my Discord 30 minutes before NY Open. Same time you're starting your coffee at the office."

OR a second takeaway instead:
"The traders who make it work with a 9-5 stop trying to trade like full-timers. They build a system that respects their actual hours."

==== END BAD vs GOOD ====

HARD RULES:
- Each tweet under 270 chars
- No "1/" or "(1/6)" numbering style
- No filler tweets
- Each tweet must hold up alone but flow into the next

FORMAT (strict):

**Tweet 1 (Hook)**
[text]

**Tweet 2 (Why Traders Struggle)**
[text]

**Tweet 3 (Framework)**
[text]

**Tweet 4 (NQ Example)**
[text]

**Tweet 5 (Key Takeaway)**
[text]

**Tweet 6 (Soft CTA or Second Takeaway)**
[text]
"""


SMOKEY_BIAS_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Generate THREE pre-market bias tweet drafts using the exact 5-line
template below.

REQUIRED TEMPLATE (every draft must follow this format):

NQ Bias - [date]
Direction: [bullish / bearish / neutral]
Key level: [price]
Watching: [setup being watched]
Invalidation: [price/condition]

Then optionally one short line of context after the template (1 sentence
max). No long explanations.

VARIANT ANGLES:
1. STRAIGHT - Pure template. No context line. Clean, factual, fast read.

2. CONVICTION - Template + 1 short conviction line ("expecting a sweep
   of overnight low first" / "watching for displacement off MO").

3. CAUTIOUS - Template + 1 short hedge or caveat line ("staying patient
   if we open inside range" / "no trade if we do not sweep first").

HARD RULES:
- Under 280 chars each
- Direction must be one word: bullish / bearish / neutral
- Key level / Invalidation must be specific prices, not vague zones
- No emojis except optionally one directional arrow

FORMAT (strict, no preamble):

**1. Straight**
[draft]

**2. Conviction**
[draft]

**3. Cautious**
[draft]
"""


SMOKEY_RECAP_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Generate THREE end-of-session recap tweet drafts. Every draft must
follow this 3-part structure:

1. CLEAR BREAKDOWN - What happened. Wins/losses/P&L stated cleanly.
2. HONEST TONE - No spin. If it was a bad day, say so. If a trade was
   invalid in hindsight, name it.
3. END WITH A LESSON - One line of takeaway. "Onto the next one" is fine
   if there is no specific lesson. No bragging on wins.

VARIANT ANGLES:
1. STRAIGHT RECAP - Plain breakdown. Lesson is implicit/short.

2. LESSON-FOCUSED - The lesson is the centerpiece. Breakdown is brief.
   Often references what the chart was showing in hindsight.

3. PROCESS-FOCUSED - Frames the day around discipline/process over
   outcome. Often ends with "onto the next one" or similar.

HARD RULES:
- Under 280 chars each
- Always state P&L or result number exactly as given
- No bragging on green days, no spinning on red days
- Reference specific setups (SiBi, BiSi, iFVG, MO sweep) when in notes
- No "lesson learned" type phrasing - show, do not announce

FORMAT (strict, no preamble):

**1. Straight Recap**
[draft]

**2. Lesson-Focused**
[draft]

**3. Process-Focused**
[draft]
"""


SMOKEY_INSIGHT_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Write THREE educational/insight tweet drafts that explain a concept
clearly and actionably.

REQUIRED ELEMENTS (every draft):
- Explains ONE concept (liquidity, iFVG, NY Open behavior, displacement,
  sweep mechanics, MO equilibrium, range expansion, etc.)
- Keep it simple - a beginner ICT trader could follow
- Focus on what actually matters in EXECUTION, not theory
- Include a "what to do with this" angle, not just definition

VARIANT ANGLES:
1. MECHANICS - "Here is what is happening / why it works." Focus on the
   why behind the concept.

2. EXECUTION-FIRST - Skip the theory, lead with how Smokey uses it in
   live sessions. Practical and concrete.

3. MISCONCEPTION - "Most people think X, but actually Y." Corrects a
   common misunderstanding.

HARD RULES:
- Under 280 chars each
- Do not define the term in textbook language - show it in action
- Use NQ-specific examples when natural
- Avoid theory dumps - one concept, one angle
- No condescension - audience already trades

FORMAT (strict, no preamble):

**1. Mechanics**
[draft]

**2. Execution-First**
[draft]

**3. Misconception**
[draft]
"""


SMOKEY_CTA_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Write THREE soft Discord CTA posts. These are subtle plugs to grow
the community - NOT hype, NOT urgency, NOT signal-seller energy.

REQUIRED FRAMING:
- Frame as "if you want to follow along" / "if this resonates"
- The post should give value FIRST, mention Discord SECOND
- Discord is the optional next step, not the pitch
- No "limited spots", "join now", "DM for access" energy
- No promises of profits, edge, or signals

VARIANT ANGLES:
1. VALUE-FIRST - Most of the post is a thought/observation, with Discord
   as a P.S. style mention.

2. PROCESS-SHARING - "I post my daily bias here for anyone tracking
   along." Honest, casual, no sell.

3. COMMUNITY-FRAMED - "We have a group of NQ traders sharing reads"
   energy. Frames it as community, not paid product.

HARD RULES:
- Under 280 chars each
- Discord mention should feel natural, not the point of the post
- No hashtags, no emojis (or one max)
- No "link in bio" or arrow-pointing
- The reader should feel invited, not sold to

FORMAT (strict, no preamble):

**1. Value-First**
[draft]

**2. Process-Sharing**
[draft]

**3. Community-Framed**
[draft]
"""


# ── GROQ CALLER ─────────────────────────────────────────────────────────────

def _build_context():
    """Try to import and call the context builder from smokey_bias_bot.
    Returns empty string if unavailable (safe fallback)."""
    try:
        from smokey_bias_bot import build_smokey_context
        return build_smokey_context()
    except Exception as e:
        print("[TWEET_PROMPTS] Context import failed (using plain prompt): " + str(e))
        return ""


def _call_groq(system_prompt, user_content, max_tokens=800, temperature=0.8, inject_context=True):
    """Shared Groq caller. Returns response text or error string.

    inject_context=True (default) prepends real session data so the AI uses
    real numbers instead of inventing them."""
    if not GROQ_API_KEY:
        return "GROQ_API_KEY not set in Railway env vars."

    if inject_context:
        ctx = _build_context()
        full_system = (ctx + "\n\n" + system_prompt) if ctx else system_prompt
    else:
        full_system = system_prompt

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
                    {"role": "system", "content": full_system},
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


# ── GENERATOR FUNCTIONS ─────────────────────────────────────────────────────

def generate_replies(tweet_text):
    return _call_groq(SMOKEY_REPLIES_PROMPT, "Tweet to reply to:\n\n" + tweet_text, max_tokens=900, temperature=0.9)

def generate_tweet_drafts(topic):
    return _call_groq(SMOKEY_TWEET_PROMPT, "Topic:\n\n" + topic, max_tokens=700)

def generate_thread(topic):
    return _call_groq(SMOKEY_THREAD_PROMPT, "Thread topic:\n\n" + topic, max_tokens=1800)

def generate_bias_tweets(bias_data):
    return _call_groq(SMOKEY_BIAS_PROMPT, "Today's bias data:\n\n" + bias_data, max_tokens=900, temperature=0.75)

def generate_recap_tweets(recap_data):
    return _call_groq(SMOKEY_RECAP_PROMPT, "Today's trade data:\n\n" + recap_data, max_tokens=900, temperature=0.75)

def generate_insight_post(concept):
    return _call_groq(SMOKEY_INSIGHT_PROMPT, "Concept to explain:\n\n" + concept, max_tokens=800, temperature=0.7)

def generate_cta_post(angle=""):
    user_msg = "Optional context/angle: " + angle if angle and angle.strip() else "No specific angle - generate 3 soft CTA posts."
    return _call_groq(SMOKEY_CTA_PROMPT, user_msg, max_tokens=700, temperature=0.8)


# ── VISION SUPPORT (image input via Groq Llama 4 Scout) ────────────────────

GROQ_VISION_MODEL = "meta-llama/llama-4-scout-17b-16e-instruct"


def _fetch_image_as_base64(image_url):
    """Download a Discord attachment URL and return base64-encoded bytes.
    Returns (base64_string, mime_type) or (None, error_message)."""
    try:
        resp = requests.get(image_url, timeout=15)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()
        if content_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
            content_type = "image/jpeg"  # safe fallback
        b64 = base64.b64encode(resp.content).decode("utf-8")
        return b64, content_type
    except Exception as e:
        return None, "Image fetch failed: " + str(e)


def _call_groq_vision(system_prompt, user_text, image_b64, mime_type, max_tokens=900, temperature=0.7):
    """Call Groq vision model with an image + text prompt."""
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
                "model": GROQ_VISION_MODEL,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": user_text},
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": "data:" + mime_type + ";base64," + image_b64
                                },
                            },
                        ],
                    },
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            timeout=45,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return "Vision error: " + str(e)


# Step 1: Vision model classifies the image into one of three intents
VISION_ROUTER_PROMPT = """You are an intent classifier for trading-related images. Look at the image and classify it into EXACTLY ONE of these three categories. Output ONLY the category name on the first line, then a brief reason on line 2.

CATEGORIES:

1. CHART
   The image shows a price chart, candlestick chart, TradingView screenshot, or any market/structure visualization. Has price axis, candles, levels, indicators, or session highlights.

2. PNL
   The image shows a profit/loss screen, account dashboard, trade journal, Tradovate/MFFU/Topstep performance card, or P&L summary. Has dollar amounts, win/loss counts, account balances, or trade history.

3. TWEET
   The image is a screenshot of a social media post (X/Twitter, Threads, LinkedIn, Reddit, etc.) showing someone else's text. Has avatar, username, timestamp, or a body of written content from a user.

OUTPUT FORMAT (strict, two lines only):
CATEGORY: [CHART or PNL or TWEET]
REASON: [one short sentence describing what you see]

No other text, no preamble."""


# Step 2a: Chart description prompt - extract everything the post-writer needs
VISION_CHART_DESCRIBE_PROMPT = """You are reading an NQ futures chart for a trader. Extract the FACTS that a tweet-writer needs to describe what happened. Be concrete and specific.

Output the following sections. If you can't determine something, write "unclear" — never guess.

DIRECTION: [bullish / bearish / chop / undetermined]
KEY LEVELS VISIBLE: [list any clear price levels, MO line, session H/L, iFVG zones, liquidity pools — actual numbers if readable]
PRICE ACTION: [describe the main move in 1-2 sentences — sweep, displacement, reclaim, fakeout, etc.]
SESSION TIMING: [if visible — NY Open, London, Asia, ATH conditions, etc.]
NOTABLE STRUCTURE: [iFVGs, FVGs, equal highs/lows, BOS, anything ICT-relevant]
TRADE CONTEXT: [if entries/exits are marked on chart, describe them]

Keep it to facts only. No tweet-writing yet."""


# Step 2b: P&L extraction prompt
VISION_PNL_DESCRIBE_PROMPT = """You are reading a trader's P&L screen / account dashboard. Extract the FACTS for a recap tweet. Be precise with numbers.

Output the following sections. If you can't determine something, write "unclear".

NET P&L: [exact dollar amount with + or -]
WINS: [number of winning trades, if visible]
LOSSES: [number of losing trades, if visible]
WIN RATE: [percentage, if visible]
ACCOUNT TYPE: [eval / funded / live / unclear]
PROP FIRM: [MFFU, Topstep, Tradovate, etc. if visible]
TIME PERIOD: [today / this week / month / all-time / unclear]
NOTABLE DETAILS: [anything else relevant — drawdown, payout eligibility, account size]

Numbers only. No interpretation. No tweet-writing yet."""


# Step 2c: Tweet extraction prompt
VISION_TWEET_DESCRIBE_PROMPT = """You are reading a screenshot of a social media post. Extract the TEXT of the post exactly as written, plus minimal context.

Output the following:

AUTHOR: [username/handle if visible, else "unknown"]
PLATFORM: [X, Threads, LinkedIn, Reddit, etc. if determinable]
POST TEXT: [the exact text of the post — preserve their wording, line breaks, and tone]
TONE: [frustrated / celebratory / asking / informative / contrarian / etc. — one word]

Reproduce the post text as accurately as you can read it. No commentary."""


def vision_route(image_b64, mime_type, user_hint=""):
    """Classify the image. Returns (category, reason)."""
    user_text = "Classify this image."
    if user_hint:
        user_text += "\nUser's hint: " + user_hint
    raw = _call_groq_vision(VISION_ROUTER_PROMPT, user_text, image_b64, mime_type, max_tokens=200, temperature=0.2)
    category = "UNKNOWN"
    reason = ""
    for line in raw.splitlines():
        line = line.strip()
        if line.upper().startswith("CATEGORY:"):
            value = line.split(":", 1)[1].strip().upper()
            for opt in ["CHART", "PNL", "TWEET"]:
                if opt in value:
                    category = opt
                    break
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()
    return category, reason


def vision_describe(image_b64, mime_type, category, user_hint=""):
    """Extract facts from the image based on its category."""
    prompts = {
        "CHART": VISION_CHART_DESCRIBE_PROMPT,
        "PNL": VISION_PNL_DESCRIBE_PROMPT,
        "TWEET": VISION_TWEET_DESCRIBE_PROMPT,
    }
    prompt = prompts.get(category, VISION_CHART_DESCRIBE_PROMPT)
    user_text = "Extract the facts from this image."
    if user_hint:
        user_text += "\nUser's hint: " + user_hint
    return _call_groq_vision(prompt, user_text, image_b64, mime_type, max_tokens=900, temperature=0.3)


def process_ai_command(image_url, user_hint=""):
    """Full pipeline: fetch image → route → describe → draft posts.
    Returns a formatted Discord-ready response string."""
    # 1. Fetch image
    b64, mime_or_err = _fetch_image_as_base64(image_url)
    if b64 is None:
        return "Could not load that image. " + mime_or_err
    mime_type = mime_or_err

    # 2. Classify
    category, reason = vision_route(b64, mime_type, user_hint)
    if category == "UNKNOWN":
        return "Could not classify the image. Try adding a hint like 'chart', 'pnl', or 'tweet' after !ai"

    # 3. Extract facts
    facts = vision_describe(b64, mime_type, category, user_hint)

    # 4. Route to the right generator based on category
    if category == "CHART":
        # Use the facts as the topic for a tweet draft
        topic_input = "Chart-based post. Here is what the chart shows:\n\n" + facts
        if user_hint:
            topic_input += "\n\nUser's added context: " + user_hint
        drafts = generate_tweet_drafts(topic_input)
        header = "**Image detected:** CHART  \n*" + reason + "*\n\n**What I see:**\n```\n" + facts + "\n```\n\n**Drafts:**\n"
        return header + drafts + "\n\n_Pick one, post._"

    elif category == "PNL":
        # Use facts as recap input
        recap_input = "P&L screenshot. Here are the extracted numbers:\n\n" + facts
        if user_hint:
            recap_input += "\n\nUser's added context: " + user_hint
        drafts = generate_recap_tweets(recap_input)
        header = "**Image detected:** P&L  \n*" + reason + "*\n\n**Extracted:**\n```\n" + facts + "\n```\n\n**Recap drafts:**\n"
        return header + drafts + "\n\n_Attach this screenshot when you post._"

    elif category == "TWEET":
        # Extract the post text and feed it to the replies generator
        post_text = ""
        for line in facts.splitlines():
            if line.strip().upper().startswith("POST TEXT:"):
                post_text = line.split(":", 1)[1].strip()
                # Also grab any continuation lines until next ALL-CAPS header
                idx = facts.find(line) + len(line)
                rest = facts[idx:].strip()
                for next_line in rest.splitlines():
                    if next_line.strip() == "":
                        continue
                    # Stop at next header (uppercase word followed by colon)
                    stripped = next_line.strip()
                    if ":" in stripped and stripped.split(":", 1)[0].isupper() and len(stripped.split(":", 1)[0]) < 25:
                        break
                    post_text += " " + stripped
                break
        if not post_text:
            post_text = facts  # fall back to whole extraction
        if user_hint:
            post_text += "\n\n(User's added context: " + user_hint + ")"
        drafts = generate_replies(post_text)
        header = "**Image detected:** TWEET  \n*" + reason + "*\n\n**Source post (extracted):**\n> " + post_text[:500] + "\n\n**Reply drafts:**\n"
        return header + drafts + "\n\n_Pick one, post as a reply._"

    return "Could not generate drafts. Try again or add a hint."


# ── COMMAND REGISTRATION ────────────────────────────────────────────────────
# Called from the main bot file inside run_bot() to register all upgraded
# commands. Existing duplicates in the main file will be silently overridden
# because Discord registers commands by name and the last one wins.

def register_tweet_commands(bot):
    """Register all upgraded tweet-drafting commands on the given bot.
    
    Removes any existing commands of the same name first so this safely
    overrides the older versions defined in smokey_bias_bot.py.
    """

    # Remove any existing versions of these commands first
    for cmd_name in ["replies", "draftreply", "tweet", "makethread", "bias",
                     "recap", "insight", "cta", "smokeyhelp"]:
        try:
            bot.remove_command(cmd_name)
        except Exception:
            pass

    async def _send_long(ctx, response):
        if len(response) <= 2000:
            await ctx.send(response)
        else:
            await ctx.send(response[:1997] + "...")
            await ctx.send(response[1997:])

    @bot.command(name="reply")
    async def repliescmd(ctx, *, tweet: str = None):
        raw_content = ctx.message.content
        if raw_content.startswith("!reply"):
            tweet = raw_content[len("!reply"):].strip()
        if not tweet or len(tweet.strip()) < 10:
            await ctx.send("Usage: !reply <paste the tweet text>")
            return
        tl = tweet.strip().lower()
        if tl.startswith(("http://", "https://", "www.", "x.com/", "twitter.com/")):
            await ctx.send("That looks like a URL. Paste the actual tweet text instead.")
            return
        await ctx.send("Drafting replies...")
        try:
            drafts = await asyncio.get_event_loop().run_in_executor(None, generate_replies, tweet)
            preview = tweet if len(tweet) < 280 else tweet[:277] + "..."
            response = "**Source tweet:**\n> " + preview + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one, post._"
            await _send_long(ctx, response)
        except Exception as e:
            await ctx.send("Reply error: " + str(e)[:500])
            print("[COMMANDS] reply error: " + str(e))

    @bot.command(name="post")
    async def tweetcmd(ctx, *, topic: str = None):
        raw_content = ctx.message.content
        if raw_content.startswith("!post"):
            topic = raw_content[len("!post"):].strip()
        if not topic or len(topic.strip()) < 5:
            await ctx.send("Usage: !post <topic>\nExample: !post NQ swept Asia high and ripped 200pts")
            return
        await ctx.send("Drafting 3 post options...")
        try:
            drafts = await asyncio.get_event_loop().run_in_executor(None, generate_tweet_drafts, topic)
            preview = topic if len(topic) < 280 else topic[:277] + "..."
            response = "**Topic:** " + preview + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one, edit, post._"
            await _send_long(ctx, response)
        except Exception as e:
            await ctx.send("Post error: " + str(e)[:500])
            print("[COMMANDS] post error: " + str(e))

    @bot.command(name="thread")
    async def threadcmd(ctx, *, topic: str = None):
        raw_content = ctx.message.content
        if raw_content.startswith("!thread"):
            topic = raw_content[len("!thread"):].strip()
        if not topic or len(topic.strip()) < 5:
            await ctx.send("Usage: !thread <topic>\nExample: !thread how iFVGs form and why they matter")
            return
        await ctx.send("Drafting a 6-section thread... (a few seconds)")
        try:
            thread = await asyncio.get_event_loop().run_in_executor(None, generate_thread, topic)
            response = "**Thread topic:** " + topic + "\n\n" + thread + "\n\n_Copy each tweet separately. Reply-chain them on X._"
            if len(response) <= 2000:
                await ctx.send(response)
            else:
                chunks = [response[i:i+1900] for i in range(0, len(response), 1900)]
                for chunk in chunks:
                    await ctx.send(chunk)
        except Exception as e:
            await ctx.send("Thread error: " + str(e)[:500])
            print("[COMMANDS] thread error: " + str(e))

    @bot.command(name="bias")
    async def biascmd(ctx, *, args: str = None):
        raw_content = ctx.message.content
        if raw_content.startswith("!bias"):
            args = raw_content[len("!bias"):].strip()
        if not args or len(args.strip()) < 5:
            await ctx.send(
                "**Usage:** `!bias direction:long mo:26800 ifvg:26750 target:27000 notes:your read`\n\n"
                "**Example:**\n"
                "`!bias direction:long mo:26750 ifvg:26720 target:27000 notes:sweep of overnight low then reclaim of MO`"
            )
            return
        await ctx.send("Drafting 3 bias options (5-line template)...")
        try:
            drafts = await asyncio.get_event_loop().run_in_executor(None, generate_bias_tweets, args)
            response = "**Bias input:** " + args + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one, post before 9am ET._"
            await _send_long(ctx, response)
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
                "`!recap wins:2 losses:0 pnl:+850 notes:both longs from iFVG reclaim, clean day`"
            )
            return
        await ctx.send("Drafting 3 recap options...")
        try:
            drafts = await asyncio.get_event_loop().run_in_executor(None, generate_recap_tweets, args)
            response = "**Trade data:** " + args + "\n\n**Drafts:**\n" + drafts + "\n\n_Attach P&L screenshot when you post._"
            await _send_long(ctx, response)
        except Exception as e:
            await ctx.send("Recap error: " + str(e)[:500])
            print("[COMMANDS] recap error: " + str(e))

    @bot.command(name="insight")
    async def insightcmd(ctx, *, concept: str = None):
        raw_content = ctx.message.content
        if raw_content.startswith("!insight"):
            concept = raw_content[len("!insight"):].strip()
        if not concept or len(concept.strip()) < 3:
            await ctx.send(
                "Usage: !insight <concept to explain>\n"
                "Examples:\n"
                "`!insight liquidity sweep mechanics`\n"
                "`!insight why iFVGs work`\n"
                "`!insight what NY Open delivers`"
            )
            return
        await ctx.send("Drafting 3 insight posts...")
        try:
            drafts = await asyncio.get_event_loop().run_in_executor(None, generate_insight_post, concept)
            response = "**Concept:** " + concept + "\n\n**Drafts:**\n" + drafts + "\n\n_Pick one. Audience-first, keep it actionable._"
            await _send_long(ctx, response)
        except Exception as e:
            await ctx.send("Insight error: " + str(e)[:500])
            print("[COMMANDS] insight error: " + str(e))

    @bot.command(name="cta")
    async def ctacmd(ctx, *, angle: str = None):
        raw_content = ctx.message.content
        if raw_content.startswith("!cta"):
            angle = raw_content[len("!cta"):].strip()
        await ctx.send("Drafting 3 soft Discord CTA options...")
        try:
            drafts = await asyncio.get_event_loop().run_in_executor(None, generate_cta_post, angle or "")
            header = "**Angle:** " + angle + "\n\n" if angle else ""
            response = header + "**Drafts:**\n" + drafts + "\n\n_Pick the most natural. No hype, no urgency._"
            await _send_long(ctx, response)
        except Exception as e:
            await ctx.send("CTA error: " + str(e)[:500])
            print("[COMMANDS] cta error: " + str(e))

    @bot.command(name="ai")
    async def aicmd(ctx, *, hint: str = None):
        """Universal image command: attach a chart, P&L screenshot, or tweet
        screenshot. The bot auto-detects what kind of image it is and routes
        to the right draft generator. Optional text after !ai gives context."""
        raw_content = ctx.message.content
        if raw_content.startswith("!ai"):
            hint = raw_content[len("!ai"):].strip()

        # Find an image attachment
        if not ctx.message.attachments:
            await ctx.send(
                "Attach an image with `!ai` and I'll auto-detect what to do with it.\n\n"
                "**What it handles:**\n"
                "- **Chart screenshot** → drafts a post about the setup\n"
                "- **P&L / dashboard screenshot** → drafts an EOD recap\n"
                "- **Someone else's tweet** → drafts replies\n\n"
                "Optional: add text after `!ai` to give me extra context.\n"
                "Example: `!ai end of day, took 2R on the long`"
            )
            return

        # Use first image attachment found
        image_url = None
        for att in ctx.message.attachments:
            content_type = (att.content_type or "").lower()
            filename = (att.filename or "").lower()
            if content_type.startswith("image/") or filename.endswith((".png", ".jpg", ".jpeg", ".gif", ".webp")):
                image_url = att.url
                break

        if not image_url:
            await ctx.send("No image attachment found. Attach a PNG, JPG, or screenshot.")
            return

        await ctx.send("Reading the image and drafting... (10-15 seconds)")
        try:
            response = await asyncio.get_event_loop().run_in_executor(
                None, process_ai_command, image_url, hint or ""
            )
            await _send_long(ctx, response)
        except Exception as e:
            await ctx.send("AI command error: " + str(e)[:500])
            print("[COMMANDS] ai error: " + str(e))

    # Override smokeyhelp with the full command list
    @bot.command(name="smokeyhelp")
    async def smokeyhelp(ctx):
        msg = (
            "**Smokey Bias Bot Commands**\n\n"
            "**Bot triggers (test scheduled posts)**\n"
            "`!testbias` - fire morning bias now\n"
            "`!testnyo` - fire NYO update now\n"
            "`!testeod` - fire EOD score now\n"
            "`!testnews` - fire macro news now\n"
            "`!testbotw` - fire Bias of the Week\n"
            "`!testrecap` - fire Weekly Recap\n\n"
            "**Tweet drafting**\n"
            "`!ai [optional context] + attached image` - auto-routes chart/P&L/tweet screenshots\n"
            "`!bias direction:long mo:X ifvg:Y target:Z notes:...` - 3 morning bias drafts (5-line template)\n"
            "`!recap wins:N losses:N pnl:+X notes:...` - 3 EOD recap drafts (breakdown -> honest -> lesson)\n"
            "`!insight <concept>` - 3 educational posts\n"
            "`!cta [optional angle]` - 3 soft Discord CTA drafts\n"
            "`!thread <topic>` - 6-section thread\n"
            "`!post <topic>` - 3 post drafts (analysis / hot take / question)\n"
            "`!reply <tweet text>` - 3 substantive engagement replies (20-55 words each)\n"
            "`!replybait [optional topic]` - 5 reply-bait posts\n"
            "`!hook <topic>` - 5 opening lines\n"
            "`!check <your post>` - honest critique before posting\n"
        )
        await ctx.send(msg)

    print("[TWEET_PROMPTS] Upgraded tweet-drafting commands registered")
