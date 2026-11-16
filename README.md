# NUOVO QUOTIDIANO bot: dalle testate del mondo al carosello Instagram

Il bot lavora da solo, agli orari stabiliti (di base **07:30, 12:30, 18:00 e 21:00**):

1. legge le notizie delle ultime ore da BBC, Guardian, NYT, FT, Bloomberg, Al Jazeera, CNBC, DW, France 24, Politico Europe, Euronews, ANSA e Il Sole 24 Ore (elenco in `sources.json`);
2. **Claude** sceglie la notizia più importante non ancora trattata e la confronta con le altre testate che ne parlano;
3. Claude scrive il carosello: copertina, 3-6 slide (fatto, numero chiave, citazione, contesto, cosa succede ora), la slide "Perché ti riguarda" e la caption con fonti e crediti delle foto;
4. crea le immagini 1080×1350 con la grafica della pagina, più una storia 1080×1920;
5. ti manda l'**anteprima su Telegram** con tre pulsanti: ✅ Pubblica · ❌ Scarta · 🔄 Un'altra notizia.

Comandi da scrivere al bot: `/nuovo` (un carosello subito), `/stato`, `/pausa`, `/riprendi`.

Per pubblicare senza approvazione imposta `AUTO_PUBLISH: "1"` nel workflow (o nel `.env` sul mini PC).

## Linea grafica

- **Colori:** nero `#000000`, bianco e un solo accento verde lime `#B6F23A`.
- **Font:** Inter Tight Black per i titoli in maiuscolo, Inter per i testi. Sono in `assets/fonts`, con licenza OFL.
- **Marchio:** il quadrato lime con "NQ" in alto a sinistra in ogni slide (`assets/logo.png`). Come foto profilo usa `assets/foto-profilo.png`.
- **Foto:** tutte passano dallo stesso trattamento: bianco e nero contrastato, neri profondi, grana leggera e sfumatura nera. Così la foto d'agenzia in copertina e le foto libere interne sembrano della stessa serie. Le foto troppo piccole vengono scartate e la slide diventa solo grafica.
- **Copertina:** la foto dell'articolo, con l'etichetta della categoria in lime, il titolo in maiuscolo con 1-3 parole in lime e il credito della foto.
- **Slide interne:** quattro impaginazioni che si alternano: *foto*, *testo*, *dato* (un numero gigante in lime) e *citazione*. Hanno il numero di pagina e la barra di avanzamento.
- **Chiusura:** "Perché ti riguarda" e il pulsante lime "SEGUI @NUOVOQUOTIDIANO".

La grafica si cambia in `src/render.py`, la linea editoriale (tono e regole di accuratezza) in `src/writer.py`.

## Foto e diritti

- **Copertina:** foto dell'articolo. Il credito (agenzia o fotografo, se la pagina lo dichiara, più la testata) va **sempre** nella caption e in piccolo sull'immagine. Le foto d'agenzia restano coperte da copyright: citare la fonte non equivale a una licenza. Se arriva una segnalazione, togli il post e valuta di usare solo foto libere anche in copertina.
- **Slide interne:** Wikimedia Commons (persone, luoghi, istituzioni) e Pexels (immagini generiche). Sono foto con licenza libera, con il credito in caption.

---

## Configurazione (circa 30 minuti, una volta sola)

### 1. Bot Telegram
1. Su **@BotFather** scrivi `/newbot`, chiamalo per esempio *NuovoQuotidiano Redazione* e copia il **token**.
2. Apri il bot e premi **Avvia**.
3. Il tuo Id Telegram (`TG_ADMIN_CHAT_ID`) è lo stesso che usi per Dr.Scount.

### 2. Instagram
1. Imposta @nuovoquotidiano come account professionale (Creator o Azienda).
2. Su **developers.facebook.com** apri l'app di Dr.Scount, o creane una nuova con il caso d'uso "Gestisci messaggi e contenuti su Instagram". Alla voce *Genera token d'accesso* aggiungi **@nuovoquotidiano**.
3. Copia `IG_ACCESS_TOKEN` e `IG_USER_ID`. Servono i permessi `instagram_business_basic` e `instagram_business_content_publish`.

### 3. Chiave Claude
1. Su **console.anthropic.com** crea una chiave API (`ANTHROPIC_API_KEY`) e carica un po' di credito. Un carosello costa pochi centesimi.

### 4. Pexels (facoltativo, consigliato)
1. Su **pexels.com/api** crea la chiave gratuita (`PEXELS_API_KEY`). Senza chiave il bot usa solo Wikimedia Commons.

### 5. Repository GitHub
1. Crea un repository **pubblico** `nuovoquotidiano-bot`. Deve essere pubblico perché Instagram scarica le immagini dal ramo `media`. I segreti restano privati.
2. *Settings → Secrets and variables → Actions*: aggiungi `TG_BOT_TOKEN`, `TG_ADMIN_CHAT_ID`, `IG_USER_ID`, `IG_ACCESS_TOKEN`, `ANTHROPIC_API_KEY` e, se ce l'hai, `PEXELS_API_KEY`.
3. *Actions* → **NUOVO QUOTIDIANO bot** → **Run workflow**. Poi scrivi `/stato` al bot e, per la prima prova, `/nuovo`.

## Passaggio al mini PC

1. Sul mini PC lancia prima `server/setup.sh` di drscount-bot, se non l'hai già fatto: installa Docker, Tailscale e il firewall.
2. Lancia `bash server/install.sh` di questo repo: scarica il bot, ti fa compilare `.env` (stessi valori dei Secrets, più `GH_TOKEN`) e lo accende con Docker. Si riavvia da solo.
   `GH_TOKEN` è un token GitHub *fine-grained* con permesso **Contents: read and write** su questo repo.
3. Su GitHub → Actions → **NUOVO QUOTIDIANO bot** → **Disable workflow**, altrimenti girano due bot.
4. Per vedere i log: `docker logs -f nuovoquotidiano-bot`. Per aggiornare il bot: `git pull && docker compose up -d --build`.

## Prove in locale

```bash
pip install -r requirements.txt
python src/main.py --demo    # solo grafica, testi di esempio, niente internet
python src/main.py --prova   # un carosello vero (serve ANTHROPIC_API_KEY), salvato in posts/ senza inviare nulla
```

## Regolazioni (`src/config.py` o variabili d'ambiente)

| Impostazione | Default | Cosa fa |
|---|---|---|
| `SLOTS` | 07:30,12:30,18:00,21:00 | orari dei caroselli (ora italiana) |
| `MAX_PER_DAY` | 6 | caroselli massimi al giorno (contano anche quelli fatti con `/nuovo`) |
| `LOOKBACK_HOURS` | 10 | ignora le notizie più vecchie |
| `AUTO_PUBLISH` | 0 | 1 = pubblica senza chiedere |
| `PENDING_HOURS` | 8 | dopo quante ore scade un'anteprima non approvata |
| `AUTO_STORY` | 1 | storia con la copertina dopo ogni carosello |
| `MIN_PHOTO_SIDE` | 900 | sotto questa misura in pixel la foto viene scartata |
| `CLAUDE_MODEL` | claude-sonnet-5-5 | modello che scrive i caroselli |
