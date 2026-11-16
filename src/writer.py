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
        "numero": {"type": "string", "description": "Solo per layout dato: il numero, es. '4,25%' o '12 mld €'"},
        "autore": {"type": "string", "description": "Solo per layout citazione: chi l'ha detto e ruolo"},
        "foto_ricerca": {"type": "string", "description": "Solo per layout foto: 2-5 parole IN INGLESE per cercare una foto libera (es. 'Christine Lagarde', 'European Central Bank Frankfurt', 'oil tanker sea')"},
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
            "categoria": {"type": "string", "enum": ["GEOPOLITICA", "GUERRA", "ECONOMIA", "MERCATI", "AZIENDE",
                                                      "POLITICA", "EUROPA", "ENERGIA", "TECNOLOGIA", "ITALIA", "MONDO"]},
            "titolo_copertina": {"type": "string",
                                 "description": "Titolo-notizia della copertina, 8-16 parole, chiaro e forte, senza punto finale"},
            "parole_evidenziate": {"type": "array", "items": {"type": "string"},
                                   "description": "1-3 parole del titolo di copertina da colorare in verde (le più forti)"},
            "slide": {"type": "array", "items": SLIDE, "minItems": config.SLIDES_MIN - 2, "maxItems": config.SLIDES_MAX - 2,
                      "description": "Slide interne in ordine: cosa è successo, contesto, numeri, reazioni, cosa succede ora. Alterna i layout, almeno 2 con foto."},
            "perche_ti_riguarda": {"type": "string",
                                   "description": "Ultima slide: max 40 parole su cosa cambia per chi vive in Italia. Se non c'è un effetto concreto, spiega perché conta comunque."},
            "caption": {"type": "string",
                        "description": "Caption Instagram: 1 riga d'apertura forte, poi 3-5 righe di riassunto, poi una domanda per i commenti. Niente hashtag qui."},
            "hashtag": {"type": "array", "items": {"type": "string"}, "description": "5-8 hashtag senza #"},
        },
        "required": ["categoria", "titolo_copertina", "parole_evidenziate", "slide", "perche_ti_riguarda", "caption", "hashtag"],
    },
}


def _client():
    import anthropic
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def _call(tool: dict, prompt: str, max_tokens: int = 4000) -> dict:
    msg = _client().messages.create(
        model=config.CLAUDE_MODEL, max_tokens=max_tokens, system=LINEA_EDITORIALE,
        tools=[tool], tool_choice={"type": "tool", "name": tool["name"]},
        messages=[{"role": "user", "content": prompt}])
    for block in msg.content:
        if block.type == "tool_use":
            return block.input
    raise RuntimeError("Claude non ha restituito il formato atteso")


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
        "un carosello. Evita cronaca nera, gossip, sport e notizie locali straniere senza rilievo internazionale."
    )
    res = _call(PICK_TOOL, prompt, 800)
    n = res.get("scelta")
    if n is None or not (0 <= n < len(items)):
        return None
    related = [items[i] for i in res.get("stessa_storia", []) if 0 <= i < len(items) and i != n][:4]
    return {"main": items[n], "related": related, "topic": res.get("argomento", items[n].title),
            "reason": res.get("motivo", "")}


def write(sources: list[dict]) -> dict:
    """sources = [{'source','title','link','text'}]. Ritorna il carosello (dict di WRITE_TOOL)."""
    docs = "\n\n".join(
        f"=== FONTE {i + 1}: {s['source']} — {s['title']}\n{s['text'][:7000]}" for i, s in enumerate(sources))
    prompt = (
        "Trasforma questa notizia in un carosello Instagram per NUOVO QUOTIDIANO, in italiano.\n"
        f"Totale slide: copertina + {config.SLIDES_MIN - 2}-{config.SLIDES_MAX - 2} interne + 'perché ti riguarda'.\n"
        "Ogni slide deve dire una cosa sola e far venire voglia di passare alla successiva.\n"
        "Usa solo i fatti di queste fonti:\n\n" + docs
    )
    return _call(WRITE_TOOL, prompt, 4000)


def build_caption(c: dict, sources: list[dict], credits: list[tuple[str, str]]) -> str:
    """Caption finale: testo di Claude + fonti + crediti foto + hashtag (max 2200 caratteri)."""
    fonti = ", ".join(dict.fromkeys(s["source"] for s in sources))
    cred = "\n".join(f"📷 {where}: {who}" for where, who in credits if who)
    tags = " ".join("#" + h.lstrip("#").replace(" ", "") for h in c.get("hashtag", [])[:8])
    parts = [c["caption"].strip(), f"Fonti: {fonti}", cred,
             f"Segui @{config.HANDLE} per capire il mondo in 1 minuto.", tags]
    text = "\n\n".join(p for p in parts if p)
    return text[:2200]
