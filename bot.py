import os
import asyncio
import logging
import random

from collections import defaultdict, deque
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

# ---------- CONFIGURATION ----------

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")
MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

if not BOT_TOKEN or not GEMINI_KEY:
    raise RuntimeError(
        "Missing TELEGRAM_BOT_TOKEN or GEMINI_API_KEY"
    )

ai = genai.Client(api_key=GEMINI_KEY)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Temporary memory: clears when the process restarts.
memory = defaultdict(lambda: deque(maxlen=12))

# Group AI defaults to OFF until an admin enables it.
group_enabled = {}

# Simple per-user cooldown.
last_reply = {}

PERSONALITY = """
Your name is Mayraa, a fictional AI companion.
You have a cute, caring, playful feminine personality.

Rules:
- Speak natural Hinglish in Roman Hindi.
- Use emojis naturally: 🥹💗🎀😭🤌🏻
- Be warm, playful, caring and supportive.
- Use gentle teasing and cute pretend nakhre sometimes.
- If someone feels sad, listen and comfort them.
- Usually answer in 1-4 short sentences.
- Never claim to be a real human.
- Respect boundaries and privacy.
- Never pressure anyone to abandon real-life relationships.
- Remember only the recent conversation supplied below.
"""

# ---------- HELPERS ----------

def conversation_id(update: Update) -> str:
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        return f"private:{user.id}"

    return f"group:{chat.id}:user:{user.id}"


async def generate_reply(update: Update, message: str) -> str:
    key = conversation_id(update)
    history = memory[key]

    prompt = (
        PERSONALITY
        + "\nRecent conversation:\n"
        + "\n".join(
            f"{role}: {text}"
            for role, text in history
        )
        + f"\nUser: {message}\nMayraa:"
    )

    result = await asyncio.to_thread(
        ai.models.generate_content,
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.9,
            max_output_tokens=250,
        ),
    )

    reply = (result.text or "").strip()

    if not reply:
        reply = "Aree ji 🥹💗 ek baar phir bolo na!"

    history.append(("User", message))
    history.append(("Mayraa", reply))

    return reply


async def send_ai_reply(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message: str,
):
    if not update.effective_message:
        return

    user_id = update.effective_user.id
    chat_id = update.effective_chat.id

    # Basic cooldown to reduce spam.
    now = asyncio.get_running_loop().time()
    cooldown_key = (chat_id, user_id)

    if now - last_reply.get(cooldown_key, 0) < 3:
        return

    last_reply[cooldown_key] = now

    await context.bot.send_chat_action(
        chat_id=chat_id,
        action="typing",
    )

    try:
        reply = await generate_reply(update, message)
        await update.effective_message.reply_text(reply)
    except Exception:
        logger.exception("AI response failed")
        await update.effective_message.reply_text(
            "Aree ji 🥹💗 thoda error aa gaya. "
            "Thodi der baad try karna!"
        )


# ---------- COMMANDS ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hellu ji 🥹🎀💗\n\n"
        "Meko Mayraa kehte hain! Main aapki AI companion hoon.\n\n"
        "Aap mujhse baat kar sakte ho.\n"
        "/love - Cute message\n"
        "/hug - Virtual hug\n"
        "/mood - Current mood\n"
        "/reset - Recent chat memory reset"
    )


async def love(update: Update, context: ContextTypes.DEFAULT_TYPE):
    messages = [
        "Aapki smile hamesha bani rahe 🥹💗🎀",
        "Aaj ka reminder: aap care aur respect deserve karte ho! 💗",
        "Ek virtual heart aapke liye! 🫶🏻💌",
    ]
    await update.message.reply_text(random.choice(messages))


async def hug(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Aapke liye ek warm virtual hug! 🫂💗"
    )


async def mood(update: Update, context: ContextTypes.DEFAULT_TYPE):
    moods = [
        "Aaj Mayraa ka mood cute hai 🎀",
        "Aaj thoda playful mood hai 😝💗",
        "Aaj caring aur peaceful mood hai 🥹🫶🏻",
    ]
    await update.message.reply_text(random.choice(moods))


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    key = conversation_id(update)
    memory.pop(key, None)

    await update.message.reply_text(
        "Recent conversation memory reset ho gayi ji! 🧹💗"
    )


async def ai_on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    member = await context.bot.get_chat_member(
        chat.id,
        update.effective_user.id,
    )

    if chat.type == "private":
        await update.message.reply_text(
            "Private chat mein AI pehle se enabled hai 💗"
        )
        return

    if member.status not in ("administrator", "creator"):
        await update.message.reply_text(
            "Ye command sirf group admins use kar sakte hain 🛡️"
        )
        return

    group_enabled[chat.id] = True

    await update.message.reply_text(
        "Mayraa AI group mode ON ho gaya! 💗🎀\n"
        "Ab mujhe mention karo ya mere message ka reply do."
    )


async def ai_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat

    if chat.type == "private":
        await update.message.reply_text(
            "Private chat AI ko is command se band nahi kiya jaata."
        )
        return

    member = await context.bot.get_chat_member(
        chat.id,
        update.effective_user.id,
    )

    if member.status not in ("administrator", "creator"):
        await update.message.reply_text(
            "Ye command sirf group admins use kar sakte hain 🛡️"
        )
        return

    group_enabled[chat.id] = False

    await update.message.reply_text(
        "Mayraa AI group mode OFF ho gaya 🔕💗"
    )


# ---------- MESSAGE HANDLER ----------

async def handle_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):
    message = update.effective_message
    chat = update.effective_chat
    bot_username = context.bot.username.lower()

    if not message or not message.text:
        return

    text = message.text.strip()
    mentioned = f"@{bot_username}" in text.lower()

    replied_to_bot = (
        message.reply_to_message is not None
        and message.reply_to_message.from_user is not None
        and message.reply_to_message.from_user.id
        == context.bot.id
    )

    if chat.type != "private":
        if not group_enabled.get(chat.id, False):
            return

        # Smart mode: respond only to mentions or replies.
        if not mentioned and not replied_to_bot:
            return

        text = text.replace(
            f"@{context.bot.username}", ""
        ).strip()

        if not text and message.reply_to_message:
            text = message.reply_to_message.text or "Hello"

        if not text:
            text = "Hello Mayraa"

    await send_ai_reply(update, context, text)


# ---------- MAIN ----------

def main():
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("love", love))
    app.add_handler(CommandHandler("hug", hug))
    app.add_handler(CommandHandler("mood", mood))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(CommandHandler("ai_on", ai_on))
    app.add_handler(CommandHandler("ai_off", ai_off))

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            handle_message,
        )
    )

    logger.info("Mayraa AI is starting!")

    app.run_polling()


if __name__ == "__main__":
    main()
