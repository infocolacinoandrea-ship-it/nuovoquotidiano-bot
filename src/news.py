"""Legge le notizie dalle testate (RSS) e scarica il testo e la foto degli articoli."""
from __future__ import annotations

import calendar
import datetime as dt
import hashlib
import json
import re
from dataclasses import dataclass, field

import feedparser
import requests
from bs4 import BeautifulSoup

import config

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


@dataclass
class Item:
    title: str
    summary: str
    link: str
    source: str
    weight: int
    published: str            # ISO, UTC
    image: str = ""           # immagine dal feed, se c'è
    uid: str = field(default="")

    def __post_init__(self):
        if not self.uid:
            self.uid = hashlib.sha1(self.link.split("?")[0].encode()).hexdigest()[:12]


def _clean(html: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(html or "", "html.parser").get_text(" ")).strip()


def _feed_image(e) -> str:
    for key in ("media_content", "media_thumbnail"):
        for m in e.get(key) or []:
            if m.get("url"):
                return m["url"]
    for l in e.get("links") or []:
        if l.get("type", "").startswith("image"):
            return l.get("href", "")
    return ""


def load_sources() -> list[dict]:
    data = json.loads((config.ROOT / "sources.json").read_text())
    return [f for f in data["fonti"] if f.get("attiva", True)]


def fetch_items(hours: int | None = None) -> list[Item]:
    """Tutte le notizie uscite nelle ultime `hours` ore, dalle fonti attive."""
    hours = hours or config.LOOKBACK_HOURS
    since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)
    out, seen = [], set()
    for src in load_sources():
        try:
            r = requests.get(src["rss"], headers={"User-Agent": UA}, timeout=20)
            feed = feedparser.parse(r.content)
        except Exception as e:
            print(f"Fonte non raggiungibile {src['nome']}: {e}")
            continue
        for e in feed.entries[:40]:
            t = e.get("published_parsed") or e.get("updated_parsed")
            if not t:
                continue
            when = dt.datetime.fromtimestamp(calendar.timegm(t), dt.timezone.utc)
            if when < since or not e.get("link") or not e.get("title"):
                continue
            it = Item(title=_clean(e.title), summary=_clean(e.get("summary", ""))[:500],
                      link=e.link, source=src["nome"], weight=int(src.get("peso", 1)),
                      published=when.isoformat(), image=_feed_image(e))
            if it.uid not in seen:
                seen.add(it.uid)
                out.append(it)
    out.sort(key=lambda i: i.published, reverse=True)
    return out


def fetch_article(url: str) -> dict:
    """Testo dell'articolo, foto principale e credito della foto (se la pagina lo dichiara)."""
    res = {"text": "", "image": "", "credit": ""}
    try:
        r = requests.get(url, headers={"User-Agent": UA, "Accept-Language": "en,it;q=0.8"}, timeout=25)
        html = r.text
    except Exception as e:
        print(f"Articolo non scaricabile {url}: {e}")
        return res
    soup = BeautifulSoup(html, "html.parser")
    for prop in ("og:image", "twitter:image", "og:image:url"):
        tag = soup.find("meta", attrs={"property": prop}) or soup.find("meta", attrs={"name": prop})
        if tag and tag.get("content"):
            res["image"] = tag["content"]
            break
    res["credit"] = _photo_credit(soup)
    try:
        import trafilatura
        res["text"] = (trafilatura.extract(html, include_comments=False, include_tables=False) or "")[:9000]
    except Exception:
        pass
    if not res["text"]:
        res["text"] = " ".join(p.get_text(" ", strip=True) for p in soup.find_all("p"))[:9000]
    return res


def _photo_credit(soup: BeautifulSoup) -> str:
    """Prova a leggere chi ha scattato la foto principale (agenzia/fotografo)."""
    # 1) dati strutturati schema.org
    for s in soup.find_all("script", attrs={"type": "application/ld+json"}):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        for d in data if isinstance(data, list) else [data]:
            img = d.get("image") if isinstance(d, dict) else None
            if isinstance(img, list):
                img = img[0] if img else None
            if isinstance(img, dict):
                for k in ("creditText", "copyrightHolder", "author", "creator"):
                    v = img.get(k)
                    if isinstance(v, dict):
                        v = v.get("name")
                    if isinstance(v, str) and v.strip():
                        return v.strip()[:80]
    # 2) didascalie con "Photo:", "Foto:", "Getty", "Reuters", "AP"...
    for el in soup.select("figcaption, [class*=credit], [class*=Credit], [class*=caption]")[:12]:
        txt = el.get_text(" ", strip=True)
        m = re.search(r"((?:Photo|Foto|Photograph|Image|Credit)[^:]{0,15}:\s*[^.|]{2,60}|"
                      r"(?:Getty Images|Reuters|AP Photo|AFP|EPA|Bloomberg|Ansa|LaPresse|Imagoeconomica)[^.|]{0,40})",
                      txt, re.I)
        if m:
            return m.group(0).strip()[:80]
    return ""


def download(url: str) -> bytes:
    r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    r.raise_for_status()
    return r.content
