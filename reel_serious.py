#!/usr/bin/env python3
"""Reel format "serious": a calm, respectful news Reel for hard stories.

Added Oct 9 at the user's request, for stories where the punchy v2 format
(boom, shake, color bursts, "YOUR PICK" card) would be in poor taste:
someone hurt or killed, a serious illness, an arrest, a death in the sport.
It reports the news plainly and ends on a respectful note.

Three quiet beats, about 10.5 seconds, no poll, no follow card:
  1. Headline (0-3.8 s): the person's photo, muted (mostly desaturated) on a
     dark ground with a soft vignette, a slow push-in, a small kicker
     ("REPORTED") and a plain headline sentence.
  2. Facts (3.8-7.8 s): the photo dims and 2-4 short facts fade in one by
     one, each with a thin rule beside it.
  3. Closing (7.8 s-end): a centered line such as "Wishing Tim Kennedy a
     full recovery", an optional second line, then the sources.

No sound effects. The audio is a soft, low synthesized pad (no credit
needed); a post can name a track with "music" instead, played quietly.

Post file:

    "format": "serious",
    "visual": [{"type": "fighter", "name": "Tim Kennedy"}],   # the person (as usual)
    "serious": {
      "tag": "NEWS UPDATE",            # top-right label (default NEWS UPDATE)
      "kicker": "REPORTED",            # small line over the headline
      "title": "Tim Kennedy wounded in Congo ambush",   # plain sentence, 3-8 words
      "facts": ["...", "...", "..."],  # 2-4 short own-words facts
      "closing": "Wishing Tim Kennedy a full recovery.",
      "closing_sub": "Our thoughts are with the family of ...",   # optional
      "seconds": 10.5                  # optional
    }

The photo is the post's resolved "subject" (from "visual"). Output:
reel.mp4 and cover.png (a headline frame).
"""

import math
import shutil
import subprocess
import sys
import wave
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter

from reel_v2 import (FPS, H, W, barlow, cap, draw_spaced, fit_lines, spaced_width, wrap,
                     silhouette)

ROOT = Path(__file__).resolve().parent
SECONDS = 10.5
T_FACTS, T_CLOSE = 3.8, 7.8

BG = (13, 14, 17)
WHITE = (244, 245, 247)
SOFT = (196, 200, 208)
MUTED = (140, 146, 156)
RULE = (150, 162, 182)          # quiet slate blue, the only "accent"
PAD_L, PAD_R = 72, 128          # right gutter keeps clear of Instagram's buttons
PHOTO_TOP, PHOTO_H = 150, 1150


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)  # smoothstep: no overshoot, nothing snaps


def fade(layer, a):
    if a >= 0.999:
        return layer
    out = layer.copy()
    out.putalpha(out.getchannel("A").point(lambda v: int(v * max(0.0, a))))
    return out


def muted(cut, keep=0.28):
    """Mostly desaturated, slightly darker: respectful, not black-and-white
    (which reads as a memorial)."""
    rgb = ImageEnhance.Color(cut.convert("RGB")).enhance(keep)
    rgb = ImageEnhance.Brightness(rgb).enhance(0.9)
    rgb = ImageEnhance.Contrast(rgb).enhance(0.95)
    out = rgb.convert("RGBA")
    out.putalpha(cut.getchannel("A"))
    return out


def fit_person(cut, box_w, box_h):
    bbox = cut.getbbox() or (0, 0, cut.width, cut.height)
    cut = cut.crop(bbox)
    s = min(box_h * 0.92 / cut.height, box_w * 0.95 / cut.width)
    return cut.resize((max(1, int(cut.width * s)), max(1, int(cut.height * s))), Image.LANCZOS)


class Serious:
    def __init__(self, spec, cut):
        s = spec.get("serious") or {}
        self.tag = (s.get("tag") or "NEWS UPDATE").upper()
        self.kicker = (s.get("kicker") or "").upper()
        self.title = s.get("title") or spec["headline"]
        self.facts = [f for f in s.get("facts", [])][:4]
        self.closing = s.get("closing", "")
        self.closing_sub = s.get("closing_sub", "")
        src = ", ".join(spec.get("sources", []))
        self.source = f"Source: {src}" if src else ""

        person = muted(cut) if cut is not None else silhouette(W, PHOTO_H)
        self.person = fit_person(person, W, PHOTO_H)
        self.ground = self._ground()
        self.header = self._header()
        self.title_layer = self._title_layer()
        self.fact_layers = self._fact_layers()
        self.close_layer = self._close_layer()

    # ---- static layers ------------------------------------------------

    def _ground(self):
        """Dark ground with a faint cool glow behind the person."""
        img = Image.new("RGBA", (W, H), BG + (255,))
        glow = Image.radial_gradient("L").resize((W * 2, H * 2))
        glow = glow.crop((W // 2, int(H * 0.68), W // 2 + W, int(H * 0.68) + H))
        tint = Image.new("RGBA", (W, H), (44, 50, 62, 255))
        tint.putalpha(glow.point(lambda v: int((255 - v) * 0.85)))
        img.alpha_composite(tint)
        return img

    def _header(self):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        top, bh = 60, 64
        f_box = barlow(40, 800)
        box = "WWIT"
        bw = int(spaced_width(box, f_box, 3)) + 36
        d.rectangle([PAD_L, top, PAD_L + bw, top + bh], fill=WHITE)
        draw_spaced(d, (PAD_L + 18, top + bh / 2 + cap(f_box) / 2), box, f_box, BG, 3)
        f_lab = barlow(36, 600)
        draw_spaced(d, (PAD_L + bw + 16, top + bh / 2 + cap(f_lab) / 2), "MMA NEWS", f_lab, SOFT, 6)
        f_tag = barlow(30, 600)
        tw = spaced_width(self.tag, f_tag, 5)
        right = W - PAD_R
        draw_spaced(d, (right - tw, top + bh / 2 + cap(f_tag) / 2), self.tag, f_tag, MUTED, 5)
        d.rectangle([right - tw, top + bh / 2 + cap(f_tag) / 2 + 12, right, top + bh / 2 + cap(f_tag) / 2 + 14],
                    fill=RULE)
        return layer

    def _title_layer(self):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        max_w = W - PAD_L - PAD_R
        f, lines, size = fit_lines(self.title.upper(), lambda s: barlow(s, 700), 104, max_w, 3)
        lh = size * 1.04
        block = cap(f) + lh * (len(lines) - 1)
        y = 1660 - block                       # headline block ends at y=1660
        if self.kicker:
            fk = barlow(40, 600)
            ky = y - 56
            d.rectangle([PAD_L, ky - cap(fk) / 2 - 2, PAD_L + 40, ky - cap(fk) / 2 + 2], fill=RULE)
            draw_spaced(d, (PAD_L + 56, ky), self.kicker, fk, RULE, 6)
        y += cap(f)
        for line in lines:
            d.text((PAD_L, y), line, font=f, fill=WHITE, anchor="ls")
            y += lh
        return layer

    def _fact_layers(self):
        max_w = W - PAD_L - PAD_R - 40
        f = barlow(58, 600)
        lh = 70
        blocks = []
        for fact in self.facts:
            lines = wrap(fact, f, max_w)[:3]
            blocks.append(lines)
        gap = 54
        total = sum(cap(f) + lh * (len(b) - 1) for b in blocks) + gap * (len(blocks) - 1)
        y = max(820, 1640 - total)
        layers = []
        for lines in blocks:
            layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            d = ImageDraw.Draw(layer)
            h = cap(f) + lh * (len(lines) - 1)
            d.rectangle([PAD_L, y - 4, PAD_L + 4, y + h + 10], fill=RULE)
            yy = y + cap(f)
            for line in lines:
                d.text((PAD_L + 40, yy), line, font=f, fill=WHITE, anchor="ls")
                yy += lh
            layers.append(layer)
            y += h + gap
        return layers

    def _close_layer(self):
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(layer)
        max_w = W - 2 * 120
        cx = W // 2 - (PAD_R - PAD_L) // 2      # optical center, clear of the side buttons
        y = 860
        if self.closing:
            fc, lines, size = fit_lines(self.closing, lambda s: barlow(s, 600), 80, max_w, 3)
            lh = size * 1.12
            y += cap(fc)
            for line in lines:
                d.text((cx, y), line, font=fc, fill=WHITE, anchor="ms")
                y += lh
            y += 10
        if self.closing_sub:
            y += 40
            d.rectangle([cx - 30, y - 2, cx + 30, y + 1], fill=RULE)
            y += 60
            fs = barlow(50, 600)
            for line in wrap(self.closing_sub, fs, max_w)[:3]:
                y += cap(fs)
                d.text((cx, y), line, font=fs, fill=SOFT, anchor="ms")
                y += 18
        fsrc = barlow(34, 600)
        yb = 1600
        for line in wrap(self.source, fsrc, max_w)[:2]:
            d.text((cx, yb), line, font=fsrc, fill=MUTED, anchor="ms")
            yb += 46
        f_h = barlow(34, 600)
        draw_spaced(d, (cx - spaced_width("@WWITMMA", f_h, 6) / 2, yb + 20), "@WWITMMA", f_h, MUTED, 6)
        return layer

    # ---- frames -------------------------------------------------------

    def photo(self, t):
        """The person, slowly pushing in (100 -> 105 %) over the whole Reel,
        with the bottom fading into the ground so the text sits on dark."""
        img = self.ground.copy()
        z = 1.0 + 0.05 * (t / SECONDS)
        p = self.person
        pw, ph = int(p.width * z), int(p.height * z)
        p = p.resize((pw, ph), Image.BILINEAR)
        x = (W - pw) // 2 - (PAD_R - PAD_L) // 4
        y = PHOTO_TOP + PHOTO_H - ph
        img.alpha_composite(p, (x, y))
        # fade the lower part of the photo into the ground
        grad = Image.linear_gradient("L").resize((W, 760))
        shade = Image.new("RGBA", (W, 760), BG + (255,))
        shade.putalpha(grad.point(lambda v: int(min(255, v * 1.15))))
        img.alpha_composite(shade, (0, PHOTO_TOP + PHOTO_H - 600))
        img.paste(Image.new("RGBA", (W, H - (PHOTO_TOP + PHOTO_H + 160)), BG + (255,)),
                  (0, PHOTO_TOP + PHOTO_H + 160))
        # soft vignette at the top edge
        top = Image.linear_gradient("L").rotate(180).resize((W, 260))
        tshade = Image.new("RGBA", (W, 260), BG + (255,))
        tshade.putalpha(top.point(lambda v: int(v * 0.85)))
        img.alpha_composite(tshade, (0, 0))
        return img

    def frame(self, t):
        if t >= T_CLOSE:
            img = self.ground.copy()
            # the photo lingers faintly behind the closing line, then settles
            k = ease((t - T_CLOSE) / 0.8)
            ph = self.photo(t)
            dim = Image.new("RGBA", (W, H), BG + (int(255 * (0.55 + 0.33 * k)),))
            ph.alpha_composite(dim)
            img = ph
            img.alpha_composite(self.header)
            img.alpha_composite(fade(self.close_layer, ease((t - T_CLOSE - 0.15) / 0.7)))
            return self._edges(img, t).convert("RGB")
        img = self.photo(t)
        if t >= T_FACTS:
            u = ease((t - T_FACTS) / 0.7)
            img.alpha_composite(Image.new("RGBA", (W, H), BG + (int(255 * 0.55 * u),)))
        img.alpha_composite(self.header)
        if t < T_FACTS + 0.5:
            a_in = 0.55 + 0.45 * ease(t / 0.6)              # visible from frame 1
            a_out = 1 - ease((t - T_FACTS) / 0.5)
            img.alpha_composite(fade(self.title_layer, min(a_in, a_out)))
        if t >= T_FACTS + 0.3:
            for i, layer in enumerate(self.fact_layers):
                t0 = T_FACTS + 0.3 + i * 0.75
                a = ease((t - t0) / 0.6)
                if t >= T_CLOSE - 0.5:
                    a *= 1 - ease((t - (T_CLOSE - 0.5)) / 0.5)
                if a > 0:
                    rise = int(18 * (1 - a))
                    moved = Image.new("RGBA", (W, H), (0, 0, 0, 0))
                    moved.alpha_composite(layer, (0, rise))
                    img.alpha_composite(fade(moved, a))
        return self._edges(img, t).convert("RGB")

    def _edges(self, img, t):
        """Gentle fade to black over the last 0.5 s so the loop is soft."""
        tail = SECONDS - t
        if tail < 0.5:
            img = img.copy()
            img.alpha_composite(Image.new("RGBA", (W, H), BG + (int(255 * ease(1 - tail / 0.5)),)))
        return img


def write_pad(path, seconds, sr=44100):
    """A soft, low pad: an open fifth with an octave, slowly breathing.
    Neutral rather than sad, quiet enough to sit under a news read."""
    import numpy as np
    n = int(seconds * sr)
    t = np.arange(n) / sr
    out = np.zeros(n)
    for f, g in ((110.0, 0.5), (164.81, 0.32), (220.0, 0.22), (329.63, 0.08)):
        for det in (-0.25, 0.25):
            out += g * np.sin(2 * np.pi * (f + det) * t + f)
    out *= 0.8 + 0.2 * np.sin(2 * np.pi * 0.18 * t)          # slow swell
    env = np.minimum(1.0, t / 1.5) * np.minimum(1.0, (seconds - t) / 1.8)
    out *= env
    pcm = (out / (np.abs(out).max() or 1.0) * 0.30 * 32767).astype("<i2")  # about -10 dBFS peak
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm.tobytes())


def make_reel_serious(spec, out, cut):
    global SECONDS
    if not shutil.which("ffmpeg"):
        sys.exit("ffmpeg is needed to make a Reel")
    SECONDS = float((spec.get("serious") or {}).get("seconds", 10.5))
    frames = int(SECONDS * FPS)
    v = Serious(spec, cut)
    cmd = ["ffmpeg", "-y", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    music = spec.get("music")
    if music:
        track = ROOT / music
        if not track.exists():
            sys.exit(f"music file not found: {music}")
        cmd += ["-ss", str(float(spec.get("music_start", 0))), "-t", str(SECONDS), "-i", str(track),
                "-af", f"volume=0.45,afade=t=in:d=1.0,afade=t=out:st={max(0.0, SECONDS - 1.8)}:d=1.8"]
    else:
        pad = out / "_pad.wav"
        write_pad(pad, SECONDS)
        cmd += ["-i", str(pad), "-af", "aformat=sample_rates=44100:channel_layouts=stereo"]
    cmd += ["-map", "0:v", "-map", "1:a", "-shortest",
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            "-profile:v", "high", "-movflags", "+faststart",
            "-c:a", "aac", "-b:a", "192k", "-ar", "44100", str(out / "reel.mp4")]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(frames):
        proc.stdin.write(v.frame(i / FPS).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg failed to write the serious Reel")
    (out / "_pad.wav").unlink(missing_ok=True)
    v.frame(1.5).save(out / "cover.png", optimize=True)
    return v
