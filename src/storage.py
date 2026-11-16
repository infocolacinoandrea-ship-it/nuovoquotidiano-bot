"""Dove vivono le immagini e lo stato.

Instagram vuole un indirizzo pubblico da cui scaricare le immagini. Le carichiamo sul ramo `media` del
repository GitHub (pubblico). Il ramo viene riscritto ogni volta e contiene SOLO i caroselli in attesa
o appena pubblicati, così il repository non si gonfia.

Funziona uguale su GitHub Actions e sul mini PC (basta che git possa fare push).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import config

STATE = config.ROOT / "state.json"


def git(*a, inp: str | None = None, check: bool = True) -> str:
    return subprocess.run(["git", *a], cwd=config.ROOT, check=check, capture_output=True,
                          text=True, input=inp).stdout.strip()


def media_url(name: str) -> str:
    return f"https://raw.githubusercontent.com/{config.REPO}/{config.MEDIA_BRANCH}/{name}"


def push_media(files: list[Path], keep_ids: set[str]) -> None:
    """Carica `files` sul ramo media, tenendo anche i file già presenti dei caroselli in `keep_ids`.
    I nomi dei file iniziano sempre con l'id del carosello (es. 20261116-1230_01.jpg)."""
    entries = {}
    ref = f"refs/remotes/origin/{config.MEDIA_BRANCH}"
    fetched = subprocess.run(["git", "fetch", "-q", "--depth=1", "origin", f"+{config.MEDIA_BRANCH}:{ref}"],
                             cwd=config.ROOT, capture_output=True).returncode == 0
    if fetched:  # al primo giro il ramo non esiste ancora
        for line in git("ls-tree", ref).splitlines():
            meta, name = line.split("\t", 1)
            if name.split("_")[0] in keep_ids:
                entries[name] = meta
    for f in files:
        entries[f.name] = f"100644 blob {git('hash-object', '-w', str(f))}"
    tree = git("mktree", inp="".join(f"{meta}\t{name}\n" for name, meta in sorted(entries.items())))
    commit = git("commit-tree", tree, "-m", "media: caroselli")
    git("push", "-q", "-f", "origin", f"{commit}:refs/heads/{config.MEDIA_BRANCH}")


def load_state() -> dict:
    base = {"seen": [], "topics": [], "pending": {}, "published": {}, "tg_offset": 0,
            "daily": {}, "slots_done": {}, "last_refresh": "", "paused": False}
    if STATE.exists():
        base.update(json.loads(STATE.read_text()))
    return base


def save_state(s: dict, push: bool = True):
    s["seen"] = s["seen"][-3000:]
    s["topics"] = s["topics"][-80:]
    s["daily"] = dict(sorted(s["daily"].items())[-14:])
    s["slots_done"] = dict(sorted(s["slots_done"].items())[-3:])
    s["published"] = dict(sorted(s["published"].items())[-200:])
    STATE.write_text(json.dumps(s, indent=1, ensure_ascii=False))
    if push and os.getenv("GITHUB_ACTIONS"):
        # su GitHub lo stato va salvato nel repository, altrimenti il giro dopo lo perde
        try:
            git("add", "state.json")
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=config.ROOT).returncode == 0:
                return
            git("commit", "-q", "-m", "bot: stato")
            git("pull", "-q", "--rebase", "-X", "theirs", check=False)
            git("push", "-q")
        except Exception as e:
            print(f"stato non salvato su GitHub: {e}", file=sys.stderr)
