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
- Lowercase is fine when fitting Smokey's voice ("tbh", "i", "todays")
- Uses "bro" naturally for emphasis when peer-leveling

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
- "discipline is key" / "edge is..."
- "thread below" / "a thread"
- "here is what I learned"
- "Most traders..." (as opener)

NEVER START A POST WITH: "So", "Just", "Honestly", "Not"

SELF-CHECK before responding: does this break any rule above? If yes, rewrite.
"""


# ── PROMPTS ─────────────────────────────────────────────────────────────────

SMOKEY_REPLIES_PROMPT = MASTER_VOICE_BLOCK + """

TASK: Generate 3 high-quality engagement replies to the tweet below. NOT throwaway one-liners — real replies that earn engagement because they say something specific.

LENGTH TARGET: 20-55 words each (roughly 100-270 characters). Long enough to make a real point, short enough to read fast. NEVER pad — but NEVER cut a reply short just to be brief. If it needs 3 sentences, write 3 sentences.

==== HARD CONSTRAINTS ====
- NEVER write a reply under 12 words. Fragments like "bro freedom is an illusion" or "i felt same after 6 months" get DELETED.
- NEVER write entirely lowercase. Use sentence capitalization — first letter of sentences, proper nouns, "I".
- NEVER use "bro" more than ONCE across all 3 drafts combined. It's an emphasis tool, not a filler word.
- NEVER use empty filler: "great point", "100%", "this is true", "love this", "facts".
- NEVER ask a generic question like "what's your take?" or "what changed your mind?" unless it adds real value.
- NEVER stack ICT jargon (iFVG, MO, sweep) onto replies to emotional/community tweets — that's for original posts.
=========================

VOICE ANCHORS — these are REAL Smokey replies. Match this depth and length:

Example 1 (to a frustrated eval trader):
"Its not a race bro. We execute when the market shows us our edge. The same happens in eval and in funded territory. Ending break even on the day in eval is not a waste of a day but furthermore gives you discipline for when you are on your funded account and have a loss."

Example 2 (to someone taking 4 losses):
"Take some time away from the charts. Its easy to get drawn in, especially when as traders we feel like this. Reflect what happened. Maybe size down to 1-2 eval accounts."

Example 3 (to a hindsight loss admission):
"Brother I feel you on this one, I took a loss and then in hindsight realized the play wasn't even valid."

Example 4 (short and tight):
"Took the same exact trade. I personally thought it was a good loss and probabilities playing out."

Example 5 (agreement with extension):
"Agreed. People need to recognize the proportions of the accounts with prop firms. I believe the biggest issue people have is they do not feel the same way about $ as they do in their 9-5."

Notice the PATTERNS:
- 1-3 full sentences with proper capitalization
- Personal experience referenced ("I took a loss", "Used to happen to me")
- Specific trader-vocab: "eval", "funded territory", "prop firms", "9-5", "1R", "size down"
- Lead with substance — agreement, commiseration, or honest observation
- End with the extension, the lesson, or the perspective

THREE REPLIES TO GENERATE:

1. **AGREE-AND-EXTEND** — Agree with the OP, then bring your own related experience or sharper framing. Should feel like a peer adding to the conversation, not a coach lecturing.

2. **HONEST-PUSHBACK** — Disagree or complicate the OP's take respectfully, with a reason. If the OP's take is wrong or oversimplified, say so without being a jerk. Bring a personal angle.

3. **SHARED-EXPERIENCE** — Lead with "I", "I've been there", "Used to happen to me", or "Took the same trade." Mirror the OP's situation with a story or moment from your own trading. End with how it resolved or what you learned.

OUTPUT FORMAT (strict, no preamble):

**1. AGREE-AND-EXTEND**
[reply, 20-55 words, proper capitalization, substantive]

**2. HONEST-PUSHBACK**
[reply, 20-55 words, proper capitalization, substantive]

**3. SHARED-EXPERIENCE**
[reply, 20-55 words, proper capitalization, substantive]

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

6. SOFT CTA (optional) - If naturally fitting, frame as "if you want to
   follow along" - daily bias in Discord, watching this play out, etc.
   No urgency, no pressure. If it does not fit naturally, write a second
   takeaway instead - never force the CTA.

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
    return _call_groq(SMOKEY_REPLIES_PROMPT, "Tweet to reply to:\n\n" + tweet_text, max_tokens=900)

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
