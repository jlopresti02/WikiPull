#!/usr/bin/env python3
"""Reel format v2: one story, three beats, 8-second loop.

Built from the "WWIT Reel Format v2" mockup (approved Oct 8):
  1. Hook (0-2.5 s): dark ground, two fighter photos side by side with a VS
     badge, accent bar, a kicker line and a big headline that slams in;
     photos slowly zoom 100 -> 108%.
  2. Context (2.5-6 s): photos dim, a white story card slides up over them,
     fact chips underneath.
  3. Question (6-8 s): "YOUR PICK", the question, two answer boxes, a
     comment prompt and the source line; then the Reel loops to frame 1.

A post file opts in with "format": "v2" and a "v2" block:

    "format": "v2",
    "v2": {
      "tag": "BLACK COMBAT 17",                 # top-right box (league, division, event)
      "kicker": "13 YEARS LATER",               # accent line over the headline
      "hook": "Leben vs Akiyama 2",             # big hook headline (defaults to "headline")
      "left":  {"name": "Chris Leben"},         # fighter visuals, as in "visual"
      "right": {"name": "Yoshihiro Akiyama"},   #   (add "file" to pick a photo)
      "story": "One sentence of context.",      # the white card
      "chips": ["FIRST FIGHT: LEBEN", "UFC 116"],
      "question": "Can Leben do it again?",     # defaults to the post's "question"
      "options": ["YES", "NO WAY"],
      "prompt": "Drop it in the comments...",   # optional line under the options
      "accent": "#FFC21A",                      # optional
      "prop": {"type": "cheeseburger", "side": "left"}  # optional drawn prop
    }

"prop" (Oct 9, user request) pops a drawn graphic into one photo column at
the hit, for lighthearted stories (a big weight miss gets a cheeseburger).
Types: "cheeseburger". "side": "left" or "right" (default left).

make_posts.py resolves "left" and "right" to cutouts (stored as
"left_subject" / "right_subject"); a side with no photo gets the
silhouette. Output: reel.mp4 and cover.png (the hook frame).

Fonts: Anton (in the repo) and Barlow Condensed, downloaded into fonts/ on
first use (Google Fonts, OFL). If Barlow can't be had, a condensed system
font or Anton stands in.
"""

import colorsys
import math
import random
import shutil
import subprocess
import sys
import urllib.request
import wave
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# ---- "punch" effects (Oct 9, user request) --------------------------------
# On by default; a post can turn them off with "v2": {"fx": false}.
#  * Color-wheel backgrounds: each photo column gets a bright, MrBeast-style
#    radial background in the hue opposite the photo's own colors, so the
#    fighter pops; the two columns never share a hue or clash with the accent.
#    Cutouts get a white outline.
#  * Movement: photos slide in from the sides, then a hit at T_IMPACT: screen
#    shake, white flash, the VS badge pops and the headline slams. Smaller
#    hits when the story card lands and when the question appears.
#  * Sound: a whoosh into a loud boom at the impact; the music starts right
#    after the boom. Smaller whoosh + hit at each later beat.
T_IMPACT = 0.35
MUSIC_DELAY = 0.42

ROOT = Path(__file__).resolve().parent
FONTS = ROOT / "fonts"
ANTON = FONTS / "Anton-Regular.ttf"
W, H, FPS = 1080, 1920, 30
SECONDS = 8.0
T_CONTEXT, T_QUESTION = 2.5, 6.0

BG = (11, 11, 13)
WHITE = (255, 255, 255)
INK = (11, 11, 13)
COL_A, COL_B = (36, 38, 43), (28, 30, 34)
GREY_LABEL = (90, 94, 102)
GREY_TEXT = (212, 214, 219)
GREY_SOURCE = (169, 173, 181)
CHIP_BG, CHIP_BORDER = (28, 30, 34), (58, 61, 68)
DEFAULT_ACCENT = "#FFC21A"

# Everything is laid out at 2x the 540x960 mockup.
PAD_L, PAD_R = 56, 128          # right gutter keeps clear of Instagram's buttons
PHOTO_TOP, PHOTO_H = 176, 1000
BAR_Y = 1176

BARLOW_URL = "https://github.com/google/fonts/raw/main/ofl/barlowcondensed/BarlowCondensed-{w}.ttf"
WEIGHTS = {500: "Medium", 600: "SemiBold", 700: "Bold", 800: "ExtraBold"}
FALLBACKS = ["/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf"]
_font_cache = {}


_paths = {}


def barlow_path(weight):
    if weight in _paths:
        return _paths[weight]
    _paths[weight] = _barlow_path(weight)
    return _paths[weight]


def _barlow_path(weight):
    path = FONTS / f"BarlowCondensed-{WEIGHTS[weight]}.ttf"
    if not path.exists():
        try:
            with urllib.request.urlopen(BARLOW_URL.format(w=WEIGHTS[weight]), timeout=30) as r:
                data = r.read()
            ImageFont.truetype(__import__("io").BytesIO(data), 20)  # check it's a font
            path.write_bytes(data)
            print(f"v2: downloaded fonts/{path.name}")
        except Exception as exc:
            print(f"v2: could not get Barlow Condensed {WEIGHTS[weight]} ({exc}); using a fallback")
            for f in FALLBACKS:
                if Path(f).exists():
                    return Path(f)
            return ANTON
    return path


def barlow(size, weight=700):
    key = ("barlow", weight, int(size))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(barlow_path(weight)), int(size))
    return _font_cache[key]


def anton(size):
    key = ("anton", int(size))
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(ANTON), int(size))
    return _font_cache[key]


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ---- text helpers -------------------------------------------------------

def spaced_width(text, f, spacing):
    if not text:
        return 0
    return sum(f.getlength(c) for c in text) + spacing * (len(text) - 1)


def draw_spaced(d, xy, text, f, fill, spacing=0, anchor="ls"):
    """Draw text with letter spacing. xy is the left baseline (anchor ls)."""
    x, y = xy
    if spacing == 0:
        d.text((x, y), text, font=f, fill=fill, anchor=anchor)
        return
    for c in text:
        d.text((x, y), c, font=f, fill=fill, anchor=anchor)
        x += f.getlength(c) + spacing


def cap(f):
    return -f.getbbox("H", anchor="ls")[1]


def wrap(text, f, max_w, spacing=0):
    lines, cur = [], ""
    for word in text.split():
        trial = (cur + " " + word).strip()
        if spaced_width(trial, f, spacing) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


def balance(lines, f, max_w):
    """Re-split wrapped text so the lines are as even as possible (no lone
    word on the last line)."""
    words = " ".join(lines).split()
    n = len(lines)
    if n < 2 or len(words) <= n:
        return lines
    best, best_w = lines, max(f.getlength(l) for l in lines)
    if n == 2:
        for i in range(1, len(words)):
            cand = [" ".join(words[:i]), " ".join(words[i:])]
            w = max(f.getlength(l) for l in cand)
            if w <= max_w and w < best_w:
                best, best_w = cand, w
    return best


def fit_lines(text, make_font, size, max_w, max_lines, min_size=24):
    """Largest size (from `size` down) at which `text` wraps into max_lines
    and no single word is wider than max_w."""
    while True:
        f = make_font(size)
        lines = wrap(text, f, max_w)
        if (len(lines) <= max_lines and all(f.getlength(l) <= max_w for l in lines)) \
                or size <= min_size:
            return f, balance(lines, f, max_w), size
        size = int(size * 0.94)


# ---- pieces -------------------------------------------------------------

def draw_header(d, accent, tag=None):
    top = 56
    f_box = anton(44)
    box_txt = "WWIT"
    bw = int(spaced_width(box_txt, f_box, 2)) + 40
    bh = 72
    d.rectangle([PAD_L, top, PAD_L + bw, top + bh], fill=accent)
    base = top + bh / 2 + cap(f_box) / 2
    draw_spaced(d, (PAD_L + 20, base), box_txt, f_box, INK, 2)
    f_lab = barlow(40, 700)
    draw_spaced(d, (PAD_L + bw + 16, top + bh / 2 + cap(f_lab) / 2), "MMA NEWS", f_lab, WHITE, 6)
    if tag:
        f_tag = barlow(32, 700)
        tw = spaced_width(tag, f_tag, 4)
        right = W - PAD_R
        x0 = right - tw - 40
        th = 60
        y0 = top + (bh - th) / 2
        d.rectangle([x0, y0, right, y0 + th], outline=accent, width=4)
        draw_spaced(d, (x0 + 20, y0 + th / 2 + cap(f_tag) / 2), tag, f_tag, accent, 4)


def fit_cut(cut, box_w, box_h):
    """Scale a cutout to fill its column: as tall as the column allows,
    trimmed to its painted area first."""
    bbox = cut.getbbox() or (0, 0, cut.width, cut.height)
    cut = cut.crop(bbox)
    # Same height for both sides (the column clips a wide photo); only a
    # very wide cutout is held back so the face isn't cropped away.
    s = min(box_h * 0.80 / cut.height, box_w * 1.7 / cut.width)
    return cut.resize((max(1, int(cut.width * s)), max(1, int(cut.height * s))), Image.LANCZOS)


def silhouette(box_w, box_h):
    S = 2
    w, h = 900 * S, 1000 * S
    g = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    cx = w // 2
    body = (70, 73, 80)
    d.rounded_rectangle([cx - 420 * S, 590 * S, cx + 420 * S, 1300 * S], radius=230 * S, fill=body)
    d.rounded_rectangle([cx - 85 * S, 440 * S, cx + 85 * S, 640 * S], radius=40 * S, fill=body)
    d.ellipse([cx - 190 * S, 40 * S, cx + 190 * S, 500 * S], fill=body)
    f = anton(360 * S)
    l, t, r, b = f.getbbox("?")
    d.text((cx - (l + r) // 2, 270 * S - (t + b) // 2), "?", font=f, fill=BG)
    g = g.resize((w // S, h // S), Image.LANCZOS)
    return fit_cut(g, box_w, box_h)


def dominant_hue(cut):
    """Average hue of a cutout's colorful pixels (0..1), or None if grey."""
    small = cut.copy()
    small.thumbnail((90, 90))
    alpha = small.getchannel("A")
    hsv = small.convert("RGB").convert("HSV")
    sx = sy = wt = 0.0
    for (h, s, v), a in zip(hsv.getdata(), alpha.getdata()):
        if a < 128 or v < 40:
            continue
        w = (s / 255) * (v / 255)
        ang = h / 255 * 2 * math.pi
        sx += math.cos(ang) * w
        sy += math.sin(ang) * w
        wt += w
    if wt < 1e-3 or math.hypot(sx, sy) / wt < 0.08:
        return None
    return (math.atan2(sy, sx) / (2 * math.pi)) % 1.0


def hue_dist(a, b):
    d = abs(a - b) % 1.0
    return min(d, 1 - d)


def pick_bg_hues(cuts, accent):
    """Complementary hue per column; columns at least 0.2 apart on the wheel
    and away from the accent's hue."""
    acc_h = colorsys.rgb_to_hsv(*[c / 255 for c in accent])[0]
    defaults = [0.58, 0.92]          # electric blue, hot pink
    hues = []
    for i, c in enumerate(cuts):
        h = dominant_hue(c) if c is not None else None
        hues.append((h + 0.5) % 1.0 if h is not None else defaults[i])
    for i in range(2):
        if hue_dist(hues[i], acc_h) < 0.08:
            hues[i] = (hues[i] + 0.12) % 1.0
    if hue_dist(hues[0], hues[1]) < 0.2:
        hues[1] = (hues[0] + 0.33) % 1.0
        if hue_dist(hues[1], acc_h) < 0.08:
            hues[1] = (hues[0] + 0.62) % 1.0
    return hues


def hsv_rgb(h, s, v):
    return tuple(int(round(x * 255)) for x in colorsys.hsv_to_rgb(h, s, v))


def burst_panel(hue, w, h):
    """Bright center fading to a deep edge, with faint sunburst rays."""
    inner, outer = hsv_rgb(hue, 0.72, 1.0), hsv_rgb(hue, 0.95, 0.42)
    grad = Image.radial_gradient("L").resize((w * 2, h * 2))
    grad = grad.crop((w // 2, int(h * 0.45), w // 2 + w, int(h * 0.45) + h))
    panel = Image.composite(Image.new("RGB", (w, h), outer), Image.new("RGB", (w, h), inner), grad)
    rays = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(rays)
    cx, cy, R = w // 2, int(h * 0.45), max(w, h) * 2
    for k in range(0, 360, 20):
        d.pieslice([cx - R, cy - R, cx + R, cy + R], k, k + 10, fill=34)
    panel = Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), panel, rays)
    return panel.convert("RGBA")


def outlined(cut, stroke=9):
    """Cutout with a white outline and a soft glow behind it."""
    pad = stroke * 3
    a = Image.new("L", (cut.width + 2 * pad, cut.height + 2 * pad), 0)
    a.paste(cut.getchannel("A"), (pad, pad))
    small = a.resize((max(1, a.width // 3), max(1, a.height // 3)))
    grown = small.filter(ImageFilter.MaxFilter(2 * (stroke // 3) + 1)).resize(a.size)
    grown = grown.filter(ImageFilter.GaussianBlur(1.5))
    glow = a.filter(ImageFilter.GaussianBlur(stroke * 2)).point(lambda v: int(v * 0.6))
    out = Image.new("RGBA", a.size, (255, 255, 255, 0))
    out.putalpha(ImageChops.lighter(grown, glow))
    out.alpha_composite(cut, (pad, pad))
    # keep the bottom edge flat on the bar (no outline under the body)
    return out.crop((0, 0, out.width, pad + cut.height))


def draw_cheeseburger(size):
    """A cartoon cheeseburger drawn with PIL (no outside art), RGBA."""
    S = size * 3
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    ol = (40, 22, 10, 255)
    lw = max(4, S // 60)
    x0, x1 = int(S * 0.08), int(S * 0.92)
    # bottom bun
    d.rounded_rectangle([x0 + S * 0.02, S * 0.74, x1 - S * 0.02, S * 0.90], radius=int(S * 0.07),
                        fill=(214, 140, 52, 255), outline=ol, width=lw)
    # patty
    d.rounded_rectangle([x0 - S * 0.02, S * 0.58, x1 + S * 0.02, S * 0.76], radius=int(S * 0.08),
                        fill=(110, 58, 28, 255), outline=ol, width=lw)
    # cheese with drips
    pts = [(x0 - S * 0.04, S * 0.56), (x1 + S * 0.04, S * 0.56), (x1 + S * 0.01, S * 0.62),
           (S * 0.74, S * 0.62), (S * 0.68, S * 0.73), (S * 0.62, S * 0.62), (S * 0.40, S * 0.62),
           (S * 0.33, S * 0.71), (S * 0.27, S * 0.62), (x0 - S * 0.01, S * 0.62)]
    d.polygon(pts, fill=(255, 196, 30, 255), outline=ol)
    d.line(pts + [pts[0]], fill=ol, width=lw, joint="curve")
    # lettuce (wavy)
    wave_pts = []
    n = 14
    for i in range(n + 1):
        x = x0 - S * 0.03 + (x1 - x0 + S * 0.06) * i / n
        y = S * 0.53 + (S * 0.03 if i % 2 else 0)
        wave_pts.append((x, y))
    d.polygon([(x0 - S * 0.03, S * 0.49), (x1 + S * 0.03, S * 0.49)] + wave_pts[::-1],
              fill=(92, 190, 60, 255), outline=ol)
    # top bun
    d.chord([x0, S * 0.12, x1, S * 0.82], 180, 360, fill=(226, 150, 58, 255), outline=ol, width=lw)
    d.rectangle([x0 + lw, S * 0.44, x1 - lw, S * 0.50], fill=(226, 150, 58, 255))
    d.line([x0, S * 0.50, x1, S * 0.50], fill=ol, width=lw)
    # shine + sesame seeds
    d.arc([x0 + S * 0.08, S * 0.18, x1 - S * 0.30, S * 0.70], 200, 250, fill=(255, 220, 160, 255), width=lw * 2)
    rnd = random.Random(3)
    for _ in range(11):
        sx = rnd.uniform(S * 0.22, S * 0.78)
        sy = rnd.uniform(S * 0.22, S * 0.40)
        a = rnd.uniform(-40, 40)
        seed = Image.new("RGBA", (int(S * 0.06), int(S * 0.035)), (0, 0, 0, 0))
        ImageDraw.Draw(seed).ellipse([0, 0, seed.width - 1, seed.height - 1], fill=(255, 244, 214, 255))
        seed = seed.rotate(a, expand=True, resample=Image.BICUBIC)
        img.alpha_composite(seed, (int(sx), int(sy)))
    img = img.resize((size, size), Image.LANCZOS)
    # white sticker outline + soft shadow
    a = img.getchannel("A")
    grown = a.filter(ImageFilter.MaxFilter(13))
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    sticker = Image.new("RGBA", img.size, (255, 255, 255, 0))
    sticker.putalpha(grown)
    out.alpha_composite(sticker)
    out.alpha_composite(img)
    return out


PROPS = {"cheeseburger": draw_cheeseburger}


def ease_out_back(x, k=1.6):
    x = min(1.0, max(0.0, x))
    return 1 + (k + 1) * (x - 1) ** 3 + k * (x - 1) ** 2


def ease_out(x):
    x = min(1.0, max(0.0, x))
    return 1 - (1 - x) ** 3


class V2:
    def __init__(self, spec, left_cut, right_cut):
        v = spec["v2"]
        self.fx = v.get("fx", True)
        self.accent = hex_rgb(v.get("accent", DEFAULT_ACCENT))
        self.tag = (v.get("tag") or "").upper() or None
        self.kicker = (v.get("kicker") or "").upper()
        self.hook = (v.get("hook") or spec["headline"]).upper()
        self.story = v.get("story", "")
        self.chips = [c.upper() for c in v.get("chips", [])][:4]
        self.question = (v.get("question") or spec.get("question") or "").upper()
        self.options = [o.upper() for o in v.get("options", ["YES", "NO WAY"])][:2]
        self.prompt = v.get("prompt", "Drop it in the comments, then send this to the friend who'll argue.")
        src = " · ".join(s.upper() for s in spec.get("sources", []))
        self.source = (f"SOURCE: {src}   ·   @WWITMMA" if src else "@WWITMMA")

        self.col_w = (W - 8) // 2
        self.cuts = []
        for c in (left_cut, right_cut):
            if c is not None and c.info.get("prop"):
                # a drawn prop: whole, most of the column wide, lifted off the bar
                c = c.crop(c.getbbox() or (0, 0, c.width, c.height))
                sc = self.col_w * 0.86 / c.width
                c = c.resize((int(c.width * sc), int(c.height * sc)), Image.LANCZOS)
                lifted = Image.new("RGBA", (c.width, c.height + 230), (0, 0, 0, 0))
                lifted.alpha_composite(c, (0, 0))
                self.cuts.append(lifted)
                continue
            self.cuts.append(fit_cut(c, self.col_w, PHOTO_H) if c is not None
                             else silhouette(self.col_w, PHOTO_H))
        if self.fx:
            self.hues = pick_bg_hues([left_cut, right_cut], self.accent)
            self.panels = [burst_panel(h, self.col_w, PHOTO_H) for h in self.hues]
            self.cuts = [outlined(c) for c in self.cuts]
        else:
            self.hues = None
            self.panels = [Image.new("RGBA", (self.col_w, PHOTO_H), col + (255,))
                           for col in (COL_A, COL_B)]
        self.text_hook = self._hook_layer()
        self.card, self.card_h = self._context_card()
        self.chips_layer = self._chips_layer()
        self.question_frame = self._question_frame()
        prop = v.get("prop")
        self.prop = None
        if prop and PROPS.get(prop.get("type")):
            size = int(prop.get("size", 300))
            self.prop = (PROPS[prop["type"]](size + 24).rotate(-12, expand=True, resample=Image.BICUBIC),
                         0 if prop.get("side", "left") == "left" else 1)

    # photos with VS badge, at a zoom factor; dim = 0..1 (0.45 = 55% opacity)
    def photos(self, zoom=1.0, dim=0.0, slide=1.0, badge=1.0):
        """slide: 0 = photos off-screen to the sides, 1 = in place.
        badge: VS badge scale (0 hides it)."""
        img = Image.new("RGBA", (W, H), BG + (255,))
        xs = [0, self.col_w + 8]
        for i, (x0, cut) in enumerate(zip(xs, self.cuts)):
            panel = self.panels[i].copy()
            cw, ch = int(cut.width * zoom), int(cut.height * zoom)
            c = cut.resize((cw, ch), Image.LANCZOS) if zoom != 1.0 else cut
            off = int((1 - slide) * self.col_w * 1.1) * (-1 if i == 0 else 1)
            px = (self.col_w - cw) // 2 + off
            py = PHOTO_H - ch  # bottoms on the accent bar
            panel.alpha_composite(c, (px, py)) if px > -cw and px < self.col_w else None
            img.alpha_composite(panel, (x0, PHOTO_TOP))
        if self.prop and badge > 0.01:
            pimg, side = self.prop
            sc = badge * zoom
            pw, ph = max(1, int(pimg.width * sc)), max(1, int(pimg.height * sc))
            p = pimg.resize((pw, ph), Image.LANCZOS)
            cx = (self.col_w - 170) if side == 0 else (self.col_w + 8 + 170)
            cy = PHOTO_TOP + PHOTO_H - 190
            img.alpha_composite(p, (cx - pw // 2, cy - ph // 2))
        if dim > 0:
            shade = Image.new("RGBA", (W, PHOTO_H), BG + (int(255 * dim),))
            img.alpha_composite(shade, (0, PHOTO_TOP))
        if badge > 0.01:
            r = int(80 * badge)
            cx, cy = W // 2, PHOTO_TOP + 248 + 80
            d = ImageDraw.Draw(img)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=BG, outline=self.accent,
                      width=max(2, int(6 * badge)))
            f = anton(max(8, int(60 * badge)))
            d.text((cx, cy + cap(f) / 2), "VS", font=f, fill=self.accent, anchor="ms")
        d = ImageDraw.Draw(img)
        d.rectangle([0, BAR_Y, W, BAR_Y + 12], fill=self.accent)
        return img

    def _hook_layer(self):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        max_w = W - PAD_L - PAD_R
        y = BAR_Y + 12 + 44
        if self.kicker:
            fk = barlow(52, 800)
            y += cap(fk)
            draw_spaced(d, (PAD_L, y), self.kicker, fk, self.accent, 6)
            y += 28
        f, lines, size = fit_lines(self.hook, anton, 124, max_w, 2)
        lh = size * 1.02
        y += cap(f)
        for line in lines:
            d.text((PAD_L, y), line, font=f, fill=WHITE, anchor="ls")
            y += lh
        return layer

    def _context_card(self):
        cw = W - PAD_L - PAD_R
        pad = 48
        fl = barlow(36, 800)
        fs, lines, size = fit_lines(self.story, lambda s: barlow(s, 700), 68, cw - 2 * pad, 5)
        lh = size * 1.12
        h = 16 + pad + cap(fl) + 28 + cap(fs) + lh * (len(lines) - 1) + pad + 12
        card = Image.new("RGBA", (cw, int(h)), WHITE + (255,))
        d = ImageDraw.Draw(card)
        d.rectangle([0, 0, cw, 16], fill=self.accent)
        y = 16 + pad + cap(fl)
        draw_spaced(d, (pad, y), "THE STORY", fl, GREY_LABEL, 6)
        y += 28 + cap(fs)
        for line in lines:
            d.text((pad, y), line, font=fs, fill=INK, anchor="ls")
            y += lh
        return card, int(h)

    def _chips_layer(self):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        if not self.chips:
            return layer
        d = ImageDraw.Draw(layer)
        f = barlow(40, 700)
        x, y = PAD_L, 0  # y set when composed (below the card)
        ch = 16 * 2 + cap(f) + 8
        rows, row = [], []
        for c in self.chips:
            w = f.getlength(c) + 48
            if row and x + w > W - PAD_R:
                rows.append(row)
                row, x = [], PAD_L
            row.append((x, c, w))
            x += w + 20
        rows.append(row)
        self.chip_rows = (rows, ch, f)
        return layer

    def draw_chips(self, img, top):
        rows, ch, f = self.chip_rows if self.chips else ([], 0, None)
        d = ImageDraw.Draw(img)
        y = top
        for row in rows:
            for x, c, w in row:
                d.rectangle([x, y, x + w, y + ch], fill=CHIP_BG, outline=CHIP_BORDER, width=2)
                d.text((x + 24, y + ch / 2 + cap(f) / 2), c, font=f, fill=WHITE, anchor="ls")
            y += ch + 20

    def _question_frame(self):
        img = Image.new("RGBA", (W, H), BG + (255,))
        if self.fx:
            # faint color-wheel burst from the left fighter's hue
            glow = burst_panel(self.hues[0], W, H)
            glow.putalpha(Image.radial_gradient("L").resize((W * 2, H * 2))
                          .crop((W // 2, H // 2, W // 2 + W, H // 2 + H))
                          .point(lambda v: int((255 - v) * 0.22)))
            img.alpha_composite(glow)
        d = ImageDraw.Draw(img)
        draw_header(d, self.accent)
        max_w = W - PAD_L - PAD_R
        y = 400
        fk = barlow(48, 800)
        y += cap(fk)
        draw_spaced(d, (PAD_L, y), "YOUR PICK", fk, self.accent, 6)
        y += 56
        fq, lines, size = fit_lines(self.question, anton, 168, max_w, 4)
        lh = size * 0.98
        y += cap(fq)
        for line in lines:
            d.text((PAD_L, y), line, font=fq, fill=WHITE, anchor="ls")
            y += lh
        y += 24 - lh + 56 + 24
        bw = (max_w - 24) // 2
        fo = anton(68)
        opts = self.options + ["NO WAY"] * (2 - len(self.options))
        f_used = fo
        for o in opts:
            while f_used.getlength(o) > bw - 40 and f_used.size > 30:
                f_used = anton(f_used.size - 4)
        bh = 40 * 2 + cap(f_used) + 8
        for i, o in enumerate(opts):
            x0 = PAD_L + i * (bw + 24)
            if self.fx:
                d.rectangle([x0, y, x0 + bw, y + bh], fill=hsv_rgb(self.hues[i], 0.85, 0.85),
                            outline=WHITE, width=6)
            else:
                d.rectangle([x0, y, x0 + bw, y + bh], outline=self.accent if i == 0 else WHITE, width=6)
            d.text((x0 + bw / 2, y + bh / 2 + cap(f_used) / 2), o, font=f_used, fill=WHITE, anchor="ms")
        y += bh + 56
        fp = barlow(48, 600)
        for line in wrap(self.prompt, fp, max_w)[:3]:
            y += cap(fp)
            d.text((PAD_L, y), line, font=fp, fill=GREY_TEXT, anchor="ls")
            y += 18
        fs = barlow(32, 600)
        src = self.source
        while spaced_width(src, fs, 2) > max_w and fs.size > 18:
            fs = barlow(fs.size - 2, 600)
        draw_spaced(d, (PAD_L, max(1520 + cap(fs), y + 60)), src, fs, GREY_SOURCE, 2)
        return img

    # ---- frames -----------------------------------------------------

    def frame(self, t):
        img = self._frame(t)
        if not self.fx:
            return img
        # punch-in when the question appears
        if T_QUESTION <= t < T_QUESTION + 0.18:
            s = 1.07 - 0.07 * ease_out((t - T_QUESTION) / 0.18)
            big = img.resize((int(W * s), int(H * s)), Image.BILINEAR)
            x, y = (big.width - W) // 2, (big.height - H) // 2
            img = big.crop((x, y, x + W, y + H))
        # screen shake
        amp = 0.0
        for t0, a0, dur in ((T_IMPACT, 30, 0.35), (T_CONTEXT + 0.35, 14, 0.2), (T_QUESTION, 14, 0.2)):
            if t0 <= t < t0 + dur:
                amp = max(amp, a0 * (1 - (t - t0) / dur))
        if amp > 0.5:
            rnd = random.Random(int(t * FPS))
            dx, dy = int(rnd.uniform(-amp, amp)), int(rnd.uniform(-amp, amp))
            shaken = Image.new("RGB", (W, H), BG)
            shaken.paste(img, (dx, dy))
            img = shaken
        # white flash on the hits
        for t0, a0, dur in ((T_IMPACT, 0.6, 0.14), (T_QUESTION, 0.3, 0.1)):
            if t0 <= t < t0 + dur:
                a = a0 * (1 - (t - t0) / dur)
                img = Image.blend(img, Image.new("RGB", (W, H), WHITE), a)
        return img

    def _frame(self, t):
        if t >= T_QUESTION:
            img = self.question_frame.copy()
            # quick fade up from the context frame over 0.15 s
            k = min(1.0, (t - T_QUESTION) / 0.15)
            if k < 1:
                prev = self._frame(T_QUESTION - 0.001).convert("RGBA")
                img = Image.blend(prev, img, k)
            return img.convert("RGB")
        zoom = 1.0 + 0.08 * (t / T_QUESTION)
        if t < T_CONTEXT:
            if self.fx:
                # photos slide in, then the hit: VS pops, headline slams
                slide = ease_out_back(t / T_IMPACT, 1.2) if t < T_IMPACT else 1.0
                badge = ease_out_back((t - T_IMPACT) / 0.22, 2.4) if t >= T_IMPACT else 0.0
                img = self.photos(zoom, slide=slide, badge=badge)
                k_raw = (t - (T_IMPACT - 0.05)) / 0.2
            else:
                img = self.photos(zoom)
                k_raw = t / 0.25
            d = ImageDraw.Draw(img)
            draw_header(d, self.accent, self.tag)
            # headline slams in from 112% scale and 40% opacity
            if k_raw <= 0:
                return img.convert("RGB")
            k = min(1.0, k_raw)
            k = 1 - (1 - k) ** 3
            layer = self.text_hook
            if k < 1:
                s = 1.12 - 0.12 * k
                big = layer.resize((int(W * s), int(H * s)), Image.LANCZOS)
                # scale around the headline's left baseline area
                ox, oy = PAD_L, BAR_Y + 120
                x, y = int(ox - ox * s), int(oy - oy * s)
                tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                tmp.paste(big, (x, y), big)
                tmp.putalpha(tmp.getchannel("A").point(lambda v: int(v * (0.4 + 0.6 * k))))
                layer = tmp
            img.alpha_composite(layer)
            return img.convert("RGB")
        # context: dim photos, card slides up (0.35 s), chips fade in
        u = min(1.0, (t - T_CONTEXT) / 0.35)
        u = 1 - (1 - u) ** 3
        img = self.photos(zoom, dim=0.45 * u)
        d = ImageDraw.Draw(img)
        draw_header(d, self.accent, self.tag)
        if u < 1:
            # hook text fades out under the rising card
            fade = self.text_hook.copy()
            fade.putalpha(fade.getchannel("A").point(lambda v: int(v * (1 - u))))
            img.alpha_composite(fade)
        card_top = 800
        y = int(H - (H - card_top) * u)
        img.alpha_composite(self.card, (PAD_L, y)) if y >= 0 else None
        chips_top = card_top + self.card_h + 48
        if u >= 1 or t - T_CONTEXT > 0.2:
            chip_img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            self.draw_chips(chip_img, chips_top)
            a = min(1.0, (t - T_CONTEXT - 0.2) / 0.25)
            chip_img.putalpha(chip_img.getchannel("A").point(lambda v: int(v * a)))
            img.alpha_composite(chip_img)
        return img.convert("RGB")


def write_sfx(path, seconds, sr=44100):
    """Whoosh -> boom at T_IMPACT, smaller whoosh + hit when the story card
    lands and when the question appears. Mono 16-bit WAV."""
    import numpy as np
    n = int(seconds * sr)
    out = np.zeros(n)
    rng = np.random.default_rng(7)

    def lowpass(x, fc):
        # one-pole lowpass with a per-sample cutoff
        a = 1 - np.exp(-2 * np.pi * np.asarray(fc) / sr) * np.ones(len(x))
        y = np.empty_like(x)
        acc = 0.0
        for i in range(len(x)):
            acc += a[i] * (x[i] - acc)
            y[i] = acc
        return y

    def whoosh(t_end, dur, gain):
        m = int(dur * sr)
        i0 = int(t_end * sr) - m
        if i0 < 0:
            m += i0
            i0 = 0
        x = rng.standard_normal(m)
        p = np.linspace(0, 1, m)
        y = lowpass(x, 250 + 7000 * p ** 2)
        y = y - lowpass(y, 180)            # thin out the rumble
        env = p ** 2.2
        out[i0:i0 + m] += gain * y * env / (np.abs(y).max() + 1e-9)

    def boom(t0, gain, length=1.3):
        i0 = int(t0 * sr)
        m = min(int(length * sr), n - i0)
        if m <= 0:
            return
        tt = np.arange(m) / sr
        f = 38 + 72 * np.exp(-tt / 0.07)                    # 110 Hz -> 38 Hz drop
        sub = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-tt / 0.45)
        f2 = 60 + 140 * np.exp(-tt / 0.03)
        thump = np.sin(2 * np.pi * np.cumsum(f2) / sr) * np.exp(-tt / 0.09)
        click = lowpass(rng.standard_normal(m), 3000) * np.exp(-tt / 0.018) * 4
        y = np.tanh(1.8 * (0.95 * sub + 0.6 * thump + 0.5 * click))
        out[i0:i0 + m] += gain * y

    whoosh(T_IMPACT, T_IMPACT, 0.55)
    boom(T_IMPACT, 1.0)
    whoosh(T_CONTEXT + 0.35, 0.35, 0.3)
    boom(T_CONTEXT + 0.35, 0.45, 0.6)
    whoosh(T_QUESTION, 0.28, 0.3)
    boom(T_QUESTION, 0.55, 0.8)
    peak = np.abs(out).max() or 1.0
    pcm = (out / peak * 0.97 * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def make_reel_v2(spec, out, left_cut, right_cut):
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to make a Reel")
    seconds = float(spec.get("seconds_v2", SECONDS))
    frames = int(seconds * FPS)
    v = V2(spec, left_cut, right_cut)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    music = spec.get("music")
    track = ROOT / music if music else None
    if music and not track.exists():
        sys.exit(f"music file not found: {music}")
    if v.fx:
        sfx = out / "_sfx.wav"
        write_sfx(sfx, seconds)
        cmd += ["-i", str(sfx)]
        if track:
            # music comes in right after the boom
            mlen = seconds - MUSIC_DELAY
            cmd += ["-ss", str(float(spec.get("music_start", 0))), "-t", str(mlen), "-i", str(track)]
            ms = int(MUSIC_DELAY * 1000)
            graph = (f"[2:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=0.85,"
                     f"afade=t=in:d=0.12,afade=t=out:st={max(0.0, mlen - 1.0)}:d=1.0,"
                     f"adelay={ms}|{ms}[m];"
                     f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,volume=1.1[s];"
                     f"[m][s]amix=inputs=2:duration=longest:normalize=0,"
                     f"alimiter=limit=0.95,atrim=0:{seconds}[a]")
        else:
            graph = f"[1:a]aformat=sample_rates=44100:channel_layouts=stereo,atrim=0:{seconds}[a]"
        cmd += ["-filter_complex", graph, "-map", "0:v", "-map", "[a]"]
    elif track:
        cmd += ["-ss", str(float(spec.get("music_start", 0))), "-t", str(seconds), "-i", str(track),
                "-af", f"afade=t=in:d=0.3,afade=t=out:st={max(0.0, seconds - 1.0)}:d=1.0",
                "-map", "0:v", "-map", "1:a"]
    else:
        cmd += ["-f", "lavfi", "-t", str(seconds), "-i", "anullsrc=r=44100:cl=stereo",
                "-map", "0:v", "-map", "1:a"]
    cmd += ["-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(out / "reel.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(frames):
        proc.stdin.write(v.frame(i / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed to write the v2 Reel")
    (out / "_sfx.wav").unlink(missing_ok=True)
    v.frame(1.0).save(out / "cover.png", optimize=True)
    return v
