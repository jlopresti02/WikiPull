#!/usr/bin/env python3
"""Render a WWIT MMA News post (and optionally a Reel) from a post file.

Usage:
    python render.py posts/queue/2026-09-30-bjp-returns.json

A post file is a small JSON file:

    {
      "fighter":  "Jiri Prochazka",          # WikiPull search name
      "headline": "BJP Returns",             # 1 to 3 words
      "caption":  "BJP is back. ...",        # the story, in your words
      "sources":  ["CBS Sports", "ESPN"],    # where the story came from
      "color":    "#d2202f",                 # optional, background
      "photo":    1,                         # optional, which cutout to use

      "reel":     true,                      # optional, also make a Reel video
      "music":    "music/track.mp3",         # optional, track in the repo
      "music_credit": "Track by Artist / CC BY 4.0",  # shown in the caption
      "music_start": 12.5,                   # optional, where in the track to start
      "seconds":  8,                         # optional, Reel length (default 8)
      "question": "Colby or Strickland?",    # optional: on the Reel the headline
                                             # turns into this question at 2.5 s
      "follow_card": true                    # optional: last 1.2 s of the Reel
                                             # reads FOLLOW @WWITMMA
    }

Output goes to posts/<post name>/:
    post.png     1080x1350 image for a feed post
    reel.mp4     1080x1920 video with music (only when "reel" is true)
    cover.png    Reel cover image (only when "reel" is true)
    caption.txt  caption + source, photo and music credits
    post.json    the post file, for the record

The design matches the MMA post template: tag at top left, big Anton
headline, fighter cutout as large as possible without touching the text.
"""

import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
FONT = ROOT / "fonts" / "Anton-Regular.ttf"
TAG = "WWIT MMA NEWS"
TAG_X, TAG_H, TAG_SIZE = 60, 70, 38
LEAD = 0.16          # space between lines, as a share of capital height
MAX_TEXT_W = 980     # widest a headline line may be
MARGIN = 28          # gap kept between the text and the fighter
MIN_SHOW = 0.8       # share of the fighter that must stay in frame
DEFAULT_COLOR = "#d2202f"
FPS = 30


@dataclass(frozen=True)
class Layout:
    w: int
    h: int
    tag_y: int        # top of the WWIT MMA NEWS tag
    top_y: int        # where the headline's capitals start
    max_block_h: int  # tallest the whole headline block may be
    bottom_safe: int  # keep framed images/graphics above this many px from the bottom


# Feed post, 4:5.
POST = Layout(1080, 1350, tag_y=60, top_y=160, max_block_h=440, bottom_safe=70)
# Reel, 9:16. Content starts lower to clear Instagram's top bar, sits inside
# the 4:5 middle crop the profile grid shows, and framed images stay above
# the caption and buttons Instagram draws over the bottom of a Reel.
REEL = Layout(1080, 1920, tag_y=330, top_y=430, max_block_h=470, bottom_safe=420)


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def is_light(rgb):
    r, g, b = (c / 255 for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.6


def font(size):
    return ImageFont.truetype(str(FONT), max(1, int(round(size))))


def cap_height(size):
    # Height of a capital letter above the baseline, measured from the font
    return -font(size).getbbox("H", anchor="ls")[1]


def layout_headline(words, L, centered=False):
    """Pick the biggest size that fits the width and height limits.

    centered=True (posts with no image) lets the headline grow and sits it in
    the middle of the space below the tag."""
    n = len(words)
    size = 420.0 if centered else 340.0
    for w in words:
        width = font(size).getlength(w)
        if width > MAX_TEXT_W:
            size = min(size, size * MAX_TEXT_W / width)
    ratio = cap_height(100) / 100
    top = L.tag_y + TAG_H + 60
    room = (L.h - L.bottom_safe) - top
    max_block = room * 0.85 if centered else L.max_block_h
    size = min(size, max_block / (ratio * (n + (n - 1) * LEAD)))
    cap = cap_height(size)
    block = cap * (n + (n - 1) * LEAD)
    top_y = top + (room - block) / 2 if centered else L.top_y
    baselines = [top_y + cap + i * cap * (1 + LEAD) for i in range(n)]
    return size, baselines


def tag_width():
    return int(font(TAG_SIZE).getlength(TAG) + 60)


def draw_words(draw, L, words, size, baselines, fg):
    f = font(size)
    for w, y in zip(words, baselines):
        draw.text((L.w / 2, y), w, font=f, fill=fg, anchor="ms")


def draw_tag(draw, L, fg, bg, light):
    tw = tag_width()
    draw.rounded_rectangle([TAG_X, L.tag_y, TAG_X + tw, L.tag_y + TAG_H], radius=10, fill=fg)
    cap = cap_height(TAG_SIZE)
    draw.text((TAG_X + tw / 2, L.tag_y + TAG_H / 2 + cap / 2), TAG, font=font(TAG_SIZE),
              fill=(255, 255, 255) if light else bg, anchor="ms")


def draw_text_layer(draw, L, words, size, baselines, fg, bg, light):
    draw_words(draw, L, words, size, baselines, fg)
    draw_tag(draw, L, fg, bg, light)


def text_bottoms(L, words, size, baselines):
    """Lowest painted pixel of the headline and tag, per column (-1 = empty)."""
    mask = Image.new("L", (L.w, L.h), 0)
    draw = ImageDraw.Draw(mask)
    draw_text_layer(draw, L, words, size, baselines, 255, 255, False)
    draw.rectangle([TAG_X, L.tag_y, TAG_X + tag_width(), L.tag_y + TAG_H], fill=255)
    a = np.asarray(mask) > 20
    rows = np.arange(L.h)[:, None]
    return np.where(a.any(axis=0), (a * rows).max(axis=0), -1)


def place_fighter(L, cut, bottoms):
    """Largest size and highest spot where the fighter never touches the text.

    Returns (scale, x, y) for the cutout.
    """
    s = min(L.w * 0.96 / cut.width, L.h * 1.6 / cut.height)
    y = 0
    for _ in range(30):
        w2, h2 = max(1, round(cut.width * s)), max(1, round(cut.height * s))
        alpha = np.asarray(cut.resize((w2, h2), Image.BILINEAR).getchannel("A")) > 40
        has = alpha.any(axis=0)
        tops = np.where(has, alpha.argmax(axis=0), -1)
        x0 = (L.w - w2) // 2
        y = L.h - h2  # default: bottom edge on the bottom of the frame
        for i in np.nonzero(has)[0]:
            col = x0 + i
            if 0 <= col < L.w and bottoms[col] >= 0:
                y = max(y, bottoms[col] + MARGIN - tops[i])
        if (L.h - y) / h2 >= MIN_SHOW or s < 0.05:
            break
        s *= 0.95
    return s, (L.w - round(cut.width * s)) // 2, int(y)


def photo_card(photo, max_w, max_h):
    """A photo (flag, venue) as a framed card: white border, rounded corners,
    soft shadow. Sized to fit max_w x max_h including the shadow."""
    border, radius, pad, off = 12, 28, 30, 12
    photo = photo.convert("RGB")
    s = min((max_w - 2 * (border + pad)) / photo.width,
            (max_h - 2 * (border + pad) - off) / photo.height)
    pw, ph = max(1, int(photo.width * s)), max(1, int(photo.height * s))
    cw, ch = pw + 2 * border, ph + 2 * border
    card = Image.new("RGBA", (cw, ch), (255, 255, 255, 255))
    card.paste(photo.resize((pw, ph), Image.LANCZOS), (border, border))
    mask = Image.new("L", (cw, ch), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, cw - 1, ch - 1], radius=radius, fill=255)
    card.putalpha(mask)
    out = Image.new("RGBA", (cw + 2 * pad, ch + 2 * pad + off), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), (pad, pad + off), mask)
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(14)))
    out.alpha_composite(card, (pad, pad))
    return out


def money_graphic(bg):
    """A big dollar sign for money stories (purses, contracts, bonuses)."""
    if is_light(bg):
        fill, stroke = (22, 120, 64), (8, 48, 24)
    else:
        fill, stroke = (255, 204, 30), (120, 84, 0)
    f = font(1000)
    l, t, r, b = f.getbbox("$", stroke_width=26)
    w, h = r - l + 80, b - t + 80
    glyph = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(glyph).text((40 - l, 40 - t), "$", font=f, fill=fill,
                               stroke_width=26, stroke_fill=stroke)
    out = Image.new("RGBA", (w + 40, h + 40), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 120), (20, 34), glyph.getchannel("A"))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(16)))
    out.alpha_composite(glyph, (20, 14))
    return out


def mystery_graphic(bg):
    """A faceless head-and-shoulders silhouette with a big question mark on it.

    Stand-in for a fighter we have no photo of (late replacements, newcomers),
    until the fighter image bank exists."""
    S = 2  # draw at 2x, then downsample for smooth edges
    W, H = 900 * S, 1000 * S
    dark_bg = sum(bg) < 120
    body = (225, 225, 225) if dark_bg else (18, 18, 18)
    mark = (17, 17, 17) if dark_bg else (255, 255, 255)
    g = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(g)
    cx = W // 2
    # shoulders and chest: broad, with rounded shoulder corners, cut off at the bottom
    d.rounded_rectangle([cx - 420 * S, 590 * S, cx + 420 * S, 1300 * S], radius=230 * S, fill=body)
    # neck
    d.rounded_rectangle([cx - 85 * S, 440 * S, cx + 85 * S, 640 * S], radius=40 * S, fill=body)
    # head
    d.ellipse([cx - 190 * S, 40 * S, cx + 190 * S, 500 * S], fill=body)
    # question mark centered on the head
    f = font(360 * S)
    l, t, r, b = f.getbbox("?")
    d.text((cx - (l + r) // 2, 270 * S - (t + b) // 2), "?", font=f, fill=mark)
    g = g.resize((W // S, H // S), Image.LANCZOS)
    out = Image.new("RGBA", (g.width + 40, g.height + 40), (0, 0, 0, 0))
    shadow = Image.new("RGBA", out.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 110), (20, 34), g.getchannel("A"))
    out.alpha_composite(shadow.filter(ImageFilter.GaussianBlur(16)))
    out.alpha_composite(g, (20, 14))
    return out


GRAPHICS = {"money": money_graphic, "mystery": mystery_graphic}


class Scene:
    """Everything needed to draw one post in one layout.

    kind:
      "fighter"  transparent cutout, as big as possible, may run off the bottom
      "card"     a photo (flag, venue) shown as a framed card under the headline
      "graphic"  a drawn graphic (money sign, mystery silhouette), centered under the headline
      "none"     headline only, set larger and centered
    """

    def __init__(self, L, words, bg, cut=None, kind="fighter", graphic="money"):
        self.L, self.words, self.bg, self.kind = L, words, bg, kind
        self.light = is_light(bg)
        self.fg = (17, 17, 17) if self.light else (255, 255, 255)
        self.size, self.baselines = layout_headline(words, L, centered=(kind == "none"))
        self.words_layer = Image.new("RGBA", (L.w, L.h), (0, 0, 0, 0))
        draw_words(ImageDraw.Draw(self.words_layer), L, words, self.size, self.baselines, self.fg)
        self.tag_layer = Image.new("RGBA", (L.w, L.h), (0, 0, 0, 0))
        draw_tag(ImageDraw.Draw(self.tag_layer), L, self.fg, bg, self.light)
        self.text = self.words_layer.copy()
        self.text.alpha_composite(self.tag_layer)
        self.cut = None
        if kind == "fighter":
            self.cut = cut
            self.scale, self.x, self.y = place_fighter(
                L, cut, text_bottoms(L, words, self.size, self.baselines))
        elif kind in ("card", "graphic"):
            top = int(text_bottoms(L, words, self.size, self.baselines).max()) + MARGIN
            room_h = (L.h - L.bottom_safe) - top
            if kind == "card":
                sub = photo_card(cut, 980, room_h)
            else:
                sub = GRAPHICS[graphic](bg)
                s = min(900 / sub.width, room_h / sub.height)
                sub = sub.resize((max(1, int(sub.width * s)), max(1, int(sub.height * s))),
                                 Image.LANCZOS)
            self.cut, self.scale = sub, 1.0
            self.x = (L.w - sub.width) // 2
            self.y = top + (room_h - sub.height) // 2

    def subject_mask(self):
        """Where the subject is painted at full size (zoom 1)."""
        mask = Image.new("L", (self.L.w, self.L.h), 0)
        if self.cut is not None:
            w2 = round(self.cut.width * self.scale)
            h2 = round(self.cut.height * self.scale)
            a = self.cut.getchannel("A").resize((max(1, w2), max(1, h2)), Image.BILINEAR)
            mask.paste(a, (self.x, self.y))
        return np.asarray(mask) > 40

    def alt_words(self, text):
        """A layer with `text` set in the headline's place (for the Reel's
        question and follow cards): no taller than the headline block and
        shrunk until it clears the subject by MARGIN."""
        words = [w.upper() for w in text.split()]
        n = len(words)
        ratio = cap_height(100) / 100
        block = cap_height(self.size) * (len(self.words) + (len(self.words) - 1) * LEAD)
        size = min(340.0, block / (ratio * (n + (n - 1) * LEAD)))
        for w in words:
            width = font(size).getlength(w)
            if width > MAX_TEXT_W:
                size = min(size, size * MAX_TEXT_W / width)
        subj = self.subject_mask()
        while True:
            cap = cap_height(size)
            total = cap * (n + (n - 1) * LEAD)
            top = self.L.top_y + (block - total) / 2  # centered in the headline's block
            baselines = [top + cap + i * cap * (1 + LEAD) for i in range(n)]
            layer = Image.new("RGBA", (self.L.w, self.L.h), (0, 0, 0, 0))
            draw_words(ImageDraw.Draw(layer), self.L, words, size, baselines, self.fg)
            a = np.asarray(layer.getchannel("A")) > 20
            # grow the text mask by MARGIN downward and check it against the subject
            grown = a.copy()
            for d in range(1, MARGIN + 1):
                grown[d:] |= a[:-d]
            if not (grown & subj).any() or size < 40:
                return layer
            size *= 0.94

    def frame(self, zoom=1.0, text_alpha=1.0, alt=None, alt_alpha=0.0):
        """Draw the post. zoom < 1 shrinks the subject: a fighter toward his
        bottom edge, a card or graphic toward its center, so the subject only
        ever moves away from the headline."""
        L = self.L
        img = Image.new("RGBA", (L.w, L.h), self.bg + (255,))
        if self.cut is not None:
            s = self.scale * zoom
            w2, h2 = max(1, round(self.cut.width * s)), max(1, round(self.cut.height * s))
            full_w = round(self.cut.width * self.scale)
            full_h = round(self.cut.height * self.scale)
            sub = self.cut.resize((w2, h2), Image.LANCZOS)
            x = self.x + (full_w - w2) // 2
            if self.kind == "fighter":
                y = self.y + (full_h - h2)  # keep the bottom edge fixed
            else:
                y = self.y + (full_h - h2) // 2  # keep the center fixed
            img.paste(sub, (x, y), sub)
        def put(layer, a):
            if a >= 1:
                img.alpha_composite(layer)
            elif a > 0:
                t = layer.copy()
                t.putalpha(t.getchannel("A").point(lambda v: int(v * a)))
                img.alpha_composite(t)
        if alt is None or alt_alpha <= 0:
            put(self.text, text_alpha)
        else:
            put(self.tag_layer, text_alpha)
            put(self.words_layer, text_alpha * (1 - alt_alpha))
            put(alt, alt_alpha)
        return img.convert("RGB")


def ease_out(t):
    return 1 - (1 - t) ** 3


FOLLOW_TEXT = "Follow @wwitmma"


def make_reel(scene, out, spec):
    """Write reel.mp4: the fighter slowly pushes in, headline punches in,
    with the music track (or silence) underneath."""
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to make a Reel")
    seconds = float(spec.get("seconds", 8))
    frames = int(seconds * FPS)
    music = spec.get("music")
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{scene.L.w}x{scene.L.h}",
           "-r", str(FPS), "-i", "-"]
    if music:
        track = ROOT / music
        if not track.exists():
            sys.exit(f"music file not found: {music}")
        start = float(spec.get("music_start", 0))
        cmd += ["-ss", str(start), "-t", str(seconds), "-i", str(track)]
        fade_out = max(0.0, seconds - 1.2)
        cmd += ["-af", f"afade=t=in:d=0.3,afade=t=out:st={fade_out}:d=1.2"]
    else:
        cmd += ["-f", "lavfi", "-t", str(seconds), "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-map", "0:v", "-map", "1:a", "-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100",
            str(out / "reel.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    punch = int(0.35 * FPS)  # headline fades/punches in over the first moment
    # Text cards that replace the headline later in the Reel: the question
    # (from 2.5 s) and the follow card (last 1.2 s). The headline returns when
    # the Reel loops.
    cards = []
    if spec.get("question"):
        cards.append((int(min(2.5, seconds * 0.42) * FPS), scene.alt_words(spec["question"])))
    if spec.get("follow_card"):
        cards.append((frames - int(1.2 * FPS), scene.alt_words(FOLLOW_TEXT)))
    fade = max(1, int(0.2 * FPS))
    for i in range(frames):
        t = i / max(1, frames - 1)
        zoom = 0.93 + 0.07 * ease_out(t)
        text_alpha = min(1.0, (i + 1) / punch)
        alt, alt_alpha, prev = None, 0.0, None
        for start, layer in cards:
            if i >= start:
                prev, alt = alt, layer
                alt_alpha = min(1.0, (i - start + 1) / fade)
        if prev is not None and alt_alpha < 1:
            # crossfade question -> follow card
            img = Image.blend(scene.frame(zoom, text_alpha, prev, 1.0),
                              scene.frame(zoom, text_alpha, alt, 1.0), alt_alpha)
        else:
            img = scene.frame(zoom, text_alpha, alt, alt_alpha)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed to write the Reel")
    scene.frame(1.0, 1.0).save(out / "cover.png", optimize=True)


def photo_credit(folder, cut_name):
    if not (folder / "credits.json").exists():
        return None
    credits = json.loads((folder / "credits.json").read_text())
    stem = Path(cut_name).stem
    for c in credits:
        if Path(c["file"]).stem == stem:
            return f"{c['author']} / {c['license']}" if c.get("license") else c["author"]
    return None


def legacy_subject(spec):
    """Old post files name a "fighter"; turn that into a subject."""
    folder = ROOT / "images" / slugify(spec["fighter"])
    cutouts = sorted((folder / "cutouts").glob("*.png"))
    if not cutouts:
        sys.exit(f"no cutouts for {spec['fighter']}; fetch them first")
    pick = int(spec.get("photo", 1))
    cut_path = cutouts[min(max(pick, 1), len(cutouts)) - 1]
    return {"kind": "fighter", "image": str(cut_path.relative_to(ROOT)),
            "credit": photo_credit(folder, cut_path.name)}


def render(spec_path):
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text())
    words = [w.upper() for w in spec["headline"].split()]
    if not 1 <= len(words) <= 3:
        sys.exit(f"{spec_path.name}: headline must be 1 to 3 words")
    subject = spec.get("subject") or legacy_subject(spec)
    kind = subject["kind"]
    bg = hex_rgb(spec.get("color", DEFAULT_COLOR))

    name = spec_path.stem
    out = ROOT / "posts" / name
    out.mkdir(parents=True, exist_ok=True)

    cut = None
    if subject.get("image"):
        with Image.open(ROOT / subject["image"]) as im:
            cut = im.convert("RGBA")
    graphic = subject.get("graphic", "money")
    Scene(POST, words, bg, cut, kind, graphic).frame().save(out / "post.png", optimize=True)
    print(f"Rendered posts/{name}/post.png ({kind})")
    if spec.get("reel"):
        make_reel(Scene(REEL, words, bg, cut, kind, graphic), out, spec)
        print(f"Rendered posts/{name}/reel.mp4")

    lines = [spec["caption"].strip(), ""]
    if spec.get("sources"):
        lines.append("📰 Source: " + ", ".join(spec["sources"]))
    if subject.get("credit"):
        lines.append(("📸 Photo: " if kind == "fighter" else "📸 Image: ") + subject["credit"])
    if spec.get("reel") and spec.get("music_credit"):
        lines.append("🎵 Music: " + spec["music_credit"])
    tags = [t if t.startswith("#") else "#" + t for t in spec.get("hashtags", [])][:5]
    if tags:
        lines += ["", " ".join(tags)]
    caption = "\n".join(lines).strip() + "\n"
    if len(caption) > 2200:
        sys.exit(f"{spec_path.name}: caption is {len(caption)} characters; Instagram's limit is 2200")
    (out / "caption.txt").write_text(caption)
    (out / "post.json").write_text(json.dumps({**spec, "subject": subject}, indent=2,
                                              ensure_ascii=False) + "\n")
    return out


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    for arg in sys.argv[1:]:
        render(arg)
