#!/usr/bin/env bash
# Avvio del bot nel contenitore del mini PC.
set -e
cd /app
git config --global --add safe.directory /app
git config user.name "nuovoquotidiano-bot"
git config user.email "nuovoquotidiano-bot@users.noreply.github.com"
# git deve poter caricare le immagini sul ramo "media" del repository pubblico
if [ -n "$GH_TOKEN" ] && [ -n "$NQ_REPO" ]; then
  git remote set-url origin "https://x-access-token:${GH_TOKEN}@github.com/${NQ_REPO}.git"
fi
exec python src/main.py
