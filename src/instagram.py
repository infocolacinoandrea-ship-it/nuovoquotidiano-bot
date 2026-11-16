"""Pubblicazione su Instagram con l'API ufficiale: caroselli e storie."""
from __future__ import annotations

import time

import requests

import config


def _check(r: requests.Response) -> dict:
    data = r.json()
    if r.status_code >= 400 or "error" in data:
        raise RuntimeError(f"Instagram: {data}")
    return data


def _tok() -> dict:
    return {"access_token": config.IG_TOKEN}


def _wait(container: str, tries: int = 40):
    for _ in range(tries):
        st = _check(requests.get(f"{config.IG_API}/{container}",
                                 params={"fields": "status_code", **_tok()}, timeout=30))
        if st.get("status_code") == "FINISHED":
            return
        if st.get("status_code") in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram non è riuscito a elaborare il contenuto: {st}")
        time.sleep(3)
    raise RuntimeError("Instagram ci mette troppo a elaborare il contenuto")


def _publish(container: str) -> str:
    return _check(requests.post(f"{config.IG_API}/{config.IG_USER_ID}/media_publish",
                                data={"creation_id": container, **_tok()}, timeout=60))["id"]


def publish_carousel(image_urls: list[str], caption: str) -> str:
    """Carosello da 2 a 10 immagini. Ritorna l'id del post."""
    base = f"{config.IG_API}/{config.IG_USER_ID}/media"
    children = []
    for url in image_urls[:10]:
        c = _check(requests.post(base, data={"image_url": url, "is_carousel_item": "true", **_tok()}, timeout=60))["id"]
        children.append(c)
    for c in children:
        _wait(c)
    parent = _check(requests.post(base, data={"media_type": "CAROUSEL", "children": ",".join(children),
                                              "caption": caption, **_tok()}, timeout=60))["id"]
    _wait(parent)
    return _publish(parent)


def publish_story(image_url: str) -> str:
    c = _check(requests.post(f"{config.IG_API}/{config.IG_USER_ID}/media",
                             data={"image_url": image_url, "media_type": "STORIES", **_tok()}, timeout=60))["id"]
    _wait(c)
    return _publish(c)


def permalink(media_id: str) -> str:
    try:
        return _check(requests.get(f"{config.IG_API}/{media_id}",
                                   params={"fields": "permalink", **_tok()}, timeout=30)).get("permalink", "")
    except Exception:
        return ""


def refresh_token() -> dict:
    return _check(requests.get("https://graph.instagram.com/refresh_access_token", params={
        "grant_type": "ig_refresh_token", **_tok()}, timeout=30))


def publishing_room() -> int:
    """Quanti post si possono ancora pubblicare nelle 24 ore (limite di Instagram: 50, il carosello conta 1)."""
    try:
        d = _check(requests.get(f"{config.IG_API}/{config.IG_USER_ID}/content_publishing_limit", params={
            "fields": "quota_usage,config", **_tok()}, timeout=30))["data"][0]
        return int(d["config"]["quota_total"]) - int(d["quota_usage"])
    except Exception:
        return 99
