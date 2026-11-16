"""Foto libere per le slide interne: Wikimedia Commons (persone, luoghi, istituzioni) e Pexels (concetti).

Ogni foto torna con il suo credito, che finisce nella caption.
Le foto troppo piccole (sgranate) vengono scartate: meglio una slide solo grafica che una foto brutta.
"""
from __future__ import annotations

import io

import requests
from PIL import Image

import config

WIKI_UA = "NuovoQuotidianoBot/1.0 (Instagram @nuovoquotidiano; bot di notizie)"


def _ok(img: Image.Image) -> bool:
    return min(img.size) >= config.MIN_PHOTO_SIDE


def _get(url: str, headers=None) -> Image.Image | None:
    try:
        r = requests.get(url, headers=headers or {"User-Agent": WIKI_UA}, timeout=30)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        img.load()
        return img.convert("RGB")
    except Exception as e:
        print(f"foto non scaricata {url}: {e}")
        return None


def wikimedia(query: str, used: set[str]) -> tuple[Image.Image, str] | None:
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": WIKI_UA}, timeout=20, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": 12,
            "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1600})
        pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    except Exception as e:
        print(f"Wikimedia non risponde: {e}")
        return None
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        url = ii.get("thumburl") or ii.get("url")
        if not url or url in used or min(ii.get("width", 0), ii.get("height", 0)) < config.MIN_PHOTO_SIDE:
            continue
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not lic or "fair use" in lic.lower() or "non-free" in lic.lower():
            continue
        from bs4 import BeautifulSoup
        artist = BeautifulSoup(meta.get("Artist", {}).get("value", ""), "html.parser").get_text(" ", strip=True)
        img = _get(url)
        if img and _ok(img):
            used.add(url)
            credit = f"{artist[:50] or 'Autore sconosciuto'} / Wikimedia Commons, {lic}"
            return img, credit
    return None


def pexels(query: str, used: set[str]) -> tuple[Image.Image, str] | None:
    if not config.PEXELS_API_KEY:
        return None
    try:
        r = requests.get("https://api.pexels.com/v1/search", timeout=20,
                         headers={"Authorization": config.PEXELS_API_KEY},
                         params={"query": query, "per_page": 10, "orientation": "portrait"})
        photos = r.json().get("photos", [])
    except Exception as e:
        print(f"Pexels non risponde: {e}")
        return None
    for ph in photos:
        url = ph["src"].get("large2x") or ph["src"]["original"]
        if url in used:
            continue
        img = _get(url, headers={"User-Agent": WIKI_UA})
        if img and _ok(img):
            used.add(url)
            return img, f"{ph.get('photographer', 'Pexels')} / Pexels"
    return None


def find(query: str, kind: str, used: set[str]) -> tuple[Image.Image, str] | None:
    """kind = 'soggetto' (persona, luogo, edificio, istituzione) oppure 'concetto' (petrolio, borsa, navi...)."""
    if not query:
        return None
    order = (wikimedia, pexels) if kind == "soggetto" else (pexels, wikimedia)
    for fn in order:
        res = fn(query, used)
        if res:
            return res
    return None
