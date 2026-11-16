#!/usr/bin/env bash
# Sposta NUOVO QUOTIDIANO sul mini PC (dopo aver lanciato setup.sh di drscount-bot, che installa Docker).
#   bash install.sh
set -euo pipefail
DIR="$HOME/nuovoquotidiano-bot"
if [ ! -d "$DIR/.git" ]; then
  git clone https://github.com/infocolacinoandrea-ship-it/nuovoquotidiano-bot.git "$DIR"
fi
cd "$DIR"
git pull -q
if [ ! -f .env ]; then
  cp .env.example .env
  echo "Apro il file .env: incolla i token (gli stessi dei Secrets di GitHub + GH_TOKEN), salva e chiudi."
  sleep 2
  nano .env
fi
# lo stato (notizie già trattate) arriva dal repository, così il bot riparte da dove era
docker compose up -d --build
echo
echo "Fatto. Il bot è acceso. Log:  docker logs -f nuovoquotidiano-bot"
echo "IMPORTANTE: su GitHub → Actions → 'NUOVO QUOTIDIANO bot' → Disable workflow (altrimenti girano due bot)."
