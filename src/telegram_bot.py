"""Bot Telegram: ti manda l'anteprima del carosello e legge i tuoi pulsanti e comandi.

Pulsanti sotto ogni anteprima:  ✅ Pubblica   ❌ Scarta   🔄 Un'altra notizia
Comandi da scrivere al bot:
  /nuovo   prepara subito un carosello con la notizia più importante del momento
  /stato   quanti caroselli oggi, quanti in attesa, prossimo orario
  /pausa   il bot smette di preparare caroselli (resta in ascolto)
  /riprendi
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import requests

import config


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


def send_album(images: list[Path]) -> list[int]:
    """Le slide come album (massimo 10)."""
    files, media = {}, []
    for i, p in enumerate(images[:10]):
        files[f"f{i}"] = open(p, "rb")
        media.append({"type": "photo", "media": f"attach://f{i}"})
    try:
        msgs = _api("sendMediaGroup", data={"chat_id": config.ADMIN_CHAT_ID, "media": json.dumps(media)}, files=files)
    finally:
        for f in files.values():
            f.close()
    return [m["message_id"] for m in msgs]


def keyboard(cid: str) -> str:
    return json.dumps({"inline_keyboard": [
        [{"text": "✅ Pubblica", "callback_data": f"ok:{cid}"},
         {"text": "❌ Scarta", "callback_data": f"no:{cid}"}],
        [{"text": "🔄 Un'altra notizia", "callback_data": f"alt:{cid}"}]]})


def send_preview(images: list[Path], caption: str, cid: str, note: str = "") -> int:
    send_album(images)
    text = (f"{note}\n\n" if note else "") + "📝 CAPTION\n\n" + caption
    msg = _api("sendMessage", data={"chat_id": config.ADMIN_CHAT_ID, "text": text[:4000],
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
        if cq and str(cq["from"]["id"]) == str(config.ADMIN_CHAT_ID):
            action, _, cid = cq.get("data", "").partition(":")
            if action in ("ok", "no", "alt"):
                out.append((action, cid, cq))
            continue
        m = u.get("message")
        if m and str(m.get("chat", {}).get("id")) == str(config.ADMIN_CHAT_ID) and m.get("text", "").startswith("/"):
            out.append(("cmd", m["text"].split()[0].split("@")[0].lower(), m))
    return out, offset


def ack(cq: dict, text: str):
    try:
        _api("answerCallbackQuery", data={"callback_query_id": cq["id"], "text": text})
    except RuntimeError:
        pass


def mark(message_id: int, text: str):
    try:
        _api("editMessageReplyMarkup", data={
            "chat_id": config.ADMIN_CHAT_ID, "message_id": message_id,
            "reply_markup": json.dumps({"inline_keyboard": [[{"text": text, "callback_data": "noop"}]]})})
    except RuntimeError:
        pass


def restore_buttons(message_id: int, cid: str):
    try:
        _api("editMessageReplyMarkup", data={"chat_id": config.ADMIN_CHAT_ID, "message_id": message_id,
                                             "reply_markup": keyboard(cid)})
    except RuntimeError:
        pass


def notify(text: str):
    _api("sendMessage", data={"chat_id": config.ADMIN_CHAT_ID, "text": text[:4000],
                              "disable_web_page_preview": "true"})
