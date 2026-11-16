"""Bot Telegram: ti manda l'anteprima del carosello e legge i tuoi pulsanti e comandi.

Pulsanti sotto ogni anteprima:  ✅ Pubblica   ❌ Scarta   ✏️ Correggi   🔄 Un'altra notizia
Comandi da scrivere al bot:
  /nuovo   prepara subito un carosello con la notizia più importante del momento
  /stato   quanti caroselli oggi, quanti in attesa, prossimo orario
  /pausa   il bot smette di preparare caroselli (resta in ascolto)
  /riprendi
Oppure manda un link (articolo di giornale o post Instagram): il bot ricrea quella notizia con la nostra grafica.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

import config


# Chat a cui rispondere: chi ha scritto al bot (se autorizzato), altrimenti l'amministratore.
reply_to: str | None = None


def _chat(chat: str | None = None) -> str:
    return str(chat or reply_to or config.ADMIN_CHAT_ID)


def _api(method: str, **kwargs):
    for attempt in range(4):
        try:
            r = requests.post(f"https://api.telegram.org/bot{config.BOT_TOKEN}/{method}", timeout=90, **kwargs)
            break
        except requests.exceptions.RequestException:
            if attempt == 3:
                raise
            time.sleep(5 * (attempt + 1))
            for f in (kwargs.get("files") or {}).values():
                f.seek(0)
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram {method}: {data}")
    return data["result"]


def send_album(images: list[Path], chat: str | None = None) -> list[int]:
    """Le slide come album (massimo 10)."""
    files, media = {}, []
    for i, p in enumerate(images[:10]):
        files[f"f{i}"] = open(p, "rb")
        media.append({"type": "photo", "media": f"attach://f{i}"})
    try:
        msgs = _api("sendMediaGroup", data={"chat_id": _chat(chat), "media": json.dumps(media)}, files=files)
    finally:
        for f in files.values():
            f.close()
    return [m["message_id"] for m in msgs]


def keyboard(cid: str) -> str:
    return json.dumps({"inline_keyboard": [
        [{"text": "✅ Pubblica", "callback_data": f"ok:{cid}"},
         {"text": "❌ Scarta", "callback_data": f"no:{cid}"}],
        [{"text": "✏️ Correggi", "callback_data": f"fix:{cid}"},
         {"text": "🔄 Un'altra notizia", "callback_data": f"alt:{cid}"}]]})


def send_preview(images: list[Path], caption: str, cid: str, note: str = "", chat: str | None = None) -> int:
    send_album(images, chat)
    text = (f"{note}\n\n" if note else "") + "━━━━━━━━━━\n📝 CAPTION (viene pubblicata così)\n━━━━━━━━━━\n\n" + caption
    msg = _api("sendMessage", data={"chat_id": _chat(chat), "text": text[:4000],
                                     "reply_markup": keyboard(cid), "disable_web_page_preview": "true"})
    return msg["message_id"]


def get_updates(offset: int, wait: int = 0) -> tuple[list[tuple[str, str, dict]], int]:
    """Ritorna [(azione, argomento, update)], nuovo offset.
    azioni: ok / no / alt (pulsanti) oppure cmd (comando scritto, argomento = testo)."""
    updates = _api("getUpdates", data={"offset": offset, "timeout": wait,
                                       "allowed_updates": json.dumps(["callback_query", "message"])})
    out = []
    for u in updates:
        offset = max(offset, u["update_id"] + 1)
        cq = u.get("callback_query")
        if cq and str(cq["from"]["id"]) in config.ALLOWED_IDS:
            action, _, cid = cq.get("data", "").partition(":")
            if action in ("ok", "no", "alt", "fix"):
                out.append((action, cid, cq))
            continue
        m = u.get("message")
        if m and str(m.get("chat", {}).get("id")) not in config.ALLOWED_IDS and m.get("chat", {}).get("type") == "private":
            out.append(("denied", str(m["chat"]["id"]), m))
            continue
        if m and str(m.get("chat", {}).get("id")) in config.ALLOWED_IDS:
            text = m.get("text") or m.get("caption") or ""
            if text.startswith("/"):
                out.append(("cmd", text.split()[0].split("@")[0].lower(), m))
            elif text.strip():
                out.append(("text", text.strip(), m))
    return out, offset


def ack(cq: dict, text: str):
    try:
        _api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": text})
    except RuntimeError:
        pass


def mark(message_id: int, text: str, chat: str | None = None):
    try:
        _api("editMessageReplyMarkup", data={
            "chat_id": _chat(chat), "message_id": message_id,
            "reply_markup": json.dumps({"inline_keyboard": [[{"text": text, "callback_data": "noop"}]]})})
    except RuntimeError:
        pass


def restore_buttons(message_id: int, cid: str, chat: str | None = None):
    try:
        _api("editMessageReplyMarkup", data={"chat_id": _chat(chat), "message_id": message_id,
                                             "reply_markup": keyboard(cid)})
    except RuntimeError:
        pass


def ask(text: str):
    """Messaggio con risposta guidata (Telegram apre subito la tastiera per rispondere)."""
    _api("sendMessage", data={"chat_id": _chat(), "text": text,
                              "reply_markup": json.dumps({"force_reply": True, "input_field_placeholder": "Cosa correggo?"})})


def notify(text: str, chat: str | None = None):
    _api("sendMessage", data={"chat_id": _chat(chat), "text": text[:4000],
                              "disable_web_page_preview": "true"})
