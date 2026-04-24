"""OG share-card image renderer.

Produces a 1200x630 PNG suitable for `og:image` / `twitter:card` embeds.
Two layouts:

- Domain card (default): shows score + grade + domain + brand wordmark.
- Brand card (brand=True): homepage embed — shows wordmark + tagline only.

Fonts: DejaVu Serif / Sans are installed on virtually every Linux base image
(fonts-dejavu / fonts-dejavu-core ship with Debian slim + Fly's default
python images). If the serif isn't found we fall back to the Pillow default.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Ship the fonts we need inside the Python package so the renderer works on
# every deployment target (Fly's default python image doesn't include
# DejaVu/Liberation out of the box). See assets/fonts/README.md for licensing.
_FONT_DIR = Path(__file__).parent / "assets" / "fonts"

# Canvas — OpenGraph's recommended 1.91:1 ratio.
WIDTH = 1200
HEIGHT = 630
MARGIN = 64

# Editorial palette — must stay in sync with frontend/src/index.css.
PAPER = (247, 243, 235)
INK_900 = (31, 27, 22)
INK_600 = (86, 76, 62)
INK_400 = (151, 139, 119)
TERRA = (183, 82, 46)
GOOD = (58, 96, 53)
BAD = (160, 58, 42)

# Primary fonts come from the bundled package assets; the /usr/share paths
# are kept as redundant fallbacks for local dev setups that want to swap in
# a system font.
_SERIF_BOLD = [
    str(_FONT_DIR / "DejaVuSerif-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
]
_SERIF_ITALIC = [
    str(_FONT_DIR / "LiberationSerif-Italic.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Italic.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
]
_SANS = [
    str(_FONT_DIR / "DejaVuSans.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]
_SANS_BOLD = [
    str(_FONT_DIR / "DejaVuSans-Bold.ttf"),
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(candidates: list[str], size: int):
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _grade_color(grade: str) -> tuple[int, int, int]:
    g = (grade or "").upper()
    if g in ("A", "B"):
        return GOOD
    if g in ("D", "F"):
        return BAD
    return TERRA


def _fit_to_width(
    draw: ImageDraw.ImageDraw,
    text: str,
    font_candidates: list[str],
    *,
    start_size: int,
    min_size: int,
    max_width: int,
):
    """Pick the largest font size from start_size→min_size that fits."""
    size = start_size
    while size > min_size:
        font = _load_font(font_candidates, size)
        if draw.textlength(text, font=font) <= max_width:
            return font, size
        size -= 4
    return _load_font(font_candidates, min_size), min_size


def _clamp_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> str:
    if draw.textlength(text, font=font) <= max_width:
        return text
    while text and draw.textlength(text + "…", font=font) > max_width:
        text = text[:-1]
    return (text + "…") if text else "…"


def render_share_card(*, domain: str, score: int, grade: str) -> bytes:
    """Render a per-report share card. Returns PNG bytes."""
    img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    d = ImageDraw.Draw(img)

    content_w = WIDTH - 2 * MARGIN

    # --- Header band ---------------------------------------------------------
    wordmark_font = _load_font(_SERIF_BOLD, 40)
    kicker_font = _load_font(_SANS_BOLD, 16)
    d.text((MARGIN, 52), "AgentGEOScore", fill=INK_900, font=wordmark_font)
    d.text(
        (MARGIN, 104),
        "· GENERATIVE ENGINE OPTIMIZATION, GRADED",
        fill=INK_400,
        font=kicker_font,
    )
    d.line([(MARGIN, 144), (WIDTH - MARGIN, 144)], fill=INK_400, width=1)

    # --- Domain kicker + name ------------------------------------------------
    d.text((MARGIN, 174), "A FIELD REPORT ON", fill=INK_400, font=kicker_font)

    # Auto-scale domain to fit the full width. Base 68 but shrink for long hosts.
    domain_font, _ = _fit_to_width(
        d, domain, _SERIF_BOLD, start_size=68, min_size=40, max_width=content_w
    )
    domain_text = _clamp_text(d, domain, domain_font, content_w)
    d.text((MARGIN, 200), domain_text, fill=INK_900, font=domain_font)

    # --- Score + grade row ---------------------------------------------------
    score_font = _load_font(_SERIF_BOLD, 200)
    grade_font = _load_font(_SERIF_ITALIC, 110)
    out_of_font = _load_font(_SANS, 32)
    grade_label_font = _load_font(_SANS_BOLD, 18)

    score_str = str(int(score))
    score_y = 320
    d.text((MARGIN, score_y), score_str, fill=_grade_color(grade), font=score_font)
    score_w = d.textlength(score_str, font=score_font)

    # Grade letter sits just right of the score, roughly baseline-aligned.
    grade_x = MARGIN + score_w + 40
    grade_y = score_y + 60
    grade_letter = (grade or "?").upper()[:1]
    d.text((grade_x, grade_y), grade_letter, fill=INK_900, font=grade_font)

    # "GRADE" label under the letter.
    grade_letter_w = d.textlength(grade_letter, font=grade_font)
    d.text(
        (grade_x + (grade_letter_w - d.textlength("GRADE", font=grade_label_font)) / 2,
         grade_y + 122),
        "GRADE",
        fill=INK_400,
        font=grade_label_font,
    )

    # "out of 100" to the far right, baseline-aligned with score.
    out_text = "out of 100"
    out_w = d.textlength(out_text, font=out_of_font)
    d.text(
        (WIDTH - MARGIN - out_w, score_y + 80),
        out_text,
        fill=INK_400,
        font=out_of_font,
    )

    # --- Verdict strapline ---------------------------------------------------
    verdict_font = _load_font(_SERIF_ITALIC, 26)
    verdict_text = _verdict_for(score)
    verdict_text = _clamp_text(d, verdict_text, verdict_font, content_w)
    d.text((MARGIN, HEIGHT - 60), verdict_text, fill=INK_600, font=verdict_font)

    return _png_bytes(img)


def render_brand_card() -> bytes:
    """Render the homepage OG card — brand + tagline, no score."""
    img = Image.new("RGB", (WIDTH, HEIGHT), PAPER)
    d = ImageDraw.Draw(img)

    kicker_font = _load_font(_SANS_BOLD, 22)
    hero_font = _load_font(_SERIF_BOLD, 88)
    hero_italic = _load_font(_SERIF_ITALIC, 88)
    tag_font = _load_font(_SERIF_ITALIC, 32)
    wordmark_font = _load_font(_SERIF_BOLD, 32)

    d.text((MARGIN, 72), "A FIELD GUIDE · ISSUE №1", fill=INK_400, font=kicker_font)

    # Hero: "Generative Engine" / "Optimization," (terra italic) / "graded."
    d.text((MARGIN, 144), "Generative Engine", fill=INK_900, font=hero_font)
    d.text((MARGIN, 248), "Optimization,", fill=TERRA, font=hero_italic)
    d.text((MARGIN, 352), "graded.", fill=INK_900, font=hero_font)

    d.line([(MARGIN, 484), (WIDTH - MARGIN, 484)], fill=INK_400, width=1)
    d.text(
        (MARGIN, 504),
        "Paste any URL. We check whether ChatGPT, Claude, Gemini, Perplexity",
        fill=INK_600,
        font=tag_font,
    )
    d.text(
        (MARGIN, 544),
        "& Groq can find, read, and cite your site.",
        fill=INK_600,
        font=tag_font,
    )

    # Wordmark bottom-right.
    wordmark = "AgentGEOScore"
    wm_w = d.textlength(wordmark, font=wordmark_font)
    d.text(
        (WIDTH - MARGIN - wm_w, HEIGHT - MARGIN - 36),
        wordmark,
        fill=INK_900,
        font=wordmark_font,
    )

    return _png_bytes(img)


def _verdict_for(score: int) -> str:
    if score >= 90:
        return "AI agents will find and cite it without breaking a sweat."
    if score >= 75:
        return "Solid — most agents will read and cite it well."
    if score >= 60:
        return "Readable, but leaving citation lift on the table."
    if score >= 40:
        return "Poor. Most agents will struggle to read or cite it."
    return "Critical — AI agents can barely see this site."


def _png_bytes(img: Image.Image) -> bytes:
    buf = BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()
