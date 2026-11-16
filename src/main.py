"""NUOVO QUOTIDIANO bot: dalle testate del mondo al carosello Instagram.

Agli orari stabiliti (config.SLOTS):
 1. legge le notizie delle ultime ore dalle testate in sources.json;
 2. Claude sceglie la più importante non ancora trattata e la confronta con le altre testate;
 3. Claude scrive il carosello (titolo, slide, "perché ti riguarda", caption);
 4. crea le immagini con la grafica della pagina (foto dell'articolo in copertina, foto libere dentro);
 5. ti manda l'anteprima su Telegram (✅ / ❌ / 🔄) oppure, con AUTO_PUBLISH=1, pubblica e ti avvisa.

Uso:
  python src/main.py                 # resta acceso (mini PC) o LISTEN_MINUTES minuti (GitHub)
  python src/main.py --prova         # prepara UN carosello vero e lo salva in posts/, senza inviare nulla
  python src/main.py --demo          # solo grafica, con testi di esempio, niente internet
"""
from __future__ import annotations

import argparse
import datetime as dt
import io
import json
import sys
import time
import traceback
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image

import config
import instagram
import news
import photos
import render
import storage
import telegram_bot as bot
import writer

POSTS = config.ROOT / "posts"
ROME = ZoneInfo("Europe/Rome")


def now_rome() -> dt.datetime:
    return dt.datetime.now(ROME)


# ------------------------------------------------------------------ creazione del carosello

def _image(url: str) -> Image.Image | None:
    if not url:
        return None
    try:
        img = Image.open(io.BytesIO(news.download(url)))
        img.load()
        return img.convert("RGB")
    except Exception as e:
        print(f"immagine non scaricata {url}: {e}")
        return None


def build(s: dict, exclude: set[str] = frozenset(), log=print) -> dict | None:
    """Prepara un carosello completo. Ritorna i dati (immagini su disco) oppure None se non c'è niente di buono."""
    items = [i for i in news.fetch_items() if i.uid not in set(s["seen"]) | set(exclude)]
    log(f"{len(items)} notizie nuove dalle testate")
    choice = writer.pick(items, [t["topic"] for t in s["topics"]])
    if not choice:
        return None
    main, related = choice["main"], choice["related"]
    log(f"Scelta: {main.title} ({main.source}) — {choice['reason']}")

    sources, cover_candidates = [], []
    for it in [main] + related:
        sources.append(_article_source(it.link, it.source, it.title, it.summary, cover_candidates, it is main))
        if it.image:
            cover_candidates.append((it.image, "", it.source))

    return assemble(sources, cover_candidates, topic=choice["topic"], reason=choice["reason"],
                    uids=[main.uid] + [r.uid for r in related], log=log)


def _article_source(it_link: str, it_source: str, it_title: str, it_summary: str, cover_candidates: list,
                    with_cover: bool) -> dict:
    art = news.fetch_article(it_link)
    text = art["text"] if len(art["text"]) > 400 else f"{it_title}. {it_summary} {art['text']}"
    if with_cover:
        for url in art.get("images") or [art["image"]]:
            if url:
                cover_candidates.append((url, art["credit"], it_source))
    if art["image"]:
        cover_candidates.append((art["image"], art["credit"], it_source))
    return {"source": it_source, "title": it_title or art.get("title", ""), "link": it_link, "text": text}


def build_from_link(s: dict, url: str, log=print) -> dict | None:
    """Ricrea con la nostra identità la notizia di un link: articolo di giornale o post Instagram."""
    import hashlib
    from urllib.parse import urlparse
    uid = hashlib.sha1(url.split("?")[0].encode()).hexdigest()[:12]
    recent = news.fetch_items(hours=72)
    sources, cover_candidates, extra = [], [], ""
    if "instagram.com" in url:
        post = news.instagram_post(url)
        imgs = [im for im in (_image(u) for u in post["images"][:10]) if im is not None]
        if not imgs and not post["caption"]:
            raise RuntimeError("non riesco a leggere il post (è privato o Instagram blocca la lettura)")
        log(f"Post di @{post['username']}: {len(imgs)} slide lette")
        read = writer.read_post(imgs, post["caption"], post["username"])
        matches = writer.match_articles(read["ricerca"] + " — " + read["notizia"][:600], recent)
        for n, it in enumerate(matches):
            sources.append(_article_source(it.link, it.source, it.title, it.summary, cover_candidates, n == 0))
        sources.append({"source": f"post Instagram di @{post['username'] or 'sconosciuto'}", "title": read["ricerca"],
                        "link": url, "text": read["notizia"]})
        extra = ("Stai RICREANDO un post Instagram di un'altra pagina con la nostra identità: stessa notizia e "
                 "stessa scaletta delle slide, ma testi riscritti interamente con parole nostre (non copiare frasi). "
                 "Verifica i fatti sulle fonti giornalistiche; se un dato del post non è confermato dalle testate, "
                 "attribuiscilo o toglilo. Scaletta del post originale:\n- " + "\n- ".join(read["scaletta"]))
        topic = read["ricerca"]
        warn = "" if matches else "⚠️ Nessuna testata trovata su questa notizia: fatti presi solo dal post, controllali. "
    else:
        art = news.fetch_article(url)
        if len(art["text"]) < 300:
            raise RuntimeError("non riesco a leggere l'articolo (pagina a pagamento o bloccata)")
        site = art.get("site") or urlparse(url).netloc.replace("www.", "")
        title = art.get("title", "")
        for u in art.get("images") or [art["image"]]:
            if u:
                cover_candidates.append((u, art["credit"], site))
        sources.append({"source": site, "title": title, "link": url, "text": art["text"]})
        for it in writer.match_articles(title, [i for i in recent if i.link != url])[:2]:
            sources.append(_article_source(it.link, it.source, it.title, it.summary, cover_candidates, False))
        extra = ("Il carosello deve raccontare la notizia di questo articolo (FONTE 1); le altre fonti servono a "
                 "completarla e verificarla.")
        topic, warn = title, ""
    log(f"Fonti: {', '.join(x['source'] for x in sources)}")
    return assemble(sources, cover_candidates, topic=topic, reason=warn + "ricreata da un link che hai mandato",
                    uids=[uid], log=log, extra=extra)


def assemble(sources: list[dict], cover_candidates: list, topic: str, reason: str, uids: list[str],
             log=print, extra: str = "") -> dict:
    """Dai testi delle fonti al carosello finito: testi, foto, immagini, caption."""


    c = writer.write(sources, extra)
    slides = c["slide"][: config.SLIDES_MAX - 2]
    total = len(slides) + 2

    # --- copertina: la foto dell'articolo, solo se è abbastanza grande (niente foto sgranate)
    # copertina: la versione più grande disponibile della foto dell'articolo (niente foto sgranate)
    cover_img, credits, best = None, [], None
    tried = set()
    for url, credit, src in cover_candidates[:8]:
        if url in tried:
            continue
        tried.add(url)
        img = _image(url)
        if img is None:
            continue
        if best is None or img.width * img.height > best[0].width * best[0].height:
            best = (img, credit, src)
        if render.scale_needed(img, (render.W, render.H)) <= 1.15:
            break  # abbastanza grande per tutta la slide
    if best and best[0].width >= 940:  # largo almeno la slide: va in alto senza ingrandirla troppo
        cover_img = best[0]
        credits.append(("copertina", f"{best[1]} via {best[2]}" if best[1] else f"{best[2]} (foto dell'articolo)"))
    used: set[str] = set()
    cover_credit = credits[0][1] if credits else ""
    # foto interne: solo dove Claude, guardandole, conferma che c'entrano con il testo
    slide_photos: dict[int, tuple] = {}
    for i, sl in enumerate(slides):
        if sl.get("foto_ricerca") and sl.get("layout") in ("foto", "testo") and len(slide_photos) < 4:
            found = photos.best_for(sl, used, log)
            if found:
                slide_photos[i] = found
    if cover_img is None:  # nessuna foto d'articolo valida: usa la migliore foto verificata, se c'è
        if slide_photos:
            first = min(slide_photos)
            cover_img, cover_credit = slide_photos.pop(first)
            credits.append(("copertina", cover_credit))

    cid = now_rome().strftime("%Y%m%d-%H%M%S")
    folder = POSTS / cid
    files = [render.save(render.cover(cover_img, c["categoria"], c["titolo_copertina"],
                                      c.get("parole_evidenziate", []), cover_credit, total), folder / f"{cid}_01.jpg")]
    for n, sl in enumerate(slides, start=2):
        ph, cr = slide_photos.get(n - 2, (None, ""))
        if ph is not None:
            credits.append((f"slide {n}", cr))
            if sl.get("layout") == "testo":
                sl = {**sl, "layout": "foto"}
        files.append(render.save(render.content(sl, n, total, ph, cr), folder / f"{cid}_{n:02d}.jpg"))
    files.append(render.save(render.closing(c["perche_ti_riguarda"], total, total, [x["source"] for x in sources]), folder / f"{cid}_{total:02d}.jpg"))
    story = render.save(render.story(Image.open(files[0])), folder / f"{cid}_story.jpg")

    caption = writer.build_caption(c, sources, credits)
    (folder / "carosello.json").write_text(json.dumps({"carosello": c, "fonti": sources and [
        {k: v for k, v in x.items() if k != "text"} for x in sources], "crediti": credits},
        indent=1, ensure_ascii=False))
    return {"id": cid, "files": files, "story": story, "caption": caption, "topic": topic,
            "uids": uids, "reason": reason, "links": [x["link"] for x in sources]}


# ------------------------------------------------------------------ pubblicazione

def upload(car: dict, s: dict):
    keep = set(s["pending"]) | {car["id"]}
    storage.push_media(car["files"] + [car["story"]], keep)
    time.sleep(10)  # GitHub ha bisogno di qualche secondo per servire i file


def publish(car_id: str, n_slides: int, caption: str) -> str:
    urls = [storage.media_url(f"{car_id}_{i:02d}.jpg") for i in range(1, n_slides + 1)]
    media_id = instagram.publish_carousel(urls, caption)
    link = instagram.permalink(media_id)
    msg = f"✅ Carosello pubblicato {link}".strip()
    if config.AUTO_STORY:
        try:
            instagram.publish_story(storage.media_url(f"{car_id}_story.jpg"))
            msg += "\n📲 Storia pubblicata"
        except Exception as e:
            msg += f"\n⚠️ Storia non pubblicata: {e}"
    return media_id, msg


def remember(s: dict, car: dict):
    s["seen"].extend(car["uids"])
    s["topics"].append({"topic": car["topic"], "date": now_rome().isoformat(timespec="minutes")})
    today = now_rome().date().isoformat()
    s["daily"][today] = s["daily"].get(today, 0) + 1


def produce(s: dict, exclude: set[str] = frozenset(), why: str = "", link: str = "") -> bool:
    """Prepara un carosello e lo manda in anteprima (o lo pubblica). Ritorna True se ha fatto qualcosa."""
    if not config.ANTHROPIC_API_KEY:
        bot.notify("⚠️ Manca ANTHROPIC_API_KEY: non posso scrivere i caroselli.")
        return False
    car = build_from_link(s, link) if link else build(s, exclude)
    if not car:
        bot.notify("🤷 Nessuna notizia nuova abbastanza importante in questo momento.")
        return False
    remember(s, car)
    upload(car, s)
    if config.AUTO_PUBLISH:
        try:
            media_id, msg = publish(car["id"], len(car["files"]), car["caption"])
            s["published"][car["id"]] = media_id
            bot.notify(f"{msg}\n📰 {car['topic']}")
        except Exception as e:
            bot.notify(f"⚠️ Pubblicazione non riuscita ({car['topic']}): {e}")
        return True
    note = (f"ℹ️ NOTA PER TE (non viene pubblicata)\n{why}{car['topic']}\nPerché: {car['reason']}\nArticoli: "
            + "\n".join(car["links"]))
    mid = bot.send_preview(car["files"], car["caption"], car["id"], note)
    s["pending"][car["id"]] = {"message_id": mid, "caption": car["caption"], "n": len(car["files"]),
                               "uids": car["uids"], "topic": car["topic"],
                               "created": dt.datetime.now(dt.timezone.utc).isoformat()}
    return True


# ------------------------------------------------------------------ Telegram: pulsanti e comandi

def handle_updates(s: dict, wait: int = 0) -> bool:
    ups, s["tg_offset"] = bot.get_updates(s["tg_offset"], wait)
    changed = bool(ups)
    for action, arg, u in ups:
        if action == "cmd":
            handle_command(s, arg)
            continue
        if action == "link":
            bot.notify("⏳ Ricreo questa notizia con la nostra grafica… (2-4 minuti)")
            safe(lambda: produce(s, why="Dal tuo link: ", link=arg), "link")
            continue
        p = s["pending"].pop(arg, None)
        if not p:
            bot.ack(u, "Già gestito")
            continue
        if action == "no":
            bot.ack(u, "Scartato")
            bot.mark(p["message_id"], "❌ Scartato")
        elif action == "alt":
            bot.ack(u, "Cerco un'altra notizia…")
            bot.mark(p["message_id"], "🔄 Sostituito")
            s["topics"].append({"topic": p["topic"] + " (scartato)", "date": now_rome().isoformat(timespec="minutes")})
            safe(lambda: produce(s, set(p["uids"]), why="Alternativa: "), "nuova notizia")
        else:
            bot.ack(u, "Pubblico su Instagram…")
            try:
                media_id, msg = publish(arg, p["n"], p["caption"])
                s["published"][arg] = media_id
                bot.mark(p["message_id"], "✅ Pubblicato")
                bot.notify(msg)
            except Exception as e:
                s["pending"][arg] = p
                bot.restore_buttons(p["message_id"], arg)
                bot.notify(f"⚠️ Pubblicazione non riuscita: {e}\nPuoi riprovare con ✅.")
    return changed


def handle_command(s: dict, cmd: str):
    if cmd in ("/nuovo", "/ora"):
        bot.notify("⏳ Cerco la notizia più importante del momento…")
        safe(lambda: produce(s, why="Su richiesta: "), "/nuovo")
    elif cmd == "/pausa":
        s["paused"] = True
        bot.notify("⏸️ In pausa: non preparo caroselli finché non scrivi /riprendi.")
    elif cmd == "/riprendi":
        s["paused"] = False
        bot.notify("▶️ Ripreso.")
    elif cmd in ("/stato", "/start"):
        today = now_rome().date().isoformat()
        nxt = next((t for t in config.SLOTS if t > now_rome().strftime("%H:%M")), config.SLOTS[0] + " (domani)")
        bot.notify(f"📊 Oggi: {s['daily'].get(today, 0)} caroselli\n⏳ In attesa: {len(s['pending'])}\n"
                   f"🕐 Prossimo: {nxt}\n{'⏸️ IN PAUSA' if s.get('paused') else '▶️ Attivo'}"
                   f"\nModalità: {'pubblicazione automatica' if config.AUTO_PUBLISH else 'approvazione con ✅'}\n\n"
                   "Comandi: /nuovo /stato /pausa /riprendi\nOppure mandami un link (articolo o post Instagram) e lo ricreo.")


def due_slot(s: dict) -> str | None:
    """L'orario da servire adesso (entro 90 minuti dall'orario previsto), se non già fatto."""
    n = now_rome()
    today = n.date().isoformat()
    done = s["slots_done"].setdefault(today, [])
    for t in config.SLOTS:
        h, m = map(int, t.split(":"))
        slot = n.replace(hour=h, minute=m, second=0, microsecond=0)
        if t not in done and slot <= n < slot + dt.timedelta(minutes=90):
            return t
    return None


def expire_pending(s: dict):
    now = dt.datetime.now(dt.timezone.utc)
    for cid, p in list(s["pending"].items()):
        if now - dt.datetime.fromisoformat(p["created"]) > dt.timedelta(hours=config.PENDING_HOURS):
            s["pending"].pop(cid)
            bot.mark(p["message_id"], "⌛ Scaduto")


def maybe_refresh_token(s: dict):
    if not config.IG_TOKEN_EXPIRES or not config.IG_TOKEN:
        return
    today = dt.date.today()
    last = dt.date.fromisoformat(s["last_refresh"]) if s["last_refresh"] else None
    if last and (today - last).days < 7:
        return
    try:
        res = instagram.refresh_token()
        s["last_refresh"] = today.isoformat()
        if res.get("access_token") and res["access_token"] != config.IG_TOKEN:
            bot.notify("🔑 Nuovo token Instagram: aggiorna IG_ACCESS_TOKEN con questo valore:\n\n" + res["access_token"])
    except Exception as e:
        bot.notify(f"⚠️ Non riesco a rinnovare il token Instagram: {e}")


def safe(fn, what: str):
    try:
        return fn()
    except Exception as e:
        traceback.print_exc()
        try:
            bot.notify(f"⚠️ Errore ({what}): {e}")
        except Exception:
            pass


def tick(s: dict) -> bool:
    """Controlli periodici: anteprime scadute e orari di pubblicazione."""
    expire_pending(s)
    slot = due_slot(s)
    if not slot or s.get("paused"):
        return False
    s["slots_done"][now_rome().date().isoformat()].append(slot)
    if s["daily"].get(now_rome().date().isoformat(), 0) >= config.MAX_PER_DAY:
        return True
    if instagram.publishing_room() < 2:
        bot.notify("⏸️ Limite giornaliero di Instagram quasi raggiunto: salto questo giro.")
        return True
    safe(lambda: produce(s, why=f"Ore {slot} · "), f"carosello delle {slot}")
    return True


def code_changed() -> bool:
    """True se su GitHub c'è una versione nuova del codice: il bot si chiude e riparte aggiornato."""
    try:
        import subprocess
        remote = subprocess.run(["git", "ls-remote", "origin", "refs/heads/main"], cwd=config.ROOT,
                                capture_output=True, text=True, timeout=30).stdout.split()
        local = storage.git("rev-parse", "HEAD")
        if not remote or remote[0] == local:
            return False
        # cambiano solo lo stato o le immagini? allora non serve riavviare
        storage.git("fetch", "-q", "--depth=20", "origin", "main", check=False)
        changed = storage.git("diff", "--name-only", "HEAD", "FETCH_HEAD", check=False).split()
        return any(not f.startswith(("state.json", "posts/")) for f in changed)
    except Exception:
        return False


def run():
    s = storage.load_state()
    end = time.time() + config.LISTEN_MINUTES * 60 if config.LISTEN_MINUTES else float("inf")
    safe(lambda: maybe_refresh_token(s), "token")
    next_tick = 0.0
    try:
        while time.time() < end - 60:
            changed = False
            try:
                changed = handle_updates(s, wait=50)
            except Exception as e:
                print(f"Telegram: {e}", file=sys.stderr)
                time.sleep(10)
            if time.time() >= next_tick:
                next_tick = time.time() + 120
                changed = bool(safe(lambda: tick(s), "giro")) or changed
                if config.LISTEN_MINUTES and code_changed():
                    print("Codice aggiornato su GitHub: riparto con la nuova versione")
                    break
            if changed:
                storage.save_state(s)
    finally:
        storage.save_state(s)


# ------------------------------------------------------------------ prove

def prova():
    s = storage.load_state()
    car = build(s)
    if not car:
        print("Nessuna notizia scelta.")
        return
    print(f"\nCarosello pronto in {car['files'][0].parent}\n\n{car['caption']}")


def demo():
    """Solo grafica, nessuna rete: utile per ritoccare render.py."""
    c = {"categoria": "ECONOMIA", "titolo_copertina": "La BCE taglia ancora i tassi: mutui più leggeri da dicembre",
         "parole_evidenziate": ["taglia", "mutui"], "slide": [
             {"layout": "testo", "occhiello": "COSA È SUCCESSO", "titolo": "Tassi giù di un quarto di punto",
              "testo": "Testo di esempio: qui va il fatto principale, in frasi brevi."},
             {"layout": "dato", "occhiello": "IL NUMERO", "numero": "1,75%", "titolo": "Il nuovo tasso",
              "testo": "Testo di esempio per spiegare il numero."},
             {"layout": "citazione", "occhiello": "LA FRASE", "testo": "Una citazione di esempio, tra virgolette.",
              "autore": "Nome Cognome, ruolo"}],
         "perche_ti_riguarda": "Testo di esempio: cosa cambia per chi vive in Italia."}
    total = len(c["slide"]) + 2
    out = POSTS / "demo"
    render.save(render.cover(None, c["categoria"], c["titolo_copertina"], c["parole_evidenziate"], "", total), out / "01.jpg")
    for n, sl in enumerate(c["slide"], start=2):
        render.save(render.content(sl, n, total), out / f"{n:02d}.jpg")
    render.save(render.closing(c["perche_ti_riguarda"], total, total, ["BBC News", "Financial Times", "Reuters"]), out / f"{total:02d}.jpg")
    print(f"Demo salvata in {out}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--prova", action="store_true")
    ap.add_argument("--demo", action="store_true")
    a = ap.parse_args()
    try:
        prova() if a.prova else demo() if a.demo else run()
    except Exception:
        traceback.print_exc()
        if config.BOT_TOKEN and config.ADMIN_CHAT_ID and not (a.prova or a.demo):
            try:
                bot.notify("⚠️ NUOVO QUOTIDIANO bot: errore\n" + traceback.format_exc()[-800:])
            except Exception:
                pass
        sys.exit(1)
