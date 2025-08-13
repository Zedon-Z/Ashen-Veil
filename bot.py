#!/usr/bin/env python3
"""
The Ashen Veil — FINAL Telegram Cinematic Bot
--------------------------------------------
• PTB v20+ Application (async).
• No schedulers / JobQueue. Uses edit_message_text + asyncio.sleep for animations.
• Full expanded arcs: Morgue Path, Flood Cover-Up, Archivist Betrayal.
• Optional OpenAI NPC responses if OPENAI_API_KEY is set.
• Replace MEDIA[...] URLs with your hosted assets (images/audio).
• Run: pip install -U python-telegram-bot==20.7
       export BOT_TOKEN="..." 
       python ashen_veil_final.py
"""

from __future__ import annotations
import asyncio
import json
import logging
import os
import random
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ParseMode, Update
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("ashen-veil-final")

# ----------------------------
# Optional OpenAI support
# ----------------------------
USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
if USE_OPENAI:
    try:
        import openai  # type: ignore

        openai.api_key = os.getenv("OPENAI_API_KEY")
    except Exception as e:
        log.warning("OpenAI import error: %s", e)
        USE_OPENAI = False

# ----------------------------
# Media placeholders: replace with final assets
# ----------------------------
MEDIA = {
    "rain_gif": "https://files.catbox.moe/5t0o3x.gif",
    "death_cert": "https://files.catbox.moe/1wk2nq.jpg",
    "newspaper": "https://files.catbox.moe/9h9n9r.jpg",
    "hallway": "https://files.catbox.moe/d0g5qv.jpg",
    "drip_audio": "https://files.catbox.moe/b7o3pn.mp3",
    "bar": "https://files.catbox.moe/6w2l6l.jpg",
    "bodybag": "https://files.catbox.moe/3b7p2z.jpg",
    "morgue_interior": "https://files.catbox.moe/abcd01.jpg",
    "toe_tag": "https://files.catbox.moe/toetag.jpg",
    "flood_map": "https://files.catbox.moe/floodmap.jpg",
    "archivist_portrait": "https://files.catbox.moe/archivist.jpg",
    "flashlight_gif": "https://files.catbox.moe/flashlight.gif",
    "heartbeat_mp3": "https://files.catbox.moe/heartbeat.mp3",
    "static_audio": "https://files.catbox.moe/static.mp3",
    "final_clip": "https://files.catbox.moe/finalvideo.mp4",
}

# ----------------------------
# Simple data models
# ----------------------------
ACT_1, ACT_2, ACT_3, ACT_4, ACT_5, THE_END = range(6)


@dataclass
class Session:
    chat_id: int
    owner_id: int
    act: int = ACT_1
    step: int = 0
    inventory: List[str] = field(default_factory=list)
    evidence: List[str] = field(default_factory=list)
    flags: Dict[str, Any] = field(default_factory=dict)
    pinned_msg_id: Optional[int] = None


SESSIONS: Dict[int, Session] = {}

# ----------------------------
# Cinematic helpers (no blocking long sleeps)
# ----------------------------


async def send_typing(context: ContextTypes.DEFAULT_TYPE, chat_id: int, seconds: float = 0.9):
    """Show typing for `seconds` and sleep."""
    try:
        await context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    except Exception:
        pass
    await asyncio.sleep(seconds)


async def send_text(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, delay: float = 0.0, parse: Optional[str] = None):
    if delay > 0:
        await asyncio.sleep(delay)
    await send_typing(context, chat_id, min(2.0, 0.4 + len(text) / 140))
    return await context.bot.send_message(chat_id, text, parse_mode=parse)


async def send_media_photo(context: ContextTypes.DEFAULT_TYPE, chat_id: int, url: str, caption: Optional[str] = None):
    await send_typing(context, chat_id, 0.8)
    try:
        return await context.bot.send_photo(chat_id, url, caption=caption)
    except Exception:
        return await context.bot.send_message(chat_id, caption or "📷 (image)", parse_mode=ParseMode.MARKDOWN)


async def animate_frames(context: ContextTypes.DEFAULT_TYPE, chat_id: int, frames: List[str], parse: Optional[str] = None, beat: float = 1.1):
    """Send first frame then edit message for each subsequent frame; fallback to sending new messages if edits fail."""
    if not frames:
        return await send_text(context, chat_id, "...")
    msg = await context.bot.send_message(chat_id, frames[0], parse_mode=parse)
    for f in frames[1:]:
        await asyncio.sleep(beat)
        try:
            await context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f, parse_mode=parse)
        except Exception:
            msg = await context.bot.send_message(chat_id, f, parse_mode=parse)
    return msg


async def show_buttons(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, choices: List[Tuple[str, str]], delay: float = 0.0):
    if delay:
        await asyncio.sleep(delay)
    await send_typing(context, chat_id, 0.6)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)] for label, cb in choices])
    return await context.bot.send_message(chat_id, text, reply_markup=kb)


async def pin_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, msg_id: int):
    try:
        await context.bot.pin_chat_message(chat_id, msg_id, disable_notification=True)
    except Exception:
        pass


async def unpin_all(context: ContextTypes.DEFAULT_TYPE, chat_id: int):
    try:
        await context.bot.unpin_all_chat_messages(chat_id)
    except Exception:
        pass


# ----------------------------
# Lightweight NPC AI (optional OpenAI)
# ----------------------------


async def npc_reply(npc_name: str, player_text: str, sess: Session) -> str:
    """Return a reply from an NPC; uses OpenAI if configured; otherwise rule-based."""
    player_text = (player_text or "").strip()
    # Try OpenAI (async wrapper)
    if USE_OPENAI:
        try:
            # We'll use a minimal ChatCompletion wrapper via thread to avoid blocking the event loop.
            import openai
            from functools import partial

            system = (
                f"You are {npc_name}, a character in a moody cinematic mystery. "
                "Reply briefly (<= 2 sentences), in-character, atmospheric, and emotional."
            )

            def call_openai():
                return openai.ChatCompletion.create(
                    model=OPENAI_MODEL,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": player_text[:800]},
                    ],
                    temperature=0.8,
                    max_tokens=120,
                )

            resp = await asyncio.to_thread(call_openai)
            text = resp["choices"][0]["message"]["content"].strip()
            return text
        except Exception as e:
            log.warning("OpenAI call failed: %s", e)

    # Rule-based fallback
    low = player_text.lower()
    if any(w in low for w in ("where", "who", "why", "how", "when")):
        return random.choice(
            [
                "The town keeps maps of lies in its drawers.",
                "Ask the Archivist — every paper is a riddle.",
                "Sometimes the answer is a name you don't know you remember.",
            ]
        )
    if any(w in low for w in ("save", "help", "please", "can't", "won't")):
        return random.choice(
            [
                "Stay with me. We'll breathe together until dawn.",
                "I can feel the rain on the other side of the glass. It's colder there.",
                "We choose people over truths when we're afraid.",
            ]
        )
    return random.choice(
        [
            "I dreamed of the chapel last night. It had no roof but kept singing.",
            "You move like someone who knows the final line but not the first word.",
            "If you listen very carefully, the town will tell you what it wants to forget.",
        ]
    )


# ----------------------------
# Full cinematic flows (expanded arcs)
# ----------------------------


async def act1_opening(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    await animate_frames(
        context,
        chat,
        [
            "🌧 *W  E  L  C  _  M  E   T O   C R E S T F A L L*",
            "🌧 *The rain tastes like salt…*",
            "🌧 *You’ve been gone 14 years.*",
        ],
        parse=ParseMode.MARKDOWN,
        beat=1.0,
    )
    await send_media_photo(context, chat, MEDIA["death_cert"], caption="*Tomorrow.* Your name. Signed in a dead hand.")
    await show_buttons(
        context,
        chat,
        "Where do you go first?",
        [("🔍 Inspect the package", "a1_pkg"), ("🏛 Town hall", "a1_hall"), ("⚓ Docks", "a1_docks")],
    )
    # small ominous close
    await asyncio.sleep(0.6)
    await send_media_photo(context, chat, MEDIA["newspaper"], caption="*LOCAL RESIDENT LAID TO REST* — dated tomorrow.")


async def act2_fracture(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    await send_text(
        context,
        chat,
        "Crestfall sleeps with one eye open.\nEvery window reflects something that isn’t there.\nThe streets feel stretched… like time’s been pulled thin.",
    )
    await show_buttons(
        context,
        chat,
        "Where to begin?",
        [("🏚 Old home", "a2_home"), ("📂 Police archives", "a2_arch"), ("🌲 Forest clearing", "a2_forest")],
    )


async def act3_investigate(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    await animate_frames(context, chat, ["⛈ *The storm hasn’t stopped…*", "🧵 *You’re being threaded somewhere.*"], parse=ParseMode.MARKDOWN, beat=1.0)
    await show_buttons(
        context,
        chat,
        "Interrogations — who do you confront?",
        [("🥃 Merrick (bar)", "a3_merrick"), ("📖 Archivist (archives)", "a3_archivist"), ("📞 Call the unknown number", "a3_call")],
    )


async def act4_collapse(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    await animate_frames(
        context,
        chat,
        [
            "[03:12] She was already dead when you found her.",
            "[02:56] You can still save her.",
            "[03:08] Why is there blood on your hands?",
        ],
        beat=0.9,
    )
    await send_text(context, chat, "*The investigation isn’t about the fire. It’s about who lit the match.*", parse=ParseMode.MARKDOWN)
    await send_text(context, chat, "And every version says it was *you*.", parse=ParseMode.MARKDOWN)
    await show_buttons(
        context,
        chat,
        "Pre-finale — choose your approach:",
        [("🕰 Break the cycle", "a4_break"), ("🔥 Let it burn", "a4_burn"), ("🩸 Hunt your other self", "a4_hunt")],
    )


async def act5_finale(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    await animate_frames(context, chat, ["\n\nThe match is already lit.", "The room inhales.", "Silence. Then heat."], beat=1.0)
    await show_buttons(
        context,
        chat,
        "Final choice — the consequence will echo:",
        [("👧 Save the girl", "end_save"), ("🪞 Break the veil", "end_veil"), ("🔥 Let it burn", "end_burn")],
    )


# ----------------------------
# Extended Scenes: Morgue Path
# ----------------------------
async def morgue_sequence(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    # Enter
    await send_text(context, chat, "You slip through the morgue door. The air tastes of iron and old paper.", delay=0.6)
    await send_media_photo(context, chat, MEDIA["morgue_interior"], caption="Fluorescent lights stutter above a row of metal drawers.")
    # flashlight sweep (frame edits)
    frames = [
        "🔦 *Flashlight on: corridor. Rows and rows of drawers.*",
        "🔦 *Flashlight: a toe tag flutters under a sheet — name blurred.*",
        "🔦 *The beam finds a small yellow raincoat, folded beside a cold tray.*",
    ]
    await animate_frames(context, chat, frames, parse=ParseMode.MARKDOWN, beat=1.1)
    # heartbeat SFX hint (attempt to send audio; if fails, text hint)
    try:
        await context.bot.send_audio(chat, MEDIA["heartbeat_mp3"], caption="A distant heartbeat — is it yours?", timeout=20)
    except Exception:
        await send_text(context, chat, "_You feel your pulse quicken._", parse=ParseMode.MARKDOWN)
    # Toe-tag reading — progressive reveal using edits
    tag_lines = [
        "TOE TAG: [ █████████ ]",
        "TOE TAG: [ E.  G R A Y ]",
        "TOE TAG: [ L I L A  G R A Y ]",
    ]
    msg = await context.bot.send_message(chat, tag_lines[0], parse_mode=ParseMode.MARKDOWN)
    for line in tag_lines[1:]:
        await asyncio.sleep(1.2)
        try:
            await context.bot.edit_message_text(chat_id=chat, message_id=msg.message_id, text=line, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            msg = await context.bot.send_message(chat, line, parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(0.8)
    # Decision: resuscitate? call help? or record evidence
    await show_buttons(
        context,
        chat,
        "The tag says Lila Gray. You can try to revive, call for help, or quietly take evidence.",
        [("🔁 Attempt revival", "morg_revive"), ("📢 Call for help", "morg_call"), ("📸 Photograph quietly", "morg_photo")],
    )


# ----------------------------
# Extended Scenes: Flood Cover-Up
# ----------------------------
async def flood_cover_sequence(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    await send_text(context, chat, "You find a stack of waterlogged rescue maps in a locked cabinet.", delay=0.6)
    await send_media_photo(context, chat, MEDIA["flood_map"], caption="An old map with routes circled and one symbol repeated — a black veil emblem.")
    # Animate discovery of annotation with edit frames
    frames = [
        "Map annotation: *Rescue route A — CLEAR*",
        "Map annotation: *Rescue route B — DIVERTED*",
        "Map annotation: *Official: 'Flood response — see addendum 11' — but addendum missing.*",
    ]
    await animate_frames(context, chat, frames, parse=ParseMode.MARKDOWN, beat=1.0)
    await send_text(context, chat, "A corner of the page has been burned methodically — someone tried to hide a signature.")
    # Present choice: leak or hide
    await show_buttons(
        context,
        chat,
        "You can photocopy and leak these maps, keep them for the archives, or burn them to protect someone.",
        [("🖨 Leak copies (public)", "flood_leak"), ("🗄 Store in archive (quiet)", "flood_archive"), ("🔥 Burn to protect", "flood_burn")],
    )


# ----------------------------
# Extended Scenes: Archivist Betrayal
# ----------------------------
async def archivist_betrayal_sequence(context: ContextTypes.DEFAULT_TYPE, sess: Session):
    chat = sess.chat_id
    await send_media_photo(context, chat, MEDIA["archivist_portrait"], caption="The Archivist removes their glasses. Their eyes are clearer than you'd expect.")
    await send_text(context, chat, "'I have been arranging the files for years,' they whisper. 'I only rearranged what had to be hidden.'", delay=0.8)
    # Illusion: message edits that rewrite their words
    m = await context.bot.send_message(chat, "Archivist: 'You shouldn't dig further.'")
    await asyncio.sleep(1.0)
    try:
        await context.bot.edit_message_text(chat_id=chat, message_id=m.message_id, text="Archivist: 'You should stop. You will only hurt yourself.'")
    except Exception:
        await context.bot.send_message(chat, "Archivist: 'You should stop. You will only hurt yourself.'")
    await asyncio.sleep(1.0)
    # Fake bot "glitch" — forward/delete style
    await context.bot.send_message(chat, "_System: restoring archive snapshot..._", parse_mode=ParseMode.MARKDOWN)
    await asyncio.sleep(0.9)
    await context.bot.send_message(chat, "_System: archive restored._", parse_mode=ParseMode.MARKDOWN)
    # Their last line becomes betrayal
    await send_text(context, chat, "Archivist: 'We promised to keep you safe. We also promised the town survived.'", delay=0.8)
    await show_buttons(
        context,
        chat,
        "Archivist reveals they helped cover the flood response. Choose how to react:",
        [("⚖️ Confront and demand truth", "arch_confront"), ("🧭 Secretly record them", "arch_record"), ("💔 Walk away silently", "arch_leave")],
    )


# ----------------------------
# Button handler / branching logic
# ----------------------------


async def on_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    chat = query.message.chat
    sess = SESSIONS.get(chat.id)
    if not sess:
        await query.edit_message_text("Session expired. Use /start to begin again.")
        return

    # ACT 1 choices
    if data == "a1_pkg":
        sess.flags["heard_cassette"] = True
        await send_text(context, chat.id, "The cassette crackles: 'Find the girl. Don’t trust anyone. Not even me.'", delay=0.3)
        # move forward
        await asyncio.sleep(0.4)
        sess.act = ACT_2
        await act2_fracture(context, sess)
        return
    if data == "a1_hall":
        sess.flags["met_archivist"] = True
        await send_text(context, chat.id, "The Archivist’s eyes are clouded. 'People who come back don’t leave the same way.'")
        await asyncio.sleep(0.4)
        sess.act = ACT_2
        await act2_fracture(context, sess)
        return
    if data == "a1_docks":
        sess.flags["met_merrick"] = True
        await send_text(context, chat.id, "Merrick smells of gasoline and old rain. 'You were lucky once,' he says.")
        await asyncio.sleep(0.4)
        sess.act = ACT_2
        await act2_fracture(context, sess)
        return

    # ACT 2 choices
    if data == "a2_home":
        sess.evidence.append("locked_room")
        await send_text(context, chat.id, "Your old bedroom is locked from the inside. The handle is warm.")
        await asyncio.sleep(0.6)
        sess.act = ACT_3
        await act3_investigate(context, sess)
        return
    if data == "a2_arch":
        sess.evidence.append("file_evelyn")
        await send_text(context, chat.id, "FILE #03 — Evelyn Marks, Missing. Note in margin: NOT AN ACCIDENT. SAME AS 1992.")
        await asyncio.sleep(0.6)
        sess.act = ACT_3
        await act3_investigate(context, sess)
        return
    if data == "a2_forest":
        sess.evidence.append("forest_disturbance")
        await send_text(context, chat.id, "The ground is soft. Something stirs beneath it.")
        await asyncio.sleep(0.6)
        sess.act = ACT_3
        await act3_investigate(context, sess)
        return

    # ACT 3 choices
    if data == "a3_merrick":
        sess.flags["merrick_photo"] = True
        await send_media_photo(context, chat.id, MEDIA["bar"], caption="Merrick: 'You don’t remember the fire, do you?'\nHe slides a half-burnt photo across the table.")
        await asyncio.sleep(0.8)
        # show half-burnt photo detail (simulate)
        await send_text(context, chat.id, "In the scorched photo, a small figure in a yellow raincoat stands beside you.")
        # morgue lead option now
        await show_buttons(context, chat.id, "Do you:", [("→ Go to the morgue (investigate)", "goto_morgue"), ("→ Check archives", "a3_archivist")])
        return
    if data == "a3_archivist":
        sess.flags["archive_tomorrow"] = True
        await send_text(context, chat.id, "Archivist: 'Some pages rearrange themselves when you aren’t looking.'")
        await asyncio.sleep(0.6)
        await sh
