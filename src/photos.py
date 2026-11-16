"""Foto per le slide interne, solo con licenza libera, e controllo di pertinenza.

Fonti (tutte con credito in caption):
- Openverse (milioni di foto Creative Commons, nessuna chiave richiesta)
- Wikimedia Commons (persone, luoghi, istituzioni)
- Pexels (facoltativo, con PEXELS_API_KEY: ottimo per immagini generiche)

Regola della pagina: una foto si usa SOLO se c'entra davvero con il testo della slide.
Per ogni slide si raccolgono alcune candidate e Claude, guardandole, sceglie quella giusta
oppure nessuna: in quel caso la slide resta solo testo. Le foto troppo piccole sono scartate.
"""
from __future__ import annotations

import io

import requests
from bs4 import BeautifulSoup
from PIL import Image

import config

UA = "NuovoQuotidianoBot/1.0 (Instagram @nuovoquotidiano; bot di notizie)"


def _big_enough(w, h) -> bool:
    return min(w or 0, h or 0) >= config.MIN_PHOTO_SIDE


def _get(url: str) -> Image.Image | None:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        r.raise_for_status()
        img = Image.open(io.BytesIO(r.content))
        img.load()
        img = img.convert("RGB")
        return img if _big_enough(*img.size) else None
    except Exception as e:
        print(f"foto non scaricata {url}: {e}")
        return None


def _openverse(query: str) -> list[tuple[str, str]]:
    try:
        r = requests.get("https://api.openverse.org/v1/images/", headers={"User-Agent": UA}, timeout=20, params={
            "q": query, "license_type": "commercial,modification", "page_size": 12, "mature": "false"})
        out = []
        for it in r.json().get("results", []):
            if not _big_enough(it.get("width"), it.get("height")):
                continue
            lic = f"CC {it.get('license', '').upper()} {it.get('license_version', '')}".strip()
            if it.get("license") in ("cc0", "pdm"):
                lic = "pubblico dominio"
            out.append((it["url"], f"{(it.get('creator') or 'Autore sconosciuto')[:50]} / {it.get('source', 'Openverse')}, {lic}"))
        return out
    except Exception as e:
        print(f"Openverse non risponde: {e}")
        return []


def _wikimedia(query: str) -> list[tuple[str, str]]:
    try:
        r = requests.get("https://commons.wikimedia.org/w/api.php", headers={"User-Agent": UA}, timeout=20, params={
            "action": "query", "format": "json", "generator": "search", "gsrnamespace": 6,
            "gsrsearch": f"{query} filetype:bitmap", "gsrlimit": 12,
            "prop": "imageinfo", "iiprop": "url|size|extmetadata", "iiurlwidth": 1600})
        pages = sorted(r.json().get("query", {}).get("pages", {}).values(), key=lambda p: p.get("index", 99))
    except Exception as e:
        print(f"Wikimedia non risponde: {e}")
        return []
    out = []
    for p in pages:
        ii = (p.get("imageinfo") or [{}])[0]
        if not _big_enough(ii.get("width"), ii.get("height")):
            continue
        meta = ii.get("extmetadata", {})
        lic = meta.get("LicenseShortName", {}).get("value", "")
        if not lic or "fair use" in lic.lower() or "non-free" in lic.lower():
            continue
        artist = BeautifulSoup(meta.get("Artist", {}).get("value", ""), "html.parser").get_text(" ", strip=True)
        out.append((ii.get("thumburl") or ii.get("url"), f"{artist[:50] or 'Autore sconosciuto'} / Wikimedia Commons, {lic}"))
    return out


def _pexels(query: str) -> list[tuple[str, str]]:
    if not config.PEXELS_API_KEY:
        return []
    try:
        r = requests.get("https://api.pexels.com/v1/search", timeout=20,
                         headers={"Authorization": config.PEXELS_API_KEY},
                         params={"query": query, "per_page": 10})
        return [(ph["src"].get("large2x") or ph["src"]["original"], f"{ph.get('photographer', 'Pexels')} / Pexels")
                for ph in r.json().get("photos", []) if _big_enough(ph.get("width"), ph.get("height"))]
    except Exception as e:
        print(f"Pexels non risponde: {e}")
        return []


def candidates(query: str, kind: str, used: set[str], n: int = 5) -> list[tuple[Image.Image, str, str]]:
    """Fino a n foto candidate [(immagine, credito, url)], alternando le fonti."""
    if not query:
        return []
    sources = [_wikimedia, _openverse, _pexels] if kind == "soggetto" else [_pexels, _openverse, _wikimedia]
    lists = [fn(query) for fn in sources]
    merged, seen = [], set(used)
    for i in range(12):  # alterna: 1a di ogni fonte, poi 2a...
        for lst in lists:
            if i < len(lst) and lst[i][0] not in seen:
                seen.add(lst[i][0])
                merged.append(lst[i])
    out = []
    for url, credit in merged:
        img = _get(url)
        if img is not None:
            out.append((img, credit, url))
        if len(out) >= n:
            break
    return out


def best_for(slide: dict, used: set[str], log=print) -> tuple[Image.Image, str] | None:
    """La foto giusta per la slide, verificata da Claude guardandola. None se nessuna c'entra davvero."""
    import writer
    cands = candidates(slide.get("foto_ricerca", ""), slide.get("foto_tipo", "concetto"), used)
    if not cands:
        return None
    idx, why = writer.choose_photo(slide, [c[0] for c in cands])
    log(f"foto per '{slide.get('titolo', '')[:40]}': {'n. ' + str(idx) if idx is not None else 'nessuna'} — {why}")
    if idx is None:
        return None
    img, credit, url = cands[idx]
    used.add(url)
    return img, credit
