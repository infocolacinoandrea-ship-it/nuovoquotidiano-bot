"""Impostazioni di NUOVO QUOTIDIANO bot.

I valori segreti arrivano dalle variabili d'ambiente (GitHub Secrets oppure il file .env sul mini PC).
Tutto il resto si regola qui o con variabili d'ambiente dello stesso nome.
"""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _env_file():
    """Sul mini PC legge il file .env nella cartella del bot (su GitHub non c'è e si usano i Secrets)."""
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_env_file()

# --- Marchio ---
BRAND_NAME = "NUOVO QUOTIDIANO"
HANDLE = os.getenv("IG_HANDLE", "nuovoquotidiano")
COLORS = {
    "bg": (0, 0, 0),            # nero
    "text": (255, 255, 255),    # bianco
    "accent": (182, 242, 58),   # verde lime #B6F23A
    "muted": (160, 160, 160),   # grigio per fonti e note
}

# --- Bot Telegram ---
BOT_TOKEN = os.getenv("TG_BOT_TOKEN", "")
ADMIN_CHAT_ID = os.getenv("TG_ADMIN_CHAT_ID", "")

# --- Instagram (stessa app Meta di Dr.Scount o una nuova) ---
IG_USER_ID = os.getenv("IG_USER_ID", "")
IG_TOKEN = os.getenv("IG_ACCESS_TOKEN", "")
IG_API = os.getenv("IG_API") or (
    "https://graph.facebook.com/v25.0" if IG_TOKEN.startswith("EAA") else "https://graph.instagram.com/v21.0")
IG_TOKEN_EXPIRES = not IG_TOKEN.startswith("EAA")

# --- Claude (scrittura dei caroselli) ---
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-5-5")      # scrive il carosello
PICK_MODEL = os.getenv("PICK_MODEL", "claude-haiku-5-5")           # sceglie la notizia (più economico)

# --- Foto libere (facoltativo: Pexels dà foto belle e coerenti, chiave gratuita su pexels.com/api) ---
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY", "")
MIN_PHOTO_SIDE = int(os.getenv("MIN_PHOTO_SIDE", "900"))  # sotto questa misura la foto è sgranata: scartata

# --- Dove vengono pubblicate le immagini (repo GitHub pubblico, ramo "media") ---
REPO = os.getenv("GITHUB_REPOSITORY", os.getenv("NQ_REPO", ""))
BRANCH = os.getenv("GITHUB_REF_NAME", "main")
MEDIA_BRANCH = "media"

# --- Ritmo di pubblicazione (ora italiana) ---
# A ogni orario il bot sceglie la notizia più importante e prepara un carosello.
SLOTS = [s.strip() for s in os.getenv("SLOTS", "07:30,12:30,18:00,21:00").split(",") if s.strip()]
MAX_PER_DAY = int(os.getenv("MAX_PER_DAY", "6"))
LOOKBACK_HOURS = int(os.getenv("LOOKBACK_HOURS", "10"))     # notizie più vecchie di così vengono ignorate
SLIDES_MIN, SLIDES_MAX = 5, 8

# Pubblicazione automatica senza approvazione (1 = sì). Di base ti arriva l'anteprima con ✅/❌.
AUTO_PUBLISH = os.getenv("AUTO_PUBLISH", "0") == "1"
# Un'anteprima non approvata entro queste ore scade (la notizia invecchia)
PENDING_HOURS = int(os.getenv("PENDING_HOURS", "8"))
# Storia automatica con la copertina dopo ogni carosello
AUTO_STORY = os.getenv("AUTO_STORY", "1") == "1"

# Modalità ascolto: ogni giro resta acceso e reagisce subito ai pulsanti.
# Su GitHub ~25 minuti per giro; sul mini PC 0 = per sempre.
LISTEN_MINUTES = int(os.getenv("LISTEN_MINUTES", "0"))
