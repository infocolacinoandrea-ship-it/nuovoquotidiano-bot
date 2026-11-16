"""Claude sceglie la notizia del momento e la trasforma in un carosello NUOVO QUOTIDIANO."""
from __future__ import annotations

import datetime as dt
import json
from zoneinfo import ZoneInfo

import config
from news import Item

LINEA_EDITORIALE = """\
Sei il caporedattore di NUOVO QUOTIDIANO, pagina Instagram italiana di notizie dal mondo.
Pubblico: italiani che vogliono capire cosa succede nel mondo: geopolitica e guerre, grandi decisioni
di governi e istituzioni (UE, BCE, Fed, USA, Cina...), economia, mercati, grandi operazioni aziendali,
e soprattutto ciò che ricade sull'Italia (bollette, mutui, lavoro, export, sicurezza).
Tono: diretto, giornalistico, asciutto. Frasi brevi. Niente opinioni, niente tifo politico, niente
sensazionalismo falso: il titolo deve colpire ma restare vero.

Regole di accuratezza (non negoziabili):
- Usa SOLO fatti presenti nei testi forniti. Mai aggiungere dati, cifre, date o dichiarazioni a memoria.
- Cifre, nomi e date esattamente come nelle fonti. Se le fonti divergono, dillo ("secondo X..., secondo Y...").
- Ciò che è un'accusa, un annuncio o una stima va attribuito ("secondo...", "annuncia...", "stima...").
- Le citazioni devono essere frasi presenti nei testi, tradotte fedelmente in italiano.
- Se un fatto non è confermato, scrivilo ("non ancora confermato").
"""

PICK_TOOL = {
    "name": "scegli_notizia",
    "description": "Scegli la notizia da trasformare in carosello.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scelta": {"type": ["integer", "null"],
                       "description": "Numero della notizia principale, null se nessuna vale un carosello"},
            "stessa_storia": {"type": "array", "items": {"type": "integer"},
                              "description": "Altri numeri che parlano della STESSA notizia (altre testate), max 4"},
            "argomento": {"type": "string", "description": "Etichetta breve dell'argomento, per non ripeterlo, es. 'Fed taglia tassi novembre 2026'"},
            "motivo": {"type": "string", "description": "Una frase: perché è la più importante ora"},
        },
        "required": ["scelta", "stessa_storia", "argomento", "motivo"],
    },
}

SLIDE = {
    "type": "object",
    "properties": {
        "layout": {"type": "string", "enum": ["foto", "testo", "dato", "citazione"],
                   "description": "foto = foto in alto e testo sotto; testo = solo testo; dato = un numero gigante; citazione = una frase tra virgolette"},
        "occhiello": {"type": "string", "description": "2-4 parole maiuscole sopra il titolo, es. 'COSA È SUCCESSO'"},
        "titolo": {"type": "string", "description": "Massimo 9 parole"},
        "testo": {"type": "string", "description": "Massimo 45 parole, frasi brevi"},
        "numero": {"type": "string", "description": "Solo per layout dato: il numero CON la sua unità, comprensibile da solo, es. '4,25%', '12 mld €', '6 petroliere', '19 navi'. Mai un numero nudo."},
        "autore": {"type": "string", "description": "Solo per layout citazione: chi l'ha detto e ruolo"},
        "foto_ricerca": {"type": "string", "description": ("Facoltativo, su qualsiasi slide tranne citazione: 2-5 parole IN INGLESE per cercare "
                         "una foto reale che illustri ESATTAMENTE il contenuto della slide (persona citata, luogo, edificio, "
                         "istituzione, oggetto concreto: es. 'Christine Lagarde', 'Revolut app smartphone', 'Milan courthouse'). "
                         "Mettila solo dove una foto aggiunge qualcosa; ometti il campo se una foto sarebbe generica o forzata.")},
        "foto_tipo": {"type": "string", "enum": ["soggetto", "concetto"],
                      "description": "soggetto = persona, luogo, edificio, istituzione precisi; concetto = immagine generica"},
    },
    "required": ["layout", "occhiello", "titolo", "testo"],
}

WRITE_TOOL = {
    "name": "scrivi_carosello",
    "description": "Il carosello completo, pronto da impaginare.",
    "input_schema": {
        "type": "object",
        "properties": {
            "categoria": {"type": "string", "enum": ["GEOPOLITICA", "GUERRA", "ECONOMIA", "MERCATI", "BUSINESS",
                                                      "POLITICA", "EUROPA", "ENERGIA", "TECNOLOGIA", "ITALIA", "MONDO"]},
            "titolo_copertina": {"type": "string",
                                 "description": "Titolo-notizia della copertina, 8-16 parole, chiaro e forte, senza punto finale"},
            "parole_evidenziate": {"type": "array", "items": {"type": "string"},
                                   "description": "1-3 parole del titolo di copertina da colorare in verde (le più forti)"},
            "slide": {"type": "array", "items": SLIDE, "minItems": config.SLIDES_MIN - 2, "maxItems": config.SLIDES_MAX - 2,
                      "description": "Slide interne in ordine: cosa è successo, contesto, numeri, reazioni, cosa succede ora. Alterna i layout; usa 'foto' per 2-3 slide dove esiste un soggetto fotografabile preciso (le foto sono verificate: se non ce n'è una adatta la slide diventa solo testo)."},
            "perche_ti_riguarda": {"type": "string",
                                   "description": "Ultima slide: max 40 parole su cosa cambia per chi vive in Italia. Se non c'è un effetto concreto, spiega perché conta comunque."},
            "caption": {"type": "string",
                        "description": ("Caption Instagram in italiano con il tono di una testata giornalistica seria "
                                        "(come un lancio d'agenzia ben scritto), non di un influencer. "
                                        "Struttura: 1) prima riga: il fatto principale in una frase netta e concreta (chi, cosa, quanto), "
                                        "max 15 parole, che regge anche troncata nel feed; 2) riga vuota; 3) un paragrafo di 2-4 frasi "
                                        "con contesto e numeri chiave, attribuendo le fonti ('secondo Reuters...'); "
                                        "4) riga vuota; 5) una domanda breve e concreta per i commenti. "
                                        "NIENTE emoji, niente punti esclamativi, niente hashtag, niente 'link in bio', "
                                        "niente frasi fatte o sensazionalistiche ('incredibile', 'shock', 'ecco perché', 'non ci crederai').")},
            "hashtag": {"type": "array", "items": {"type": "string"}, "minItems": 4, "maxItems": 4,
                        "description": ("Esattamente 4 hashtag senza #, scelti per QUESTA notizia (il quinto, #nuovoquotidiano, "
                                        "lo aggiunge il sistema): 2-3 specifici (paese, istituzione, azienda o persona chiave, "
                                        "es. 'bce', 'iran', 'nvidia') e 1-2 di categoria in italiano molto cercati "
                                        "(es. 'economia', 'geopolitica', 'finanza', 'esteri'). Minuscolo, senza accenti né spazi, "
                                        "niente hashtag generici da spam né inventati.")},
        },
        "required": ["categoria", "titolo_copertina", "parole_evidenziate", "slide", "perche_ti_riguarda", "caption", "hashtag"],
    },
}


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _call(tool: dict, prompt: str, max_tokens: int = 4000, model: str = "") -> dict:
    """Chiede a Claude di rispondere con lo strumento `tool`.
    I modelli più recenti non accettano tool_choice forzato: si usa "auto" con l'istruzione esplicita,
    e se il modello risponde a testo si prova a leggere il JSON (poi un secondo tentativo)."""
    instr = (f"\n\nRispondi SOLO chiamando lo strumento `{tool['name']}` con tutti i campi richiesti. "
             "Non scrivere altro testo.")
    messages = [{"role": "user", "content": prompt + instr}]
    last_text = ""
    for attempt in range(2):
        msg = _client().messages.create(
            model=model or config.CLAUDE_MODEL, max_tokens=max_tokens, system=LINEA_EDITORIALE,
            tools=[tool], tool_choice={"type": "auto"}, messages=messages)
        for block in msg.content:
            if block.type == "tool_use" and block.name == tool["name"]:
                return block.input
        last_text = "".join(getattr(b, "text", "") for b in msg.content)
        parsed = _json_from_text(last_text)
        if parsed is not None:
            return parsed
        messages = messages + [{"role": "assistant", "content": msg.content},
                               {"role": "user", "content": f"Usa lo strumento `{tool['name']}` adesso."}]
    raise RuntimeError(f"Claude non ha restituito il formato atteso: {last_text[:300]}")


def _json_from_text(text: str):
    import re
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except Exception:
        return None


def pick(items: list[Item], recent_topics: list[str]) -> dict | None:
    """Ritorna {'main': Item, 'related': [Item], 'topic': str, 'reason': str} oppure None."""
    if not items:
        return None
    now = dt.datetime.now(ZoneInfo("Europe/Rome")).strftime("%A %d %B %Y, ore %H:%M")
    lines = []
    for n, it in enumerate(items[:120]):
        age = dt.datetime.now(dt.timezone.utc) - dt.datetime.fromisoformat(it.published)
        lines.append(f"[{n}] ({it.source}, {int(age.total_seconds() // 3600)}h fa) {it.title} — {it.summary[:220]}")
    prompt = (
        f"Adesso è {now} (ora italiana).\n\n"
        "Argomenti GIÀ trattati di recente (non ripeterli, a meno di uno sviluppo davvero nuovo e importante):\n"
        + ("\n".join(f"- {t}" for t in recent_topics[-40:]) or "- nessuno") +
        "\n\nNotizie delle ultime ore dalle testate:\n" + "\n".join(lines) +
        "\n\nScegli LA notizia più importante e interessante adesso per il nostro pubblico. Preferisci quelle "
        "riprese da più testate autorevoli, con conseguenze concrete, e quelle che si possono spiegare bene in "
        "un carosello. Evita cronaca nera, gossip, sport, curiosità, notizie leggere o 'strane', notizie locali "
        "straniere senza rilievo internazionale e notizie già vecchie. Se nessuna notizia è davvero rilevante, rispondi null: "
        "meglio saltare un giro che pubblicare una notizia debole."
    )
    res = _call(PICK_TOOL, prompt, 800, model=config.PICK_MODEL)
    n = res.get("scelta")
    if n is None or not (0 <= n < len(items)):
        return None
    related = [items[i] for i in res.get("stessa_storia", []) if 0 <= i < len(items) and i != n][:4]
    return {"main": items[n], "related": related, "topic": res.get("argomento", items[n].title),
            "reason": res.get("motivo", "")}


def write(sources: list[dict], extra: str = "") -> dict:
    """sources = [{'source','title','link','text'}]. Ritorna il carosello (dict di WRITE_TOOL)."""
    docs = "\n\n".join(
        f"=== FONTE {i + 1}: {s['source']} — {s['title']}\n{s['text'][:7000]}" for i, s in enumerate(sources))
    prompt = (
        "Trasforma questa notizia in un carosello Instagram per NUOVO QUOTIDIANO, in italiano.\n"
        f"Totale slide: copertina + {config.SLIDES_MIN - 2}-{config.SLIDES_MAX - 2} interne + 'perché ti riguarda'.\n"
        "Ogni slide deve dire una cosa sola e far venire voglia di passare alla successiva.\n"
        + (extra + "\n\n" if extra else "") +
        "Usa solo i fatti di queste fonti:\n\n" + docs
    )
    return _call(WRITE_TOOL, prompt, 4000)


READ_POST_TOOL = {
    "name": "leggi_post",
    "description": "Cosa racconta il post Instagram.",
    "input_schema": {
        "type": "object",
        "properties": {
            "notizia": {"type": "string", "description": "Tutti i fatti del post (testo delle slide + caption) riscritti in italiano in modo completo: chi, cosa, quando, numeri, dichiarazioni"},
            "scaletta": {"type": "array", "items": {"type": "string"}, "description": "Di cosa parla ogni slide del post, in ordine, una riga per slide"},
            "ricerca": {"type": "string", "description": "Titolo breve della notizia in inglese, per cercarla nelle testate"},
        },
        "required": ["notizia", "scaletta", "ricerca"],
    },
}

MATCH_TOOL = {
    "name": "trova_articoli",
    "description": "Articoli delle testate che parlano della stessa notizia.",
    "input_schema": {
        "type": "object",
        "properties": {"numeri": {"type": "array", "items": {"type": "integer"}, "description": "Fino a 4 numeri, vuoto se nessuno"}},
        "required": ["numeri"],
    },
}


def _img_block(im) -> dict:
    import base64
    import io as _io
    th = im.copy()
    th.thumbnail((1080, 1080))
    buf = _io.BytesIO()
    th.convert("RGB").save(buf, "JPEG", quality=88)
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.b64encode(buf.getvalue()).decode()}}


def read_post(images: list, caption: str, username: str) -> dict:
    """Claude legge le slide (immagini) e la caption di un post Instagram."""
    content = [{"type": "text", "text": f"Post Instagram di @{username or 'sconosciuto'}. Caption:\n{caption[:2500]}\n\nSlide:"}]
    for i, im in enumerate(images[:10]):
        content += [{"type": "text", "text": f"Slide {i + 1}:"}, _img_block(im)]
    content.append({"type": "text", "text": f"Rispondi SOLO chiamando lo strumento `{READ_POST_TOOL['name']}`."})
    msg = _client().messages.create(model=config.CLAUDE_MODEL, max_tokens=2500, system=LINEA_EDITORIALE,
                                    tools=[READ_POST_TOOL], tool_choice={"type": "auto"},
                                    messages=[{"role": "user", "content": content}])
    res = next((b.input for b in msg.content if b.type == "tool_use"), None) or \
        _json_from_text("".join(getattr(b, "text", "") for b in msg.content))
    if not res:
        raise RuntimeError("non sono riuscito a leggere il post")
    return res


def match_articles(story: str, items: list) -> list:
    """Tra le notizie delle testate, quelle che parlano della stessa storia."""
    if not items:
        return []
    lines = [f"[{n}] ({it.source}) {it.title} — {it.summary[:160]}" for n, it in enumerate(items[:150])]
    res = _call(MATCH_TOOL, f"NOTIZIA: {story}\n\nArticoli delle testate:\n" + "\n".join(lines) +
                "\n\nQuali articoli parlano proprio di questa notizia (stesso fatto, non solo stesso tema)?",
                600, model=config.PICK_MODEL)
    return [items[i] for i in res.get("numeri", []) if isinstance(i, int) and 0 <= i < len(items)][:4]


PHOTO_TOOL = {
    "name": "scegli_foto",
    "description": "Scegli la foto adatta alla slide oppure nessuna.",
    "input_schema": {
        "type": "object",
        "properties": {
            "scelta": {"type": ["integer", "null"], "description": "Numero della foto adatta (da 0), null se nessuna va bene"},
            "motivo": {"type": "string", "description": "Una frase"},
        },
        "required": ["scelta", "motivo"],
    },
}


def choose_photo(slide: dict, images: list) -> tuple[int | None, str]:
    """Claude guarda le foto candidate e sceglie quella coerente con la slide (o nessuna)."""
    import base64
    import io as _io
    content = [{"type": "text", "text": (
        "Sei il photo editor di NUOVO QUOTIDIANO. Questa è una slide di un carosello di notizie:\n"
        f"TITOLO: {slide.get('titolo', '')}\nTESTO: {slide.get('testo', '')}\n"
        f"(ricerca usata: {slide.get('foto_ricerca', '')})\n\n"
        "Qui sotto ci sono le foto candidate, numerate da 0. Scegline UNA solo se mostra davvero il soggetto "
        "della slide (la persona giusta, il luogo o l'istituzione giusta, l'oggetto di cui si parla) ed è una foto "
        "giornalistica credibile: niente foto generiche da stock, illustrazioni, grafici, loghi isolati, screenshot, "
        "testo in sovrimpressione, persone sbagliate o immagini che potrebbero fuorviare il lettore. "
        "Sarà convertita in bianco e nero, quindi conta la composizione, non il colore. "
        "Se nessuna è davvero adatta, scegli null: meglio una slide senza foto che una foto fuori tema.")}]
    for i, im in enumerate(images):
        th = im.copy()
        th.thumbnail((768, 768))
        buf = _io.BytesIO()
        th.convert("RGB").save(buf, "JPEG", quality=85)
        content += [{"type": "text", "text": f"Foto {i}:"},
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                                 "data": base64.b64encode(buf.getvalue()).decode()}}]
    content.append({"type": "text", "text": f"Rispondi SOLO chiamando lo strumento `{PHOTO_TOOL['name']}`."})
    try:
        msg = _client().messages.create(model=config.CLAUDE_MODEL, max_tokens=400, tools=[PHOTO_TOOL],
                                        tool_choice={"type": "auto"}, messages=[{"role": "user", "content": content}])
        res = next((b.input for b in msg.content if b.type == "tool_use"), None) or \
            _json_from_text("".join(getattr(b, "text", "") for b in msg.content)) or {}
    except Exception as e:
        return None, f"verifica non riuscita: {e}"
    n = res.get("scelta")
    if isinstance(n, int) and 0 <= n < len(images):
        return n, res.get("motivo", "")
    return None, res.get("motivo", "nessuna adatta")


def build_caption(c: dict, sources: list[dict], credits: list[tuple[str, str]]) -> str:
    """Caption finale: testo di Claude + fonti + crediti foto + CTA + 5 hashtag (max 2200 caratteri)."""
    fonti = ", ".join(dict.fromkeys(s["source"] for s in sources))
    cred = "; ".join(f"{where} {who}" for where, who in credits if who)
    tags = []
    for h in c.get("hashtag", []):
        h = h.lstrip("#").replace(" ", "").lower()
        if h and h != config.HANDLE and h not in tags:
            tags.append(h)
    tags = tags[:4] + [config.HANDLE]
    parts = [c["caption"].strip(),
             f"Fonti: {fonti}." + (f"\nFoto: {cred}." if cred else ""),
             f"Segui @{config.HANDLE} per scoprire il mondo in un minuto.",
             " ".join("#" + t for t in tags)]
    return "\n\n".join(p for p in parts if p)[:2200]
