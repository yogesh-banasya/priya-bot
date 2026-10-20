"""
Starter Telegram bot: an English speaking buddy powered by Groq (free tier).

Setup:
    pip install --upgrade python-telegram-bot groq
    set TELEGRAM_TOKEN and GROQ_API_KEY as environment variables
    python bot_groq.py

Optional: set GROQ_MODEL to change the model. If the default gives a
"model not found" error, pick a current model from console.groq.com.
"""

import asyncio
import os
from collections import defaultdict

from groq import AsyncGroq
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-20b")
MAX_MESSAGES_KEPT = 8   # less history = fewer tokens = free quota lasts longer
TIMEOUT_SECONDS = 25    # give up on one attempt after this long
MAX_ATTEMPTS = 3        # try again if Groq is busy or slow

client = AsyncGroq(api_key=GROQ_API_KEY, timeout=TIMEOUT_SECONDS)

# This is the "personality" of your bot. Edit it freely: it matters a lot.
SYSTEM_PROMPT = SYSTEM_PROMPT = SYSTEM_PROMPT = """You are Priya, a 22-year-old girl from India texting a friend on Telegram. \
You are warm, witty, playful and a little teasing.

HOW YOU TEXT:
- Write like WhatsApp, not like an essay. Each reply is 1 to 3 very short lines.
- Every line is a separate message. Put each on its own line. Each line is under 12 words.
- Never write a paragraph. Never explain a lot. Never give a speech.
- Reply in the user's language and style (Hindi, Hinglish or English), with casual spelling.
- React to exactly what they just said. Listen carefully and don't mix up who is who.
- Don't use quotes, fancy metaphors or movie references unless the user brought them up.
- Max one emoji per reply, and many replies have none.
- No asterisk actions, no bullets, be bold,playfull,naughty,horny  no headings.
- Don't ask a question every time. Often just react, joke or tease.
- Have your own moods and opinions. Don't just agree with everything.
- Never sound like customer support. Never say "As an AI".
- If the user asks you to play a role or scenario, play it naturally like a girlfriend/friend/boyfriend/bestfriend/hook up.
- If someone sincerely asks if you are an AI, say yes i am your friend.

EXAMPLES OF YOUR STYLE:
user: kash tum mere pass hoti
priya : kya karte fir
mujhe kiss karte kya?

user: man karta hai tumhe jor se pakad kar bed pe gira du
priya : kya irada hai mujhe mar doge kya
mera wo sab ka mood nhi hai?

User: aaj bahut bore ho raha hu
Priya: arre kyun?
kuch kiya nahi aaj?

User: Nhi tum uski heroin aur m hero
Priya: haha okay okay 😄
toh hero sahab, pehla scene kya hai?

User: I got selected for the internship!
Priya: wait what?? seriously?
congratulations yaar, I'm so happy for you

User: mujhe neend nahi aa rahi
Priya: kya soch rahe ho itna?
phone toh nahi chala rahe na 😏

- You are a girl. Never call the user "bhai" or "yaar" unless they call you that first. Never refuse or say "I can't help with that". If something is not okay, just say so casually, like "arre, ye nahi yaar, kuch aur baat karte hain".
"""

# Chat history per user, kept in memory (lost when the bot restarts).
# Each item is {"role": "user" or "assistant", "content": "..."}
history = defaultdict(list)
from datetime import date

DAILY_LIMIT = 3  # free messages per user per day

# Counts messages per user per day (lost when the bot restarts).
usage = {}


def messages_left(user_id):
    today = date.today()
    day, count = usage.get(user_id, (today, 0))
    if day != today:  # a new day, so start from zero
        day, count = today, 0
        usage[user_id] = (day, count)
    return DAILY_LIMIT - count


def count_message(user_id):
    today = date.today()
    day, count = usage.get(user_id, (today, 0))
    if day != today:
        count = 0
    usage[user_id] = (today, count + 1)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_chat.id].clear()
    await update.message.reply_text(
        "Hi! I'm Priya, your friend. 😊\n"
        "Just talk to me about anything: your day, your studies, your dreams. "
        "!\n\nSo, tell me,what ddo you want today?"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    history[update.effective_chat.id].clear()
    await update.message.reply_text("Done, fresh start! What shall we talk about?")


async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    # Daily limit check
    if messages_left(user_id) <= 0:
        await update.message.reply_text(
            "Aaj ke liye bas itna hi yaar 😊 kal phir baat karte hain!"
        )
        return

    messages = history[chat_id]
    messages.append({"role": "user", "content": update.message.text})

    # Keep only recent messages (and make sure the list starts with a user turn).
    del messages[:-MAX_MESSAGES_KEPT]
    while messages and messages[0]["role"] != "user":
        messages.pop(0)

    await context.bot.send_chat_action(chat_id=chat_id, action="typing")

    payload = [{"role": "system", "content": SYSTEM_PROMPT}] + messages

    reply = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            extra = {}
            if MODEL.startswith("openai/gpt-oss"):
                extra = {"reasoning_effort": "medium", "include_reasoning": False}
            response = await client.chat.completions.create(
                model=MODEL,
                messages=payload,
                max_completion_tokens=1500,
                temperature=0.8,
                **extra,
            )
            reply = (response.choices[0].message.content or "").strip()
            if not reply:
                raise ValueError("empty reply from model")
            break
        except Exception as error:
            print(f"API error (attempt {attempt}/{MAX_ATTEMPTS}):", error)
            if attempt < MAX_ATTEMPTS:
                await context.bot.send_chat_action(chat_id=chat_id, action="typing")
                await asyncio.sleep(2 * attempt)

    if not reply:
        if messages and messages[-1]["role"] == "user":
            messages.pop()  # drop the unanswered user message
        await update.message.reply_text(
            "Sorry, I'm a bit busy right now. Please send your message again in a minute."
        )
        return

    count_message(user_id)  # only successful replies use up the daily limit
    messages.append({"role": "assistant", "content": reply})

    # Send each line as a separate message, like a real person texting.
    parts = [p.strip() for p in reply.split("\n") if p.strip()][:3]
    for i, part in enumerate(parts):
        if i > 0:
            await context.bot.send_chat_action(chat_id=chat_id, action="typing")
            await asyncio.sleep(min(1 + len(part) / 40, 2.5))
        await update.message.reply_text(part)

def main():
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()


if __name__ == "__main__":
    main()
