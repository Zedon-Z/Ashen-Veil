#!/usr/bin/env python3
# The Ashen Veil — FINAL (PTB 13.15 compatible)
# Full downgrade from PTB v20 async -> PTB v13 sync.
from __future__ import annotations
import json
import logging
import os
import random
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# PTB 13.15 imports (sync)
from telegram import (
    Bot,
    Update,
    ParseMode,
    ChatAction,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Updater,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    Filters,
    CallbackContext,
)

# ----------------------------
# Logging
# ----------------------------
logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("ashen-veil-final-ptb13")

# ----------------------------
# Optional OpenAI support
# ----------------------------
USE_OPENAI = bool(os.getenv("OPENAI_API_KEY"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")
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
# Cinematic helpers (sync)
# ----------------------------
def send_typing(context: CallbackContext, chat_id: int, seconds: float = 0.9) -> None:
    try:
        context.bot.send_chat_action(chat_id, ChatAction.TYPING)
    except Exception:
        pass
    time.sleep(seconds)


def send_text(context: CallbackContext, chat_id: int, text: str, delay: float = 0.0, parse: Optional[str] = None):
    if delay > 0:
        time.sleep(delay)
    send_typing(context, chat_id, min(2.0, 0.4 + len(text) / 140.0))
    return context.bot.send_message(chat_id, text, parse_mode=parse)


def send_media_photo(context: CallbackContext, chat_id: int, url: str, caption: Optional[str] = None):
    send_typing(context, chat_id, 0.8)
    try:
        return context.bot.send_photo(chat_id, url, caption=caption)
    except Exception:
        return context.bot.send_message(chat_id, caption or "📷 (image)", parse_mode=ParseMode.MARKDOWN)


def animate_frames(context: CallbackContext, chat_id: int, frames: List[str], parse: Optional[str] = None, beat: float = 1.1):
    """Send first frame and edit it to create animation; fallback to sending new messages."""
    if not frames:
        return send_text(context, chat_id, "...")
    msg = context.bot.send_message(chat_id, frames[0], parse_mode=parse)
    for f in frames[1:]:
        time.sleep(beat)
        try:
            context.bot.edit_message_text(chat_id=chat_id, message_id=msg.message_id, text=f, parse_mode=parse)
        except Exception:
            msg = context.bot.send_message(chat_id, f, parse_mode=parse)
    return msg


def show_buttons(context: CallbackContext, chat_id: int, text: str, choices: List[Tuple[str, str]], delay: float = 0.0):
    if delay:
        time.sleep(delay)
    send_typing(context, chat_id, 0.6)
    kb = InlineKeyboardMarkup([[InlineKeyboardButton(label, callback_data=cb)] for label, cb in choices])
    return context.bot.send_message(chat_id, text, reply_markup=kb)


def pin_message(context: CallbackContext, chat_id: int, msg_id: int):
    try:
        context.bot.pin_chat_message(chat_id, msg_id, disable_notification=True)
    except Exception:
        pass


def unpin_all(context: CallbackContext, chat_id: int):
    try:
        context.bot.unpin_all_chat_messages(chat_id)
    except Exception:
        pass


# ----------------------------
# Lightweight NPC AI (sync)
# ----------------------------
def npc_reply(npc_name: str, player_text: str, sess: Session) -> str:
    player_text = (player_text or "").strip()
    if USE_OPENAI:
        try:
            system = (
                f"You are {npc_name}, a character in a moody cinematic mystery. "
                "Reply briefly (<= 2 sentences), in-character, atmospheric, and emotional."
            )
            resp = openai.ChatCompletion.create(
                model=OPENAI_MODEL,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": player_text[:800]},
                ],
                temperature=0.8,
                max_tokens=120,
            )
            text = resp["choices"][0]["message"]["content"].strip()
            return text
        except Exception as e:
            log.warning("OpenAI call failed: %s", e)

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
def act1_opening(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    animate_frames(
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
    send_media_photo(context, chat, MEDIA["death_cert"], caption="*Tomorrow.* Your name. Signed in a dead hand.")
    show_buttons(
        context,
        chat,
        "Where do you go first?",
        [("🔍 Inspect the package", "a1_pkg"), ("🏛 Town hall", "a1_hall"), ("⚓ Docks", "a1_docks")],
    )
    time.sleep(0.6)
    send_media_photo(context, chat, MEDIA["newspaper"], caption="*LOCAL RESIDENT LAID TO REST* — dated tomorrow.")


def act2_fracture(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    send_text(
        context,
        chat,
        "Crestfall sleeps with one eye open.\nEvery window reflects something that isn’t there.\nThe streets feel stretched… like time’s been pulled thin.",
    )
    show_buttons(
        context,
        chat,
        "Where to begin?",
        [("🏚 Old home", "a2_home"), ("📂 Police archives", "a2_arch"), ("🌲 Forest clearing", "a2_forest")],
    )


def act3_investigate(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    animate_frames(context, chat, ["⛈ *The storm hasn’t stopped…*", "🧵 *You’re being threaded somewhere.*"], parse=ParseMode.MARKDOWN, beat=1.0)
    show_buttons(
        context,
        chat,
        "Interrogations — who do you confront?",
        [("🥃 Merrick (bar)", "a3_merrick"), ("📖 Archivist (archives)", "a3_archivist"), ("📞 Call the unknown number", "a3_call")],
    )


def act4_collapse(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    animate_frames(
        context,
        chat,
        [
            "[03:12] She was already dead when you found her.",
            "[02:56] You can still save her.",
            "[03:08] Why is there blood on your hands?",
        ],
        beat=0.9,
    )
    send_text(context, chat, "*The investigation isn’t about the fire. It’s about who lit the match.*", parse=ParseMode.MARKDOWN)
    send_text(context, chat, "And every version says it was *you*.", parse=ParseMode.MARKDOWN)
    show_buttons(
        context,
        chat,
        "Pre-finale — choose your approach:",
        [("🕰 Break the cycle", "a4_break"), ("🔥 Let it burn", "a4_burn"), ("🩸 Hunt your other self", "a4_hunt")],
    )


def act5_finale(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    animate_frames(context, chat, ["\n\nThe match is already lit.", "The room inhales.", "Silence. Then heat."], beat=1.0)
    show_buttons(
        context,
        chat,
        "Final choice — the consequence will echo:",
        [("👧 Save the girl", "end_save"), ("🪞 Break the veil", "end_veil"), ("🔥 Let it burn", "end_burn")],
    )


# ----------------------------
# Extended Scenes: Morgue Path
# ----------------------------
def morgue_sequence(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    send_text(context, chat, "You slip through the morgue door. The air tastes of iron and old paper.", delay=0.6)
    send_media_photo(context, chat, MEDIA["morgue_interior"], caption="Fluorescent lights stutter above a row of metal drawers.")
    frames = [
        "🔦 *Flashlight on: corridor. Rows and rows of drawers.*",
        "🔦 *Flashlight: a toe tag flutters under a sheet — name blurred.*",
        "🔦 *The beam finds a small yellow raincoat, folded beside a cold tray.*",
    ]
    animate_frames(context, chat, frames, parse=ParseMode.MARKDOWN, beat=1.1)
    try:
        context.bot.send_audio(chat, MEDIA["heartbeat_mp3"], caption="A distant heartbeat — is it yours?", timeout=20)
    except Exception:
        send_text(context, chat, "_You feel your pulse quicken._", parse=ParseMode.MARKDOWN)
    tag_lines = [
        "TOE TAG: [ █████████ ]",
        "TOE TAG: [ E.  G R A Y ]",
        "TOE TAG: [ L I L A  G R A Y ]",
    ]
    msg = context.bot.send_message(chat, tag_lines[0], parse_mode=ParseMode.MARKDOWN)
    for line in tag_lines[1:]:
        time.sleep(1.2)
        try:
            context.bot.edit_message_text(chat_id=chat, message_id=msg.message_id, text=line, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            msg = context.bot.send_message(chat, line, parse_mode=ParseMode.MARKDOWN)
    time.sleep(0.8)
    show_buttons(
        context,
        chat,
        "The tag says Lila Gray. You can try to revive, call for help, or quietly take evidence.",
        [("🔁 Attempt revival", "morg_revive"), ("📢 Call for help", "morg_call"), ("📸 Photograph quietly", "morg_photo")],
    )


# ----------------------------
# Extended Scenes: Flood Cover-Up
# ----------------------------
def flood_cover_sequence(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    send_text(context, chat, "You find a stack of waterlogged rescue maps in a locked cabinet.", delay=0.6)
    send_media_photo(context, chat, MEDIA["flood_map"], caption="An old map with routes circled and one symbol repeated — a black veil emblem.")
    frames = [
        "Map annotation: *Rescue route A — CLEAR*",
        "Map annotation: *Rescue route B — DIVERTED*",
        "Map annotation: *Official: 'Flood response — see addendum 11' — but addendum missing.*",
    ]
    animate_frames(context, chat, frames, parse=ParseMode.MARKDOWN, beat=1.0)
    send_text(context, chat, "A corner of the page has been burned methodically — someone tried to hide a signature.")
    show_buttons(
        context,
        chat,
        "You can photocopy and leak these maps, keep them for the archives, or burn them to protect someone.",
        [("🖨 Leak copies (public)", "flood_leak"), ("🗄 Store in archive (quiet)", "flood_archive"), ("🔥 Burn to protect", "flood_burn")],
    )


# ----------------------------
# Extended Scenes: Archivist Betrayal
# ----------------------------
def archivist_betrayal_sequence(context: CallbackContext, sess: Session):
    chat = sess.chat_id
    send_media_photo(context, chat, MEDIA["archivist_portrait"], caption="The Archivist removes their glasses. Their eyes are clearer than you'd expect.")
    send_text(context, chat, "'I have been arranging the files for years,' they whisper. 'I only rearranged what had to be hidden.'", delay=0.8)
    m = context.bot.send_message(chat, "Archivist: 'You shouldn't dig further.'")
    time.sleep(1.0)
    try:
        context.bot.edit_message_text(chat_id=chat, message_id=m.message_id, text="Archivist: 'You should stop. You will only hurt yourself.'")
    except Exception:
        context.bot.send_message(chat, "Archivist: 'You should stop. You will only hurt yourself.'")
    time.sleep(1.0)
    context.bot.send_message(chat, "_System: restoring archive snapshot..._", parse_mode=ParseMode.MARKDOWN)
    time.sleep(0.9)
    context.bot.send_message(chat, "_System: archive restored._", parse_mode=ParseMode.MARKDOWN)
    send_text(context, chat, "Archivist: 'We promised to keep you safe. We also promised the town survived.'", delay=0.8)
    show_buttons(
        context,
        chat,
        "Archivist reveals they helped cover the flood response. Choose how to react:",
        [("⚖️ Confront and demand truth", "arch_confront"), ("🧭 Secretly record them", "arch_record"), ("💔 Walk away silently", "arch_leave")],
    )


# ----------------------------
# Button handler / branching logic
# ----------------------------
def on_button(update: Update, context: CallbackContext):
    query = update.callback_query
    if query is None:
        return
    data = query.data
    chat = query.message.chat
    sess = SESSIONS.get(chat.id)
    if not sess:
        try:
            query.edit_message_text("Session expired. Use /start to begin again.")
        except Exception:
            context.bot.send_message(chat.id, "Session expired. Use /start to begin again.")
        return

    # acknowledge
    try:
        query.answer()
    except Exception:
        pass

    # ACT 1 choices
    if data == "a1_pkg":
        sess.flags["heard_cassette"] = True
        send_text(context, chat.id, "The cassette crackles: 'Find the girl. Don’t trust anyone. Not even me.'", delay=0.3)
        time.sleep(0.4)
        sess.act = ACT_2
        act2_fracture(context, sess)
        return
    if data == "a1_hall":
        sess.flags["met_archivist"] = True
        send_text(context, chat.id, "The Archivist’s eyes are clouded. 'People who come back don’t leave the same way.'")
        time.sleep(0.4)
        sess.act = ACT_2
        act2_fracture(context, sess)
        return
    if data == "a1_docks":
        sess.flags["met_merrick"] = True
        send_text(context, chat.id, "Merrick smells of gasoline and old rain. 'You were lucky once,' he says.")
        time.sleep(0.4)
        sess.act = ACT_2
        act2_fracture(context, sess)
        return

    # ACT 2 choices
    if data == "a2_home":
        sess.evidence.append("locked_room")
        send_text(context, chat.id, "Your old bedroom is locked from the inside. The handle is warm.")
        time.sleep(0.6)
        sess.act = ACT_3
        act3_investigate(context, sess)
        return
    if data == "a2_arch":
        sess.evidence.append("file_evelyn")
        send_text(context, chat.id, "FILE #03 — Evelyn Marks, Missing. Note in margin: NOT AN ACCIDENT. SAME AS 1992.")
        time.sleep(0.6)
        sess.act = ACT_3
        act3_investigate(context, sess)
        return
    if data == "a2_forest":
        sess.evidence.append("forest_disturbance")
        send_text(context, chat.id, "The ground is soft. Something stirs beneath it.")
        time.sleep(0.6)
        sess.act = ACT_3
        act3_investigate(context, sess)
        return

    # ACT 3 choices
    if data == "a3_merrick":
        sess.flags["merrick_photo"] = True
        send_media_photo(context, chat.id, MEDIA["bar"], caption="Merrick: 'You don’t remember the fire, do you?'\nHe slides a half-burnt photo across the table.")
        time.sleep(0.8)
        send_text(context, chat.id, "In the scorched photo, a small figure in a yellow raincoat stands beside you.")
        show_buttons(context, chat.id, "Do you:", [("→ Go to the morgue (investigate)", "goto_morgue"), ("→ Check archives", "a3_archivist")])
        return
    if data == "a3_archivist":
        sess.flags["archive_tomorrow"] = True
        send_text(context, chat.id, "Archivist: 'Some pages rearrange themselves when you aren’t looking.'")
        time.sleep(0.6)
        show_buttons(context, chat.id, "Do you:", [("→ Press them for answers", "arch_press"), ("→ Search the morgue", "goto_morgue"), ("→ Call the number", "a3_call")])
        return
    if data == "a3_call":
        sess.flags["mystery_call"] = True
        send_text(context, chat.id, "'Get her out before the siren. They’ll bury the evidence in the flood.' The line dies.")
        time.sleep(0.8)
        show_buttons(context, chat.id, "Immediate options:", [("→ Morgue", "goto_morgue"), ("→ Flood maps", "goto_flood")])
        return

    # Morgue sub-choices
    if data == "goto_morgue":
        morgue_sequence(context, sess)
        return
    if data == "morg_revive":
        animate_frames(
            context,
            chat.id,
            [
                "🔁 *You slap cold water across her face.*",
                "🔁 *Her fingers twitch. The monitor blinks.*",
                "🔁 *A cough—then silence. She remembers you.*",
            ],
            parse=ParseMode.MARKDOWN,
            beat=1.0,
        )
        sess.flags["revived_lila"] = True
        sess.evidence.append("lila_alive")
        send_text(context, chat.id, "Lila: 'You came back.' Her voice is a brittle thing.", delay=0.6)
        show_buttons(context, chat.id, "Choices:", [("→ Hide her and flee", "morg_hide"), ("→ Confront Archivist with proof", "morg_confront_arch")])
        return
    if data == "morg_call":
        sess.evidence.append("guard_radio")
        send_text(context, chat.id, "You shout into the corridor. No one answers, but a guard's radio crackles distant: '—evacuation route B: diverted—'.")
        show_buttons(context, chat.id, "Do you:", [("→ Investigate Flood maps", "goto_flood"), ("→ Return quietly", "a3_archivist")])
        return
    if data == "morg_photo":
        sess.evidence.append("lila_photo")
        send_text(context, chat.id, "You take a photograph of the tag and the raincoat. It will be evidence if you survive to show it.")
        show_buttons(context, chat.id, [("→ Save and continue", "goto_flood"), ("→ Hide and run", "morg_hide")])
        return
    if data == "morg_hide":
        animate_frames(
            context,
            chat.id,
            ["🕶 *You wrap the coat and slip her into a satchel.*", "🕶 *You feel the weight of futures in the straps.*"],
            parse=ParseMode.MARKDOWN,
            beat=1.0,
        )
        sess.flags["lila_hidden"] = True
        send_text(context, chat.id, "You managed to hide Lila. For now.")
        sess.act = ACT_4
        act4_collapse(context, sess)
        return
    if data == "morg_confront_arch":
        sess.flags["confront_with_lila"] = True
        send_text(context, chat.id, "You march to the archives with a living girl folded into your coat. The Archivist freezes when you produce her.")
        time.sleep(0.8)
        archivist_betrayal_sequence(context, sess)
        return

    # Flood sub-choices
    if data == "goto_flood":
        flood_cover_sequence(context, sess)
        return
    if data == "flood_leak":
        sess.flags["leaked_maps"] = True
        animate_frames(
            context,
            chat.id,
            ["🖨 *You photocopy the maps and distribute them to the web.*", "🖨 *Two accounts take the files and disappear.*"],
            beat=1.0,
            parse=ParseMode.MARKDOWN,
        )
        send_text(context, chat.id, "News picks up the leak. The town trembles. Some names change in public records.")
        sess.act = ACT_4
        act4_collapse(context, sess)
        return
    if data == "flood_archive":
        sess.flags["kept_maps"] = True
        send_text(context, chat.id, "You tuck the maps into the archivist's private drawer. The truth remains a private coal.")
        sess.act = ACT_4
        act4_collapse(context, sess)
        return
    if data == "flood_burn":
        sess.flags["burned_maps"] = True
        animate_frames(context, chat.id, ["🔥 *You burn the maps.*", "🔥 *The smoke tastes like promises.*"], beat=1.0, parse=ParseMode.MARKDOWN)
        send_text(context, chat.id, "You burned the route that might have saved them. Your hands smell like ash.")
        sess.act = ACT_4
        act4_collapse(context, sess)
        return

    # Archivist path
    if data == "arch_press":
        archivist_betrayal_sequence(context, sess)
        return
    if data == "arch_confront":
        send_text(context, chat.id, "You press the Archivist for names. Their face finally breaks.")
        animate_frames(context, chat.id, ["Archivist: 'We made deals.'","Archivist: 'To keep the town, we buried certain truths.'","Archivist: 'We buried your family first.'"], beat=1.0, parse=ParseMode.MARKDOWN)
        sess.flags["arch_betrayal"] = True
        show_buttons(context, chat.id, "Next:", [("→ Expose to public", "arch_expose"), ("→ Record secretly", "arch_record"), ("→ Walk away", "arch_leave")])
        return
    if data == "arch_record":
        sess.flags["arch_recorded"] = True
        sess.act = ACT_4
        send_text(context, chat.id, "You secretly record them. The Archivist smiles sadly — they expected it.")
        send_text(context, chat.id, "Archivist: 'You always thought proof would heal you.'", delay=0.8)
        act4_collapse(context, sess)
        return
    if data == "arch_leave":
        sess.flags["arch_left"] = True
        sess.act = ACT_4
        send_text(context, chat.id, "You turn away. In the silence the town rearranges its chairs.")
        act4_collapse(context, sess)
        return
    if data == "arch_expose":
        sess.flags["arch_exposed"] = True
        sess.act = ACT_4
        animate_frames(context, chat.id, ["📣 *You publish the Archivist's confession.*","📣 *A noise like a century cracking answers loose.*"], beat=1.0, parse=ParseMode.MARKDOWN)
        send_text(context, chat.id, "Profiles in town shift as people learn to remember everything.")
        act4_collapse(context, sess)
        return

    # Act 4 routes
    if data == "a4_break":
        sess.flags["route"] = "break"
        animate_frames(context, chat.id, ["🕰 *You fold the timeline like wet paper.*","🕰 *Some names snap free, others stick.*"], parse=ParseMode.MARKDOWN, beat=1.0)
        if sess.flags.get("lila_hidden") or sess.flags.get("revived_lila"):
            send_text(context, chat.id, "You use Lila's presence as the anchor to pull time open.")
        sess.act = ACT_5
        act5_finale(context, sess)
        return
    if data == "a4_burn":
        sess.flags["route"] = "burn"
        animate_frames(context, chat.id, ["🔥 *You step into the heat.*","🔥 *Ash falls like slow rain.*"], parse=ParseMode.MARKDOWN, beat=1.0)
        sess.act = ACT_5
        act5_finale(context, sess)
        return
    if data == "a4_hunt":
        sess.flags["route"] = "hunt"
        animate_frames(context, chat.id, ["🩸 *You hunt your other self across mirrors.*","🩸 *At each reflection, a name slips.*"], parse=ParseMode.MARKDOWN, beat=1.0)
        sess.act = ACT_5
        act5_finale(context, sess)
        return

    # Endings
    if data == "end_save":
        if sess.flags.get("revived_lila") or sess.flags.get("lila_hidden"):
            animate_frames(context, chat.id, ["👧 *You hold Lila as the world frays.*","👧 *She coughs. The timeline shutters — then chooses mercy.*"], beat=1.0, parse=ParseMode.MARKDOWN)
            send_text(context, chat.id, "You saved her. The world forgets you kindly; you become a faded photograph in people's memories.")
            try:
                context.bot.send_video(chat.id, MEDIA["final_clip"], caption="You leave a mark no one can name.")
            except Exception:
                pass
        else:
            animate_frames(context, chat.id, ["👧 *You reach for her, hands find only smoke.*","👧 *There is a name on the lip of the flame.*"], beat=1.0, parse=ParseMode.MARKDOWN)
            send_text(context, chat.id, "You tried. The town keeps its secret. You keep the memory.")
        send_text(context, chat.id, "\n[GAME OVER] — *Saved, forgotten, eternal.*", parse=ParseMode.MARKDOWN)
        sess.act = THE_END
        return

    if data == "end_veil":
        animate_frames(context, chat.id, ["🪞 *The veil rips.*","🪞 *Everything remembers.*","🪞 *A terrible, beautiful quiet follows.*"], beat=1.0, parse=ParseMode.MARKDOWN)
        send_text(context, chat.id, "The town wakes to remember every loss. No one sleeps easily again.")
        send_text(context, chat.id, "\n[GAME OVER] — *Truth without peace.*", parse=ParseMode.MARKDOWN)
        sess.act = THE_END
        return

    if data == "end_burn":
        animate_frames(context, chat.id, ["🔥 *You let it burn.*","🔥 *Secrets cook until they are bones.*"], beat=1.0, parse=ParseMode.MARKDOWN)
        send_text(context, chat.id, "You keep your name. Others will have to answer later.")
        send_text(context, chat.id, "\n[GAME OVER] — *Survivor's quiet.*", parse=ParseMode.MARKDOWN)
        sess.act = THE_END
        return

    # fallback
    try:
        query.edit_message_text("…the world rearranges its punctuation.")
    except Exception:
        send_text(context, chat.id, "…the world rearranges its punctuation.")


# ----------------------------
# Commands
# ----------------------------
def cmd_start(update: Update, context: CallbackContext):
    chat = update.effective_chat
    user = update.effective_user
    if chat is None or user is None:
        return
    sess = Session(chat_id=chat.id, owner_id=user.id)
    SESSIONS[chat.id] = sess
    log.info("Session started: chat=%s user=%s", chat.id, user.id)
    send_text(context, chat.id, f"Welcome, {user.first_name}.", delay=0.2)
    act1_opening(context, sess)


def cmd_state(update: Update, context: CallbackContext):
    chat = update.effective_chat
    sess = SESSIONS.get(chat.id)
    if not sess:
        update.message.reply_text("No active session.")
        return
    update.message.reply_text(json.dumps(sess.__dict__, default=str, indent=2))


def cmd_reset(update: Update, context: CallbackContext):
    chat = update.effective_chat
    if chat:
        SESSIONS.pop(chat.id, None)
    update.message.reply_text("Session reset. /start to begin again.")


def cmd_talk(update: Update, context: CallbackContext):
    chat = update.effective_chat
    sess = SESSIONS.get(chat.id)
    if not sess:
        update.message.reply_text("/start first.")
        return
    args = context.args or []
    if len(args) < 2:
        update.message.reply_text("Usage: /talk <npc> <message>\nExample: /talk archivist tell me about the maps")
        return
    npc = args[0]
    msg = " ".join(args[1:])
    send_typing(context, chat.id, 0.8)
    reply = npc_reply(npc.title(), msg, sess)
    update.message.reply_text(f"{npc.title()}: {reply}")


# ----------------------------
# Error handler
# ----------------------------
def error_handler(update: object, context: CallbackContext):
    log.exception("Unhandled exception: %s", context.error)
    try:
        if isinstance(update, Update) and update.effective_chat:
            context.bot.send_message(update.effective_chat.id, "An error occurred. The story stutters; please /reset and try again.")
    except Exception:
        pass


# ----------------------------
# Bootstrap
# ----------------------------
def main():
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN environment variable is not set. Please set it in your host (Render/Heroku) environment.")
    # Build bot/updater for PTB 13.15
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher

    # Commands
    dp.add_handler(CommandHandler("start", cmd_start))
    dp.add_handler(CommandHandler("state", cmd_state))
    dp.add_handler(CommandHandler("reset", cmd_reset))
    dp.add_handler(CommandHandler("talk", cmd_talk))

    # Callbacks
    dp.add_handler(CallbackQueryHandler(on_button))

    # Text for NPC free-talk (if implemented)
    dp.add_handler(MessageHandler(Filters.text & ~Filters.command, lambda u, c: None))  # no-op default

    # Error handler
    dp.add_error_handler(error_handler)

    log.info("Starting The Ashen Veil (PTB 13.15) — polling...")
    updater.start_polling(clean=True)
    updater.idle()


if __name__ == "__main__":
    main()
