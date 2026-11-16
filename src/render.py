"""Grafica NUOVO QUOTIDIANO: caroselli 1080x1350 e storia 1080x1920.

Linea visiva (uguale in ogni slide):
- nero assoluto, bianco, un solo colore d'accento: verde lime #B6F23A;
- Inter Tight (titoli, maiuscolo, nero 900) + Inter (testi);
- TUTTE le foto passano dallo stesso trattamento: bianco e nero contrastato, neri profondi, grana leggera,
  sfumatura nera verso il testo. Così la foto d'agenzia in copertina e le foto libere interne sembrano
  della stessa serie;
- marchio "NQ" in alto a sinistra, numero di pagina in alto a destra, barra di avanzamento in basso.
"""
from __future__ import annotations

import datetime as dt
import random
import re
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps

import config

W, H = 1080, 1350
M = 72  # margine laterale
FONTS = config.ROOT / "assets" / "fonts"
BG, FG, ACC, MUTED = (config.COLORS[k] for k in ("bg", "text", "accent", "muted"))
BODY = (215, 215, 215)


def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"{name}.ttf"), size)


# ---------------------------------------------------------------- foto

def house_style(img: Image.Image, size: tuple[int, int], focus_y: float = 0.4) -> Image.Image:
    """Il trattamento foto unico della pagina."""
    img = ImageOps.exif_transpose(img).convert("RGB")
    img = ImageOps.fit(img, size, Image.LANCZOS, centering=(0.5, focus_y))
    g = ImageOps.grayscale(img)
    g = ImageOps.autocontrast(g, cutoff=1)
    g = ImageEnhance.Contrast(g).enhance(1.18)
    g = g.point(lambda v: int(max(0, v - 18) * 255 / 237))            # neri più profondi
    g = g.filter(ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    # grana leggera, sempre uguale (seme fisso) per coerenza
    rnd = random.Random(7)
    noise = Image.frombytes("L", (size[0] // 2, size[1] // 2),
                            bytes(rnd.randint(108, 148) for _ in range((size[0] // 2) * (size[1] // 2))))
    noise = noise.resize(size, Image.BILINEAR)
    g = Image.blend(g, Image.merge("L", [noise]), 0.07)
    # leggerissima dominante fredda per non avere un grigio "piatto"
    return Image.merge("RGB", (g, g.point(lambda v: min(255, v + 2)), g.point(lambda v: min(255, v + 6))))


def gradient(size: tuple[int, int], start: float, end: float, top_alpha=0, bottom_alpha=255) -> Image.Image:
    """Maschera verticale: trasparente fino a `start` (frazione dell'altezza), nera piena da `end`."""
    w, h = size
    col = Image.new("L", (1, h))
    for y in range(h):
        t = (y / h - start) / max(1e-6, end - start)
        t = min(1, max(0, t))
        t = t * t * (3 - 2 * t)  # curva morbida
        col.putpixel((0, y), int(top_alpha + (bottom_alpha - top_alpha) * t))
    return col.resize(size)


def darken(img: Image.Image, mask: Image.Image) -> Image.Image:
    return Image.composite(Image.new("RGB", img.size, BG), img, mask)


# ---------------------------------------------------------------- testo

def _norm(w: str) -> str:
    w = unicodedata.normalize("NFKD", w).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9%€$]", "", w)


def wrap(text: str, f: ImageFont.FreeTypeFont, width: int) -> list[str]:
    lines, cur = [], ""
    for word in text.split():
        test = f"{cur} {word}".strip()
        if f.getlength(test) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def fit(text: str, name: str, width: int, max_lines: int, sizes: range) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for s in sizes:
        f = font(name, s)
        lines = wrap(text, f, width)
        if len(lines) <= max_lines and all(f.getlength(l) <= width for l in lines):
            return f, lines
    f = font(name, sizes[-1])
    return f, wrap(text, f, width)


def draw_lines(d: ImageDraw.ImageDraw, xy, lines, f, fill, leading=1.12, highlight: set[str] = frozenset()) -> int:
    """Scrive righe (con parole evidenziate in verde). Ritorna la y sotto l'ultima riga."""
    x, y = xy
    step = int(f.size * leading)
    space = f.getlength(" ")
    for line in lines:
        cx = x
        for word in line.split(" "):
            col = ACC if _norm(word) in highlight else fill
            d.text((cx, y), word, font=f, fill=col)
            cx += f.getlength(word) + space
        y += step
    return y


def spaced(d: ImageDraw.ImageDraw, xy, text: str, f, fill, tracking: float = 0.18) -> int:
    """Testo maiuscolo spaziato (etichette). Ritorna la x finale."""
    x, y = xy
    for ch in text.upper():
        d.text((x, y), ch, font=f, fill=fill)
        x += f.getlength(ch) + f.size * tracking
    return int(x)


# ---------------------------------------------------------------- marchio

def logo_mark(size: int, border: bool = True) -> Image.Image:
    """Il marchio della pagina: quadrato nero con 'NQ' verde lime (bordo lime sottile sulle slide nere)."""
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=int(size * 0.14), fill=BG,
                        outline=ACC if border else None, width=max(2, size // 28))
    f = font("InterTight-Black", int(size * 0.52))
    bb = d.textbbox((0, 0), "NQ", font=f)
    d.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]), "NQ", font=f, fill=ACC)
    return im


def logo_full(size: int = 1080) -> Image.Image:
    """Logo / foto profilo: sfondo nero pieno, NQ verde lime al centro."""
    im = Image.new("RGB", (size, size), BG)
    d = ImageDraw.Draw(im)
    f = font("InterTight-Black", int(size * 0.44))
    bb = d.textbbox((0, 0), "NQ", font=f)
    d.text(((size - (bb[2] - bb[0])) / 2 - bb[0], (size - (bb[3] - bb[1])) / 2 - bb[1]), "NQ", font=f, fill=ACC)
    return im


def header(img: Image.Image, page: int | None, total: int, date: bool = False):
    d = ImageDraw.Draw(img)
    mark = logo_mark(58)
    img.paste(mark, (M, 58), mark)
    f = font("InterTight-ExtraBold", 25)
    d.text((M + 76, 63), "NUOVO", font=f, fill=FG)
    d.text((M + 76, 89), "QUOTIDIANO", font=f, fill=FG)
    fr = font("Inter-Medium", 24)
    if date:
        mesi = "GEN FEB MAR APR MAG GIU LUG AGO SET OTT NOV DIC".split()
        now = dt.datetime.now(ZoneInfo("Europe/Rome"))
        txt = f"{now.day} {mesi[now.month - 1]} {now.year}"
    else:
        txt = f"{page:02d} / {total:02d}" if page else ""
    if txt:
        d.text((W - M - fr.getlength(txt), 76), txt, font=fr, fill=FG)


def progress(img: Image.Image, page: int, total: int):
    d = ImageDraw.Draw(img)
    gap, y, h = 8, H - 40, 5
    seg = (W - 2 * M - gap * (total - 1)) / total
    for i in range(total):
        x0 = M + i * (seg + gap)
        d.rounded_rectangle((x0, y, x0 + seg, y + h), radius=2, fill=ACC if i < page else (55, 55, 55))


def footer_handle(img: Image.Image):
    d = ImageDraw.Draw(img)
    f = font("Inter-Medium", 24)
    d.text((M, H - 92), f"@{config.HANDLE}", font=f, fill=MUTED)


def credit_tag(img: Image.Image, text: str, y: int):
    if not text:
        return
    d = ImageDraw.Draw(img)
    f = font("Inter-Regular", 18)
    t = f"Foto: {text}"[:90]
    d.text((W - M - f.getlength(t), y), t, font=f, fill=(150, 150, 150))


# ---------------------------------------------------------------- slide

def _hl(words: list[str]) -> set[str]:
    return {_norm(w) for p in words for w in p.split()} - {""}


def cover(photo: Image.Image | None, category: str, title: str, highlight: list[str], credit: str,
          total: int) -> Image.Image:
    if photo is not None:
        img = house_style(photo, (W, H), focus_y=0.35)
        img = darken(img, gradient((W, H), 0.30, 0.78))
        img = darken(img, gradient((W, H), 0.0, 0.16, top_alpha=150, bottom_alpha=0))  # leggibilità del marchio
    else:  # copertina solo grafica
        img = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(img)
        for i in range(0, W + H, 46):
            d.line((i, 0, i - H, H), fill=(18, 18, 18), width=2)
    header(img, None, total, date=True)
    d = ImageDraw.Draw(img)
    title = title.upper().rstrip(".")
    f, lines = fit(title, "InterTight-Black", W - 2 * M, 6, range(96, 58, -2))
    lh = int(f.size * 1.04)
    bottom = H - 150
    y = bottom - lh * len(lines)
    # etichetta categoria
    fc = font("InterTight-ExtraBold", 27)
    d.rectangle((M, y - 62, M + 34, y - 56), fill=ACC)
    spaced(d, (M + 50, y - 76), category, fc, ACC, 0.22)
    draw_lines(d, (M, y), lines, f, FG, leading=1.04, highlight=_hl(highlight))
    # piede: crediti + invito a scorrere
    credit_tag(img, credit, H - 112) if photo is not None else None
    fs = font("InterTight-ExtraBold", 26)
    spaced(d, (M, H - 92), "SCORRI  →", fs, ACC, 0.16)
    progress(img, 1, total)
    return img


def _text_block(d, y, s: dict, title_sizes=range(64, 44, -2), body_size=36, max_title_lines=3) -> int:
    fo = font("InterTight-ExtraBold", 26)
    spaced(d, (M, y), s.get("occhiello", ""), fo, ACC, 0.2)
    y += 54
    ft, lines = fit(s.get("titolo", ""), "InterTight-Black", W - 2 * M, max_title_lines, title_sizes)
    y = draw_lines(d, (M, y), lines, ft, FG, leading=1.08) + 22
    fb, blines = fit(s.get("testo", ""), "Inter-Regular", W - 2 * M, 9, range(body_size, 26, -2))
    return draw_lines(d, (M, y), blines, fb, BODY, leading=1.42)


def _centered(d_img: Image.Image, top: int, bottom: int, draw_fn) -> int:
    """Disegna un blocco centrato verticalmente tra top e bottom (lo misura prima su un foglio di prova)."""
    scratch = Image.new("RGB", (W, H * 2))
    end = draw_fn(ImageDraw.Draw(scratch), 0)
    y = top + max(0, (bottom - top - end) // 2)
    return draw_fn(ImageDraw.Draw(d_img), y)


def content(s: dict, page: int, total: int, photo: Image.Image | None = None, credit: str = "") -> Image.Image:
    layout = s.get("layout", "testo")
    if layout == "foto" and photo is None:
        layout = "testo"
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    if layout == "foto":
        ph_h = 720
        ph = house_style(photo, (W, ph_h), focus_y=0.4)
        ph = darken(ph, gradient((W, ph_h), 0.55, 1.0))
        ph = darken(ph, gradient((W, ph_h), 0.0, 0.25, top_alpha=150, bottom_alpha=0))
        img.paste(ph, (0, 0))
        credit_tag(img, credit, ph_h - 34)
        _centered(img, ph_h, H - 110, lambda dd, y: _text_block(dd, y, s, range(60, 42, -2), 37, 2))

    elif layout == "dato":
        def blk(dd, y):
            fo = font("InterTight-ExtraBold", 28)
            spaced(dd, (M, y), s.get("occhiello", ""), fo, ACC, 0.2)
            fn, _ = fit(s.get("numero", ""), "InterTight-Black", W - 2 * M, 1, range(280, 90, -10))
            bb = dd.textbbox((M, y + 60), s.get("numero", ""), font=fn)
            dd.text((M, y + 60), s.get("numero", ""), font=fn, fill=ACC)
            y = bb[3] + 50
            dd.rectangle((M, y, M + 120, y + 6), fill=FG)
            return _text_block(dd, y + 40, {**s, "occhiello": ""}, range(64, 44, -2), 40, 3)
        _centered(img, 160, H - 110, blk)

    elif layout == "citazione":
        def blk(dd, y):
            dd.text((M - 10, y - 40), "“", font=font("InterTight-Black", 300), fill=ACC)
            y += 230
            spaced(dd, (M, y), s.get("occhiello", ""), font("InterTight-ExtraBold", 28), ACC, 0.2)
            quote = s.get("testo", "") or s.get("titolo", "")
            f, lines = fit(quote, "InterTight-SemiBold", W - 2 * M, 8, range(66, 38, -2))
            y = draw_lines(dd, (M, y + 60), lines, f, FG, leading=1.18) + 40
            dd.rectangle((M, y + 16, M + 50, y + 20), fill=ACC)
            fa = font("Inter-Medium", 32)
            for l in wrap(s.get("autore", ""), fa, W - 2 * M - 70)[:2]:
                dd.text((M + 70, y), l, font=fa, fill=MUTED)
                y += 42
            return y
        _centered(img, 160, H - 110, blk)

    else:  # testo
        def blk(dd, y):
            end = _text_block(dd, y, s, range(84, 54, -2), 42, 4)
            dd.rectangle((0, y, 10, end), fill=ACC)
            return end
        _centered(img, 160, H - 110, blk)

    header(img, page, total)
    footer_handle(img)
    progress(img, page, total)
    return img


CTA_TOP = "Segui @{handle}"
CTA_SUB = "per scoprire il mondo in un minuto"


def _cta_editorial(img: Image.Image, y: int):
    """CTA in stile firma editoriale: riga lime, marchio NQ, testo su due righe."""
    d = ImageDraw.Draw(img)
    d.rectangle((M, y, W - M, y + 3), fill=ACC)
    mark = logo_mark(96)
    img.paste(mark, (M, y + 40), mark)
    f1 = font("InterTight-Black", 44)
    d.text((M + 124, y + 42), "Segui ", font=f1, fill=FG)
    d.text((M + 124 + f1.getlength("Segui "), y + 42), f"@{config.HANDLE}", font=f1, fill=ACC)
    d.text((M + 124, y + 96), CTA_SUB, font=font("Inter-Medium", 32), fill=BODY)


def _cta_panel(img: Image.Image, y: int):
    """CTA in un riquadro grigio scuro con bordo lime a sinistra."""
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((M, y, W - M, y + 170), radius=18, fill=(22, 22, 22))
    d.rectangle((M, y, M + 8, y + 170), fill=ACC)
    f1 = font("InterTight-Black", 46)
    d.text((M + 44, y + 34), "Segui ", font=f1, fill=FG)
    d.text((M + 44 + f1.getlength("Segui "), y + 34), f"@{config.HANDLE}", font=f1, fill=ACC)
    d.text((M + 44, y + 98), CTA_SUB, font=font("Inter-Medium", 32), fill=BODY)
    d.text((W - M - 70, y + 50), "→", font=font("InterTight-Black", 64), fill=ACC)


CTA_STYLE = "editorial"


def closing(why: str, page: int, total: int, sources: list[str] | None = None) -> Image.Image:
    """Ultima slide: "Perché ti riguarda", fonti e invito a seguire la pagina."""
    img = Image.new("RGB", (W, H), BG)

    def blk(dd, y):
        spaced(dd, (M, y), "PERCHÉ TI RIGUARDA", font("InterTight-ExtraBold", 28), ACC, 0.2)
        f, lines = fit(why, "InterTight-SemiBold", W - 2 * M, 8, range(58, 34, -2))
        end = draw_lines(dd, (M, y + 70), lines, f, FG, leading=1.22)
        dd.rectangle((0, y + 70, 10, end - 10), fill=ACC)
        return end

    cta_y = H - 330
    _centered(img, 170, cta_y - 120, blk)
    d = ImageDraw.Draw(img)
    if sources:
        fs = font("Inter-Medium", 23)
        txt = "Fonti: " + ", ".join(dict.fromkeys(sources))
        d.text((M, cta_y - 70), wrap(txt, fs, W - 2 * M)[0], font=fs, fill=MUTED)
    (_cta_panel if CTA_STYLE == "panel" else _cta_editorial)(img, cta_y)
    header(img, page, total)
    progress(img, page, total)
    return img


def story(cover_img: Image.Image) -> Image.Image:
    """Storia 1080x1920: copertina al centro, invito a vedere il post."""
    img = Image.new("RGB", (1080, 1920), BG)
    bg = house_style(cover_img, (1080, 1920)).filter(ImageFilter.GaussianBlur(40))
    img = Image.blend(img, bg, 0.35)
    c = cover_img.resize((920, 1150), Image.LANCZOS)
    img.paste(c, (80, 330))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((80, 330, 1000, 1480), radius=4, outline=(60, 60, 60), width=2)
    mark = logo_mark(70)
    img.paste(mark, (80, 170), mark)
    fl = font("InterTight-Black", 44)
    d.text((172, 180), "NUOVO QUOTIDIANO", font=fl, fill=FG)
    fs = font("InterTight-ExtraBold", 30)
    spaced(d, (80, 1540), "NUOVO POST  ·  TOCCA PER LEGGERE", fs, ACC, 0.14)
    return img


def save(img: Image.Image, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=92, optimize=True, progressive=True)
    return path
