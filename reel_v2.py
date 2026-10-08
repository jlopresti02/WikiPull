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
      "accent": "#FFC21A"                       # optional
    }

make_posts.py resolves "left" and "right" to cutouts (stored as
"left_subject" / "right_subject"); a side with no photo gets the
silhouette. Output: reel.mp4 and cover.png (the hook frame).

Fonts: Anton (in the repo) and Barlow Condensed, downloaded into fonts/ on
first use (Google Fonts, OFL). If Barlow can't be had, a condensed system
font or Anton stands in.
"""

import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

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
DEFAULT_CORNERS = ("#D7262E", "#1F6FE0")   # red corner (left), blue corner (right)
SEAM = 70          # diagonal split: seam leans this far either side of centre
T_LAND = 0.40      # fighters land, VS pops, impact (sound hit; music starts here)

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


# ---- colour-wheel backgrounds (thumbnail principle) ---------------------
# Each fighter gets a loud, saturated background chosen against the colours
# of their own photo: far round the colour wheel from the photo's main hue
# (complementary), bright where the photo is dark, never close to the skin
# tones every face shares, never the brand yellow, and clearly different
# from the other fighter's side.

VIVID = {
    "electric cyan": "#00C8FF", "royal blue": "#2457FF", "violet": "#8B3DFF",
    "hot magenta": "#FF2D9B", "fire red": "#FF2B2B", "blaze orange": "#FF7417",
    "lime": "#6BFF2E", "emerald": "#00D97E", "teal": "#00C2B8",
}
SKIN_HUE = 25.0          # degrees: where faces sit on the wheel


def _hue_dist(a, b):
    d = abs(a - b) % 360
    return min(d, 360 - d)


def subject_colour(cut):
    """Main hue (degrees), how colourful it is (0-1) and brightness (0-1) of
    a cutout's visible pixels, ignoring greys that carry no hue."""
    import numpy as np
    small = cut.copy()
    small.thumbnail((240, 240))
    a = np.asarray(small.getchannel("A"), dtype=float) / 255
    hsv = np.asarray(small.convert("RGB").convert("HSV"), dtype=float) / 255
    vis = a > 0.8
    if vis.sum() < 50:
        return SKIN_HUE, 0.0, 0.4
    h, s, v = hsv[..., 0][vis] * 360, hsv[..., 1][vis], hsv[..., 2][vis]
    w = s * v                                   # colourful, lit pixels count most
    if w.sum() < 1e-6:
        return SKIN_HUE, 0.0, float(v.mean())
    ang = np.radians(h)
    hue = (np.degrees(np.arctan2((np.sin(ang) * w).sum(), (np.cos(ang) * w).sum())) + 360) % 360
    return float(hue), float((s * v).mean() * 2), float(v.mean())


def _bg_score(bg_hex, subj, accent_hue):
    import colorsys
    r, g, b = hex_rgb(bg_hex)
    bh, bs, bv = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
    bh *= 360
    hue, chroma, light = subj
    comp = _hue_dist(bh, hue) / 180                       # 1 = complementary
    skin = _hue_dist(bh, SKIN_HUE) / 180                  # keep away from faces
    lum = 0.2126 * r / 255 + 0.7152 * g / 255 + 0.0722 * b / 255
    contrast = abs(lum - light * 0.75)                    # bright behind a dark photo
    score = 1.2 * comp * min(1.0, 0.4 + chroma) + 1.0 * skin + 1.4 * contrast
    if _hue_dist(bh, accent_hue) < 30:
        score -= 0.8                                      # brand yellow is for badges
    return score, bh


def pick_backgrounds(cuts, accent, seed=""):
    import colorsys
    ah = colorsys.rgb_to_hsv(*(c / 255 for c in accent))[0] * 360
    subs = [subject_colour(c) if c is not None else (SKIN_HUE, 0.0, 0.3) for c in cuts]
    scored = [{n: _bg_score(h, s, ah) for n, h in VIVID.items()} for s in subs]
    pairs = []
    for n1, (s1, h1) in scored[0].items():
        for n2, (s2, h2) in scored[1].items():
            gap = _hue_dist(h1, h2)
            pairs.append((s1 + s2 + (0.6 if gap >= 90 else -1.5 if gap < 50 else 0), n1, n2))
    pairs.sort(reverse=True)
    # every face sits near the same spot on the wheel, so rotate among the
    # pairs that score close to the best (per story) to keep the feed varied
    top = [p for p in pairs if p[0] >= pairs[0][0] - 0.5][:8]
    import zlib
    _, n1, n2 = top[zlib.crc32(seed.encode()) % len(top)]
    return [hex_rgb(VIVID[n1]), hex_rgb(VIVID[n2])], [n1, n2], subs


def outline_cut(cut, width=9, colour=WHITE):
    """Thumbnail-style white outline plus a soft shadow behind the cutout.
    Edges where the photo is cropped (the subject runs off the image) get no
    stroke, so there's never a straight white line."""
    import numpy as np
    a = np.asarray(cut.getchannel("A"))
    pad_l = 0 if (a[:, :2] > 128).mean() > 0.02 else width + 14
    pad_r = 0 if (a[:, -2:] > 128).mean() > 0.02 else width + 14
    pad_t = width + 14
    W2, H2 = cut.width + pad_l + pad_r, cut.height + pad_t
    base = Image.new("RGBA", (W2, H2), (0, 0, 0, 0))
    alpha = Image.new("L", (W2, H2), 0)
    alpha.paste(cut.getchannel("A"), (pad_l, pad_t))
    shadow = alpha.filter(ImageFilter.GaussianBlur(16)).point(lambda v: int(v * 0.55))
    base.paste(Image.new("RGBA", (W2, H2), (0, 0, 0, 255)), (0, 0), shadow)
    grown = alpha.filter(ImageFilter.GaussianBlur(width / 2)).point(lambda v: 255 if v > 18 else 0)
    grown = grown.filter(ImageFilter.GaussianBlur(1.2))
    base.paste(Image.new("RGBA", (W2, H2), colour + (255,)), (0, 0), grown)
    base.alpha_composite(cut, (pad_l, pad_t))
    return base


class V2:
    def __init__(self, spec, left_cut, right_cut):
        v = spec["v2"]
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

        self.corners = [hex_rgb(c) for c in v.get("corners", DEFAULT_CORNERS)][:2]
        hl = v.get("highlight")
        if hl is None and ":" in self.hook:
            hl = self.hook.split(":", 1)[1]
        elif hl is None:
            hl = self.hook.split()[-1]       # no highlight given: the last word
        self.highlight = set((hl or "").upper().replace(":", " ").split())

        self.col_w = (W - 8) // 2
        self.cuts = []
        for c in (left_cut, right_cut):
            self.cuts.append(fit_cut(c, self.col_w, PHOTO_H) if c is not None
                             else silhouette(self.col_w, PHOTO_H))
        if "corners" not in v:
            self.corners, self.corner_names, self.subject_colours = pick_backgrounds(
                [left_cut, right_cut], self.accent, spec.get("story_id") or self.hook)
            print(f"v2 backgrounds: {self.corner_names[0]} | {self.corner_names[1]}")
        if v.get("outline", True):
            self.cuts = [outline_cut(c) if c is not None and src is not None else c
                         for c, src in zip(self.cuts, (left_cut, right_cut))]
        self._build_panels()
        self._layout_hook()
        self.text_hook = self._hook_layer()
        self.card, self.card_h = self._context_card()
        self.chips_layer = self._chips_layer()
        self.question_frame = self._question_frame()

    # ---- fight-poster panels -------------------------------------------

    def _build_panels(self):
        """Diagonal split with a corner-colour glow behind each fighter."""
        top_mid, bot_mid = W // 2 + SEAM, W // 2 - SEAM
        self.masks, self.panel_bgs = [], []
        polys = [[(0, 0), (top_mid - 5, 0), (bot_mid - 5, PHOTO_H), (0, PHOTO_H)],
                 [(top_mid + 5, 0), (W, 0), (W, PHOTO_H), (bot_mid + 5, PHOTO_H)]]
        for i, poly in enumerate(polys):
            m = Image.new("L", (W, PHOTO_H), 0)
            ImageDraw.Draw(m).polygon(poly, fill=255)
            self.masks.append(m)
            # loud, saturated fill: the colour itself across the panel, a
            # bright hot-spot behind the fighter, darker toward the edges
            c = self.corners[i]
            dark = tuple(int(v * 0.42) for v in c)
            hot = tuple(int(v + (255 - v) * 0.35) for v in c)
            bg = Image.new("RGBA", (W, PHOTO_H), dark + (255,))
            cx = W // 4 if i == 0 else 3 * W // 4
            for col, box, blur in ((c, [cx - 520, -120, cx + 520, PHOTO_H + 200], 120),
                                   (hot, [cx - 260, 120, cx + 260, 760], 110)):
                glow = Image.new("RGBA", (W, PHOTO_H), (0, 0, 0, 0))
                ImageDraw.Draw(glow).ellipse(box, fill=col + (255,))
                bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(blur)))
            # light floor shade so the fighters sit on something
            floor = Image.new("RGBA", (W, PHOTO_H), (0, 0, 0, 0))
            fd = ImageDraw.Draw(floor)
            for k in range(160):
                fd.line([(0, PHOTO_H - k), (W, PHOTO_H - k)], fill=BG + (int(90 * (1 - k / 160)),))
            bg.alpha_composite(floor)
            self.panel_bgs.append(bg)
        seam = Image.new("RGBA", (W, PHOTO_H), (0, 0, 0, 0))
        ImageDraw.Draw(seam).line([(top_mid, -10), (bot_mid, PHOTO_H + 10)], fill=self.accent, width=10)
        self.seam = seam

    # photos with VS badge, at a zoom factor; dim = 0..1 (0.45 = 55% opacity);
    # dx shifts each fighter sideways (slide-in); vs = VS badge scale (0 hides it)
    def photos(self, zoom=1.0, dim=0.0, dx=(0, 0), vs=1.0):
        img = Image.new("RGBA", (W, H), BG + (255,))
        strip = Image.new("RGBA", (W, PHOTO_H), BG + (255,))
        for i, cut in enumerate(self.cuts):
            panel = self.panel_bgs[i].copy()
            cw, ch = int(cut.width * zoom), int(cut.height * zoom)
            c = cut.resize((cw, ch), Image.LANCZOS) if zoom != 1.0 else cut
            cx = W // 4 if i == 0 else 3 * W // 4
            px = cx - cw // 2 + int(dx[i])
            py = PHOTO_H - ch  # bottoms on the accent bar
            panel.paste(c, (px, py), c)
            strip.paste(panel, (0, 0), self.masks[i])
        strip.alpha_composite(self.seam)
        img.alpha_composite(strip, (0, PHOTO_TOP))
        if dim > 0:
            shade = Image.new("RGBA", (W, PHOTO_H), BG + (int(255 * dim),))
            img.alpha_composite(shade, (0, PHOTO_TOP))
        d = ImageDraw.Draw(img)
        if vs > 0.02:
            r = int(92 * vs)
            cx, cy = W // 2, PHOTO_TOP + 300
            d.ellipse([cx - r - 8, cy - r - 8, cx + r + 8, cy + r + 8], fill=BG)
            d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=self.accent)
            f = anton(max(8, int(76 * vs)))
            d.text((cx, cy + cap(f) / 2), "VS", font=f, fill=INK, anchor="ms")
        d.rectangle([0, BAR_Y, W, BAR_Y + 12], fill=self.accent)
        return img

    # ---- hook text: solid kicker tag + big word-by-word headline ----------

    def _layout_hook(self):
        max_w = W - PAD_L - PAD_R
        y = BAR_Y + 12 + 52
        self.kicker_box = None
        if self.kicker:
            fk = barlow(50, 800)
            kw = spaced_width(self.kicker, fk, 5) + 44
            kh = cap(fk) + 36
            box = Image.new("RGBA", (int(kw), int(kh)), self.accent + (255,))
            draw_spaced(ImageDraw.Draw(box), (22, kh / 2 + cap(fk) / 2), self.kicker, fk, INK, 5)
            self.kicker_box = (box, PAD_L, int(y))
            y += kh + 30
        f, lines, size = fit_lines(self.hook, anton, 168, max_w, 3)
        lh = size * 1.0
        y += cap(f)
        space = f.getlength(" ")
        self.words = []          # (image, x, baseline-top y, index)
        n = 0
        for line in lines:
            x = PAD_L
            for word in line.split():
                key = word.strip(":,.!?\"'").upper()
                col = self.accent if key in self.highlight else WHITE
                ww = int(f.getlength(word)) + 4
                im = Image.new("RGBA", (ww, int(size * 1.3)), (0, 0, 0, 0))
                ImageDraw.Draw(im).text((0, cap(f)), word, font=f, fill=col, anchor="ls")
                self.words.append((im, int(x), int(y - cap(f)), n))
                x += f.getlength(word) + space
                n += 1
            y += lh

    def draw_hook(self, img, t):
        if self.kicker_box:
            box, x, y = self.kicker_box
            k = 1.0 if t >= 0.12 else 0.55 + 0.45 * t / 0.12   # on screen from frame 0
            k = 1 - (1 - k) ** 3
            if k > 0:
                img.alpha_composite(box, (int(x - (box.width + x) * (1 - k)), y))
        for im, x, y, i in self.words:
            t0 = 0.0 + 0.06 * i             # first word is on screen from frame 0, then one by one
            k = (t - t0) / 0.14 if t0 > 0 else 1.0
            if k <= 0:
                continue
            k = min(1.0, k)
            s = 1.0 + 0.55 * (1 - k) ** 2   # 155% -> 100%
            a = min(1.0, k * 1.6)
            w2, h2 = int(im.width * s), int(im.height * s)
            w_im = im.resize((w2, h2), Image.LANCZOS) if s != 1.0 else im.copy()
            if a < 1:
                w_im.putalpha(w_im.getchannel("A").point(lambda v: int(v * a)))
            cx, cy = x + im.width / 2, y + im.height / 2
            img.alpha_composite(w_im, (int(cx - w2 / 2), int(cy - h2 / 2)))

    def _hook_layer(self):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self.draw_hook(layer, 99)
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
        if t >= T_QUESTION:
            img = self.question_frame.copy()
            # quick fade up from the context frame over 0.15 s
            k = min(1.0, (t - T_QUESTION) / 0.15)
            if k < 1:
                prev = self.frame(T_QUESTION - 0.001).convert("RGBA")
                img = Image.blend(prev, img, k)
            return img.convert("RGB")
        zoom = 1.0 + 0.10 * (t / T_QUESTION)
        if t < T_CONTEXT:
            # fighters slide in from their own sides (already ~80% in on frame 0)
            # and land at T_LAND; VS pops; one quick impact shake + flash
            k = min(1.0, t / T_LAND)
            k = 1 - (1 - k) ** 3
            off = 0.22 * (W // 2) * (1 - k)
            vs = 0.0
            if t >= T_LAND - 0.04:
                u = min(1.0, (t - T_LAND + 0.04) / 0.18)
                vs = u * (1.0 + 0.35 * (1 - u) * 2) if u < 1 else 1.0   # overshoot then settle
            img = self.photos(zoom, dx=(-off, off), vs=vs)
            d = ImageDraw.Draw(img)
            draw_header(d, self.accent, self.tag)
            self.draw_hook(img, t)
            since = t - T_LAND
            if 0 <= since < 0.10:
                flash = Image.new("RGBA", (W, H), WHITE + (int(70 * (1 - since / 0.10)),))
                img.alpha_composite(flash)
            if 0 <= since < 0.22:
                amp = 18 * (1 - since / 0.22)
                sx = int(amp * (1 if int(since * FPS) % 2 == 0 else -1))
                sy = int(amp * 0.6 * (-1 if int(since * FPS) % 2 == 0 else 1))
                shaken = Image.new("RGBA", (W, H), BG + (255,))
                big = img.resize((int(W * 1.03), int(H * 1.03)), Image.LANCZOS)
                shaken.paste(big, (int(-W * 0.015) + sx, int(-H * 0.015) + sy))
                img = shaken
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


def make_sfx(path, seconds, sr=44100, seed=7):
    """Synthesise the opening sound: a whoosh that builds while the fighters
    slide in, then a heavy cinematic impact at T_LAND (sub drop + crack +
    body). Made in code, so there's nothing to license or credit."""
    import wave
    import numpy as np
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    out = np.zeros((n, 2))
    land = int(T_LAND * sr)

    def lowpass(x, cutoffs):
        y, acc = np.empty_like(x), 0.0
        a = 1 - np.exp(-2 * np.pi * cutoffs / sr)
        for i in range(len(x)):
            acc += a[i] * (x[i] - acc)
            y[i] = acc
        return y

    # whoosh: band of noise sweeping up in pitch and volume into the hit
    wn = land + int(0.06 * sr)
    t = np.arange(wn) / sr
    u = np.clip(t / T_LAND, 0, 1)
    cut_hi = 400 + 5200 * u ** 1.6
    cut_lo = 120 + 1400 * u ** 1.6
    env = (0.15 + 0.85 * u ** 2.2) * np.where(t > T_LAND, np.exp(-(t - T_LAND) / 0.02), 1)
    for ch in range(2):
        noise = rng.standard_normal(wn)
        band = lowpass(noise, cut_hi) - lowpass(noise, cut_lo)
        out[:wn, ch] += 2.6 * band * env
    sweep_f = 180 + 700 * u ** 1.5
    out[:wn] += (0.2 * np.sin(2 * np.pi * np.cumsum(sweep_f) / sr) * env)[:, None]

    # impact
    m = min(n - land, int(1.6 * sr))
    t = np.arange(m) / sr
    f = 38 + 110 * np.exp(-t / 0.045)                       # pitch-dropping sub thump
    sub = np.sin(2 * np.pi * np.cumsum(f) / sr) * np.exp(-t / 0.6)
    sub += 0.6 * np.sin(2 * np.pi * np.cumsum(f * 0.5) / sr) * np.exp(-t / 0.8)   # octave below
    crack_n = rng.standard_normal(m)
    crack = (crack_n - lowpass(crack_n, np.full(m, 1800.0))) * np.exp(-t / 0.012)
    body_n = rng.standard_normal(m)
    body = lowpass(body_n, 300 + 2500 * np.exp(-t / 0.05)) * np.exp(-t / 0.16)
    hit = 2.0 * sub + 1.0 * crack + 1.6 * body
    hit = np.tanh(2.6 * hit)                                 # drive it hard: louder, heavier
    out[land:land + m] += hit[:, None]

    out *= 0.89 / max(1e-9, np.abs(out[land:land + m]).max())  # the hit peaks ~ -1 dBFS
    # push the boom up: soft-clip the hit and its tail so it plays much louder
    out[land:] = 0.95 * np.tanh(2.2 * out[land:]) / np.tanh(2.2)
    out = np.clip(out, -0.95, 0.95)
    pcm = (out * 32767).astype("<i2")
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def make_reel_v2(spec, out, left_cut, right_cut):
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to make a Reel")
    seconds = float(spec.get("seconds_v2", SECONDS))
    frames = int(seconds * FPS)
    v = V2(spec, left_cut, right_cut)
    sfx = out / "_sfx.wav"
    make_sfx(sfx, seconds)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
           "-i", str(sfx)]
    music = spec.get("music")
    if music:
        # music comes in right on the impact, at full level
        track = ROOT / music
        if not track.exists():
            sys.exit(f"music file not found: {music}")
        delay = int(T_LAND * 1000)
        cmd += ["-ss", str(float(spec.get("music_start", 0))), "-t", str(seconds - T_LAND), "-i", str(track),
                "-filter_complex",
                f"[2:a]volume='0.85*min(1,0.3+0.7*t/0.7)':eval=frame,afade=t=in:d=0.08,afade=t=out:st={max(0.0, seconds - T_LAND - 1.0)}:d=1.0,"
                f"adelay={delay}|{delay},apad[m];"
                f"[1:a]volume=1.0[s];[s][m]amix=inputs=2:duration=first:normalize=0,"
                f"alimiter=limit=0.95[a]"]
    else:
        cmd += ["-filter_complex", "[1:a]anull[a]"]
    cmd += ["-map", "0:v", "-map", "[a]", "-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(out / "reel.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(frames):
        proc.stdin.write(v.frame(i / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed to write the v2 Reel")
    sfx.unlink(missing_ok=True)
    v.frame(1.6).save(out / "cover.png", optimize=True)
    return v
