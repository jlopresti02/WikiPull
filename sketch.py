#!/usr/bin/env python3
"""Sketch Reels: turn a fight clip into a hand-drawn "breakdown" animation.

Added Oct 11 at the user's request, modelled on the rotoscoped technique
breakdowns some MMA accounts post: the fighters are redrawn as white figures
with black ink outlines, flat black hair/shorts/gloves and flat colour where
the gear is colourful, on a plain white ground; the crowd, cage and arena
disappear. Around the animation sits the WWIT frame: a dark header band, a
white sketch panel, and big captions underneath that change phrase by phrase,
with key words in the accent colour.

Everything runs on CPU in GitHub Actions, no paid API:
  1. ffmpeg decodes the clip (optionally trimmed) at a low, cartoon-like
     frame rate (12 fps by default; the "on twos" look also hides flicker).
  2. A human-segmentation model (u2net_human_seg, the same family rembg
     uses) finds the people; only the biggest few blobs are kept (the two
     fighters by default), so the crowd and the cage go away.
  3. Each fighter is flattened into ink: an outer contour, inner lines from
     an XDoG edge filter, and flat fills (dark -> black, vivid -> colour,
     everything else -> white).
  4. The frames are framed into the 1080x1920 Reel with header and captions,
     and music (or the clip's own audio) is laid under it.

Post file (posts/queue/<name>.json), on top of the usual fields:

    "format": "sketch",
    "headline": "Distance",                  # 1-3 words, used for post.png
    "visual": [{"type": "text"}],
    "sketch": {
      "video": "drive:1AbC...",               # Drive file id, a Drive share link,
                                               # a repo path (sketch/input/clip.mp4)
                                               # or a direct https link to a video
      "start": 12.5, "end": 18.0,             # optional trim, in seconds
      "title": "VOLK VS HOLLOWAY",            # optional: line under the logo
      "tag": "UFC 276",                       # optional: box at top right
      "captions": [                           # phrase by phrase; *word* = accent
        "Volkanovski creates the *distance*.",
        "Holloway is forced to *close*.",
        {"text": "And walks into the *jab*.", "start": 4.2}
      ],
      "fighters": 2,                          # how many people to keep (1-3)
      "fps": 12,                              # animation frame rate
      "accent": "#FFC21A",                    # caption highlight colour
      "audio": "music",                       # "music" (pool), "original" or "none"
      "colors": true,                         # keep flat colour on gear
      "mirror": false                         # flip left/right
    },
    "footage_credit": "UFC",                  # shown as "🎥 Footage: ..." in the caption
    "music_pool": "espn"

Captions without a "start" share the clip's length evenly. The finished Reel
is posts/<name>/reel.mp4 with cover.png, exactly like the other formats, so
it is scheduled the same way.

Run by hand: python sketch.py <clip.mp4> [--out dir] [--start s] [--end s]
    [--caption "First *line*." --caption "Second line."]
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

import cv2

ROOT = Path(__file__).resolve().parent
W, H, OUT_FPS = 1080, 1920, 30

# layout (px, 1080x1920)
HEADER_H = 300          # dark band with the WWIT logo (clears Instagram's top bar)
PANEL_Y0, PANEL_Y1 = 300, 1330
CAPTION_Y = 1365        # captions start here; Instagram's UI covers ~1500+ only partly
BAND = (11, 11, 13)
INK = (11, 11, 13)
WHITE = (255, 255, 255)
PAPER = (255, 255, 255)
DEFAULT_ACCENT = "#FFC21A"

MODEL_URL = "https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net_human_seg.onnx"
MODEL_DIR = Path(os.environ.get("U2NET_HOME", Path.home() / ".u2net"))
MODEL_PATH = MODEL_DIR / "u2net_human_seg.onnx"
PROC_W = 640            # processing width for segmentation/stylizing


# ----------------------------------------------------------------- input ---

def resolve_video(src, workdir):
    """Return a local path for "drive:<id>", a Drive link, a repo path or a URL."""
    src = str(src).strip()
    m = re.search(r"(?:drive:|/d/|[?&]id=)([A-Za-z0-9_-]{20,})", src)
    if src.startswith("drive:") or ("drive.google.com" in src and m):
        fid = m.group(1)
        dest = Path(workdir) / f"drive-{fid}.mp4"
        url = f"https://drive.usercontent.google.com/download?id={fid}&export=download&confirm=t"
        _download(url, dest)
        if dest.stat().st_size < 50_000 or dest.read_bytes()[:15].lower().startswith(b"<!doctype html"):
            raise RuntimeError(f"Drive file {fid} didn't download as a video; "
                               "is the folder shared as 'anyone with the link can view'?")
        print(f"sketch: downloaded Drive video {fid} ({dest.stat().st_size // 1024} KB)")
        return dest
    if src.startswith("http://") or src.startswith("https://"):
        dest = Path(workdir) / ("url-" + re.sub(r"[^A-Za-z0-9.]+", "-", src.split("/")[-1])[:60] or "clip.mp4")
        _download(src, dest)
        return dest
    p = Path(src)
    if not p.is_absolute():
        p = ROOT / p
    if not p.exists():
        raise RuntimeError(f"video not found: {src}")
    return p


def _download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "WikiPull/1.0 (+https://github.com/jlopresti02/WikiPull)"})
    with urllib.request.urlopen(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def probe(path):
    """(width, height, duration) as displayed, i.e. after rotation metadata
    (phone screen recordings of a landscape video are often stored rotated)."""
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height:stream_side_data=rotation:stream_tags=rotate:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    j = json.loads(out)
    s = j["streams"][0]
    w, h = int(s["width"]), int(s["height"])
    rot = 0
    for sd in s.get("side_data_list", []) or []:
        if "rotation" in sd:
            rot = int(float(sd["rotation"]))
    rot = rot or int(float((s.get("tags") or {}).get("rotate", 0) or 0))
    if abs(rot) % 180 == 90:
        w, h = h, w
    return w, h, float(j["format"]["duration"])


def has_audio(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries",
                          "stream=index", "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


def read_frames(path, fps, start=None, end=None, proc_w=PROC_W, crop=None, out_h=None):
    """Decode the clip at `fps` as RGB arrays, proc_w wide. `crop` = (x0, y0, x1, y1)
    in source pixels (may reach outside the frame; the outside is white)."""
    w, h, dur = probe(path)
    vf = [f"fps={fps}"]
    if crop:
        x0, y0, x1, y1 = (int(round(v)) for v in crop)
        pl, pt = max(0, -x0), max(0, -y0)
        pr, pb = max(0, x1 - w), max(0, y1 - h)
        if pl or pt or pr or pb:
            vf.append(f"pad={w + pl + pr}:{h + pt + pb}:{pl}:{pt}:color=white")
        vf.append(f"crop={x1 - x0}:{y1 - y0}:{x0 + pl}:{y0 + pt}")
        cw, ch = x1 - x0, y1 - y0
    else:
        cw, ch = w, h
    ph = out_h or int(round(ch * proc_w / cw / 2)) * 2
    vf.append(f"scale={proc_w}:{ph}:flags=lanczos")
    cmd = ["ffmpeg", "-v", "error"]
    if start:
        cmd += ["-ss", str(start)]
    cmd += ["-i", str(path)]
    if end:
        cmd += ["-t", str(max(0.2, end - (start or 0)))]
    cmd += ["-vf", ",".join(vf), "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    n = len(raw) // (proc_w * ph * 3)
    if not n:
        raise RuntimeError("no frames decoded (check start/end)")
    return np.frombuffer(raw[: n * proc_w * ph * 3], np.uint8).reshape(n, ph, proc_w, 3)


# ----------------------------------------------------------- segmentation ---

class Segmenter:
    def __init__(self):
        import onnxruntime as ort
        if not MODEL_PATH.exists():
            MODEL_DIR.mkdir(parents=True, exist_ok=True)
            print("sketch: downloading u2net_human_seg model")
            _download(MODEL_URL, MODEL_PATH)
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = os.cpu_count() or 2
        self.sess = ort.InferenceSession(str(MODEL_PATH), opts, providers=["CPUExecutionProvider"])
        self.inp = self.sess.get_inputs()[0].name

    def __call__(self, rgb):
        h, w = rgb.shape[:2]
        x = cv2.resize(rgb, (320, 320), interpolation=cv2.INTER_AREA).astype(np.float32) / 255.0
        x = x / max(x.max(), 1e-6)
        x = (x - (0.485, 0.456, 0.406)) / (0.229, 0.224, 0.225)
        x = x.transpose(2, 0, 1)[None].astype(np.float32)
        pred = self.sess.run(None, {self.inp: x})[0][0, 0]
        pred = (pred - pred.min()) / max(pred.max() - pred.min(), 1e-6)
        return cv2.resize(pred, (w, h), interpolation=cv2.INTER_LINEAR)


class PersonDetector:
    """YOLO instance segmentation (ultralytics), used to pick the fighters:
    every person gets their own mask, so the crowd, the referee and the cage
    can be told apart from the two people we want."""

    def __init__(self, model=None):
        from ultralytics import YOLO
        self.model = YOLO(model or os.environ.get("SKETCH_YOLO", "yolo11s-seg.pt"))

    def people(self, rgb):
        """[(mask bool HxW, box (x0,y0,x1,y1), conf)] for each person."""
        h, w = rgb.shape[:2]
        r = self.model.predict(rgb[..., ::-1], imgsz=640, conf=0.35, classes=[0], verbose=False,
                               retina_masks=False)[0]
        out = []
        if r.masks is None:
            return out
        md = r.masks.data.cpu().numpy()
        for i in range(len(md)):
            m = cv2.resize(md[i], (w, h), interpolation=cv2.INTER_LINEAR) > 0.5
            out.append((m, r.boxes.xyxy[i].cpu().numpy(), float(r.boxes.conf[i])))
        return out


def _iou(a, b):
    x0, y0 = max(a[0], b[0]), max(a[1], b[1])
    x1, y1 = min(a[2], b[2]), min(a[3], b[3])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    ua = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / ua if ua > 0 else 0


def select_fighters(frames, k, det):
    """Per frame, the union mask of the k people most likely to be the
    fighters: big, not in a dark shirt (the referee), and consistent with
    who was picked in the previous frame."""
    sel_masks, prev = [], []
    for i, f in enumerate(frames):
        people = det.people(f)
        v = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)[..., 2]
        scored = []
        for m, box, conf in people:
            area = m.sum()
            if area < 0.004 * m.size:
                continue
            # torso darkness: the referee wears a black shirt, fighters don't
            ys = np.nonzero(m)[0]
            top, bot = ys.min(), ys.max()
            torso = m.copy()
            torso[: int(top + 0.18 * (bot - top))] = False
            torso[int(top + 0.55 * (bot - top)):] = False
            dark = (v[torso] < 70).mean() if torso.any() else 0
            sc = area * conf * (0.2 if dark > 0.55 else 1.0)
            if prev and max(_iou(box, p) for p in prev) > 0.3:
                sc *= 1.6
            scored.append((sc, m, box))
        scored.sort(key=lambda x: -x[0])
        chosen = scored[:k]
        union = np.zeros(f.shape[:2], bool)
        for _, m, _ in chosen:
            union |= m
        sel_masks.append(union)
        prev = [b for _, _, b in chosen] or prev
        if i % 24 == 0:
            print(f"sketch: picked fighters in {i + 1}/{len(frames)} frames ({len(people)} people seen)")
    return np.stack(sel_masks)


def keep_biggest(mask, k, min_frac=0.004, rgb=None):
    """Keep the k most fighter-like blobs (biggest, and not mostly dark: a
    referee in a black shirt scores low), drop the rest."""
    n, lab, stats, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 8)
    if n <= 1:
        return mask.astype(bool)
    areas = stats[1:, cv2.CC_STAT_AREA].astype(float)
    score = areas.copy()
    if rgb is not None:
        v = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 2]
        dark = v < 70
        for i in range(1, n):
            frac = dark[lab == i].mean() if areas[i - 1] else 0
            if frac > 0.5:
                score[i - 1] *= 0.25
    order = np.argsort(score)[::-1]
    keep = [i + 1 for i in order[:k] if areas[i] >= min_frac * mask.size]
    return np.isin(lab, keep)


def fighter_masks(frames, k, seg=None, priors=None, strict=False):
    """Binary fighter masks per frame. `priors` (optional, same shape) limits
    each frame to blobs that overlap the fighters found in a first pass."""
    seg = seg or Segmenter()
    probs = []
    for i, f in enumerate(frames):
        probs.append(seg(f))
        if i % 24 == 0:
            print(f"sketch: segmented {i + 1}/{len(frames)} frames")
    probs = np.stack(probs)
    # light temporal smoothing so outlines don't jump between drawings
    sm = probs.copy()
    for i in range(len(probs)):
        a, b = max(0, i - 1), min(len(probs), i + 2)
        sm[i] = 0.5 * probs[i] + 0.5 * probs[a:b].mean(0)
    masks = []
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    for p in sm:
        m = (p > 0.5).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, kernel)
        m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, kernel, iterations=2)
        if priors is not None:
            g = priors[len(masks)].astype(np.uint8)
            if strict:
                # instance masks from the person detector: only keep the
                # segmenter's pixels near the chosen fighters (no crowd, no
                # cage, no referee); fall back to the detector's own mask
                pr = cv2.dilate(g, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))).astype(bool)
                m = (m.astype(bool) & pr)
                if m.sum() < 0.5 * g.sum():
                    m = cv2.GaussianBlur(g * 255, (0, 0), 3) > 127
                m = m.astype(np.uint8)
            else:
                pr = cv2.dilate(g, np.ones((15, 15), np.uint8)).astype(bool)
                n_, cc_, _, _ = cv2.connectedComponentsWithStats(m, 8)
                hit = np.unique(cc_[pr & (cc_ > 0)])
                m = np.isin(cc_, hit).astype(np.uint8)
        m = keep_biggest(m, k, rgb=frames[len(masks)])
        m = fill_holes(m)
        masks.append(m)
    return np.stack(masks)


def fill_holes(m):
    m = m.astype(np.uint8)
    h, w = m.shape
    flood = m.copy()
    ff = np.zeros((h + 2, w + 2), np.uint8)
    flood_inv = (1 - flood).astype(np.uint8)
    cv2.floodFill(flood_inv, ff, (0, 0), 0)
    return (m | flood_inv).astype(bool)


# ------------------------------------------------------------ stylizing ---

def xdog(gray, sigma=1.1, k=1.6, p=20.0, eps=-0.03, phi=12.0):
    g = gray.astype(np.float32) / 255.0
    g1 = cv2.GaussianBlur(g, (0, 0), sigma)
    g2 = cv2.GaussianBlur(g, (0, 0), sigma * k)
    d = (1 + p) * g1 - p * g2
    e = np.where(d >= eps, 1.0, 1.0 + np.tanh(phi * (d - eps)))
    return e < 0.55  # True = ink


def flat_fills(rgb, mask, colors=True):
    """Label each fighter pixel: 0 white, 1 black, 2 vivid colour, 3 light grey.
    Returns (labels, colour image for label 2)."""
    smooth = cv2.bilateralFilter(rgb, 9, 60, 9)
    hsv = cv2.cvtColor(smooth, cv2.COLOR_RGB2HSV)
    hch, s, v = hsv[..., 0].astype(int), hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    lab = np.zeros(mask.shape, np.uint8)
    dark = (v < 62) | ((v < 85) & (s < 70))
    grey = (s < 45) & (v >= 85) & (v < 150) & ~dark
    lab[grey & mask] = 3
    lab[dark & mask] = 1
    fill = np.zeros_like(rgb)
    if colors:
        # skin, tans and wood/leather tones stay white; only real gear colour fills
        skin = ((hch >= 4) & (hch <= 26)) | (((hch < 4) | (hch >= 172)) & (s < 150))
        vivid = (s > 125) & (v > 80) & ~skin & ~dark
        lab[vivid & mask] = 2
        # snap each colour to a pure, flat version of its own hue
        hh = (np.round(hch / 15.0) * 15) % 180
        flat = np.stack([hh, np.full_like(hh, 215), np.full_like(hh, 225)], -1).astype(np.uint8)
        fill = cv2.cvtColor(flat, cv2.COLOR_HSV2RGB)
    # clean the label map into flat, cartoon-like patches; drop confetti
    min_area = max(30, int(mask.sum() * 0.004))
    for val in (1, 2, 3):
        m = (lab == val).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        m = cv2.medianBlur(m * 255, 7) > 127
        n, cc, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= (min_area if val != 1 else min_area // 3)
        m = keep[cc]
        lab[(lab == val) & ~m] = 0
        lab[m & mask & (lab == 0)] = val
    return lab, fill


def draw_frame(rgb, mask, scale, colors=True, line_px=3):
    """One drawing: white paper, fighters in flat fills with ink lines.
    Rendered at `scale` x the processing size for crisp lines."""
    h, w = mask.shape
    big = (int(w * scale), int(h * scale))
    lab, fill = flat_fills(rgb, mask, colors)
    gray = cv2.cvtColor(rgb, cv2.COLOR_RGB2GRAY)
    gray = cv2.bilateralFilter(gray, 7, 40, 7)
    lines = xdog(gray) & cv2.erode(mask.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
    # drop tiny speckles from the edge map
    n, cc, st, _ = cv2.connectedComponentsWithStats(lines.astype(np.uint8), 8)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 14
    lines = keep[cc]

    up = lambda a, interp=cv2.INTER_NEAREST: cv2.resize(a, big, interpolation=interp)
    canvas = np.full((big[1], big[0], 3), PAPER, np.uint8)
    m_big = up(mask.astype(np.uint8) * 255, cv2.INTER_LINEAR)
    m_big = cv2.GaussianBlur(m_big, (0, 0), 1.2) > 127
    canvas[m_big] = WHITE
    lab_big = up(lab)
    fill_big = up(fill)
    canvas[(lab_big == 1) & m_big] = INK
    sel = (lab_big == 2) & m_big
    canvas[sel] = fill_big[sel]
    canvas[(lab_big == 3) & m_big] = (206, 207, 214)
    # inner lines, slightly thickened, then smoothed
    l_big = up(lines.astype(np.uint8) * 255, cv2.INTER_LINEAR)
    l_big = cv2.GaussianBlur(l_big, (0, 0), 0.8) > 90
    if line_px > 2:
        l_big = cv2.dilate(l_big.astype(np.uint8), np.ones((2, 2), np.uint8)).astype(bool)
    canvas[l_big & m_big] = INK
    # outer contour, drawn as a smooth ink line
    cnts, _ = cv2.findContours(m_big.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    smooth = []
    for c in cnts:
        if cv2.contourArea(c) < 200:
            continue
        smooth.append(cv2.approxPolyDP(c, 1.2, True))
    cv2.drawContours(canvas, smooth, -1, INK, int(line_px * scale / 1.5) + 2, cv2.LINE_AA)
    return canvas


def follow_boxes(masks, aspect, pad=0.12, smooth_s=0.8, fps=12, min_h_frac=0.45):
    """A crop box per frame that follows the fighters like a slow camera:
    the kept blobs' bounding box, gaps filled, smoothed over ~smooth_s
    seconds, padded and widened to the panel's aspect ratio (w/h)."""
    n, h, w = masks.shape
    raw = np.full((n, 4), np.nan)
    for i, m in enumerate(masks):
        ys, xs = np.nonzero(m)
        if len(xs) > 0.002 * m.size:
            raw[i] = (np.percentile(xs, 1), np.percentile(ys, 1), np.percentile(xs, 99), np.percentile(ys, 99))
    ok = ~np.isnan(raw[:, 0])
    if not ok.any():
        return np.tile([0, 0, w, h], (n, 1)).astype(float)
    idx = np.arange(n)
    for c in range(4):
        raw[:, c] = np.interp(idx, idx[ok], raw[ok, c])
    # hold each edge at its widest over ~0.6 s so fast moves stay in frame
    r_ = max(1, int(0.3 * fps))
    held = raw.copy()
    for i in range(n):
        a, b = max(0, i - r_), min(n, i + r_ + 1)
        held[i, 0], held[i, 1] = raw[a:b, 0].min(), raw[a:b, 1].min()
        held[i, 2], held[i, 3] = raw[a:b, 2].max(), raw[a:b, 3].max()
    raw = held
    cx, cy = (raw[:, 0] + raw[:, 2]) / 2, (raw[:, 1] + raw[:, 3]) / 2
    bw, bh = (raw[:, 2] - raw[:, 0]) * (1 + 2 * pad), (raw[:, 3] - raw[:, 1]) * (1 + 2 * pad)
    bh = np.maximum(bh, np.maximum(bw / aspect, min_h_frac * h))
    sig = max(1.0, smooth_s * fps / 2)
    def blur(a):
        r = int(3 * sig)
        k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
        k /= k.sum()
        return np.convolve(np.pad(a, r, mode="edge"), k, mode="valid")
    cx, cy, bh = blur(cx), blur(cy), blur(bh)
    # never crop a fighter off: when they're far apart the box may grow past
    # the frame's height (white above/below), but not much past its width
    bh = np.minimum(bh, w * 1.05 / aspect)
    bw = bh * aspect
    return np.stack([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 1)


def crop_frame(frame, box, out_w, out_h):
    """Crop `box` (may reach outside) from frame, white outside, resized."""
    x0, y0, x1, y1 = box
    sx = out_w / (x1 - x0)
    M = np.array([[sx, 0, -x0 * sx], [0, out_h / (y1 - y0), -y0 * out_h / (y1 - y0)]], np.float32)
    return cv2.warpAffine(frame, M, (out_w, out_h), flags=cv2.INTER_AREA if sx < 1 else cv2.INTER_CUBIC,
                          borderMode=cv2.BORDER_CONSTANT, borderValue=(255, 255, 255))


# --------------------------------------------------------------- framing ---

def _fonts():
    from reel_v2 import anton, barlow, cap, draw_spaced, spaced_width, wrap
    return anton, barlow, cap, draw_spaced, spaced_width, wrap


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def chrome(accent, title=None, tag=None):
    """The fixed frame: header band, panel, caption band (RGB, 1080x1920)."""
    anton, barlow, cap, draw_spaced, spaced_width, _ = _fonts()
    im = Image.new("RGB", (W, H), BAND)
    d = ImageDraw.Draw(im)
    # faint diagonal texture on the bands, like a printed program
    for x in range(-H, W, 22):
        d.line([(x, 0), (x + HEADER_H, HEADER_H)], fill=(20, 20, 24), width=2)
        d.line([(x, PANEL_Y1), (x + (H - PANEL_Y1), H)], fill=(20, 20, 24), width=2)
    # logo
    top, left = 112, 54
    f_box = anton(64)
    bw = int(spaced_width("WWIT", f_box, 2)) + 44
    bh = 96
    d.rectangle([left, top, left + bw, top + bh], fill=accent)
    draw_spaced(d, (left + 22, top + bh / 2 + cap(f_box) / 2), "WWIT", f_box, INK, 2)
    f_lab = barlow(54, 800)
    draw_spaced(d, (left + bw + 20, top + bh / 2 + cap(f_lab) / 2), "MMA BREAKDOWN", f_lab, WHITE, 6)
    if title:
        f_t = barlow(40, 700)
        draw_spaced(d, (left, top + bh + 58), title.upper(), f_t, (190, 190, 196), 5)
    if tag:
        f_tag = barlow(34, 700)
        tw = spaced_width(tag.upper(), f_tag, 4)
        x1 = W - 54
        x0 = x1 - tw - 40
        d.rectangle([x0, top + 18, x1, top + 78], outline=accent, width=4)
        draw_spaced(d, (x0 + 20, top + 48 + cap(f_tag) / 2), tag.upper(), f_tag, accent, 4)
    # panel + accent rules
    d.rectangle([0, PANEL_Y0, W, PANEL_Y1], fill=PAPER)
    d.rectangle([0, PANEL_Y0 - 6, W, PANEL_Y0], fill=accent)
    d.rectangle([0, PANEL_Y1, W, PANEL_Y1 + 6], fill=accent)
    return im


def parse_caption(text):
    """'Holloway is forced to *close*.' -> [(word, highlighted), ...]"""
    words = []
    for tok in text.split():
        hl = "*" in tok
        words.append((tok.replace("*", "").upper(), hl))
    return words


def caption_layer(text, accent, t_in):
    """Caption block (RGBA, full frame) for a phrase that appeared t_in seconds ago."""
    anton, barlow, cap, draw_spaced, spaced_width, _ = _fonts()
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    words = parse_caption(text)
    size = 88
    max_w = W - 120
    while True:
        f = barlow(size, 800)
        sp = f.getlength(" ")
        lines, cur, cur_w = [], [], 0
        for wd, hl in words:
            ww = f.getlength(wd)
            if cur and cur_w + sp + ww > max_w:
                lines.append(cur)
                cur, cur_w = [], 0
            cur.append((wd, hl, ww))
            cur_w += (sp if len(cur) > 1 else 0) + ww
        if cur:
            lines.append(cur)
        if len(lines) == 2:
            # balance two lines: pick the split with the narrowest longer line
            flat = lines[0] + lines[1]
            lw = lambda ws: sum(x[2] for x in ws) + sp * (len(ws) - 1)
            best = min(range(1, len(flat)), key=lambda i: max(lw(flat[:i]), lw(flat[i:])))
            if max(lw(flat[:best]), lw(flat[best:])) <= max_w:
                lines = [flat[:best], flat[best:]]
        if len(lines) <= 2 or size <= 60:
            break
        size -= 6
    d = ImageDraw.Draw(layer)
    # pop-in: scale isn't cheap with PIL text, so slide up + fade instead
    k = min(1.0, t_in / 0.18)
    dy = int((1 - k) * 26)
    alpha = int(255 * k)
    lh = int(size * 1.08)
    y = CAPTION_Y + 40 + dy
    for line in lines:
        total = sum(w for _, _, w in line) + sp * (len(line) - 1)
        x = (W - total) / 2
        for wd, hl, ww in line:
            col = accent if hl else WHITE
            # ink shadow for legibility
            d.text((x + 4, y + 5), wd, font=f, fill=(0, 0, 0, int(alpha * 0.8)), anchor="la")
            d.text((x, y), wd, font=f, fill=col + (alpha,), anchor="la")
            x += ww + sp
        y += lh
    return layer


def caption_schedule(captions, duration):
    """[(start, end, text)] from strings or {"text","start"} dicts."""
    items = [c if isinstance(c, dict) else {"text": c} for c in (captions or [])]
    if not items:
        return []
    n = len(items)
    for i, it in enumerate(items):
        it.setdefault("start", duration * i / n)
    items.sort(key=lambda it: it["start"])
    out = []
    for i, it in enumerate(items):
        end = items[i + 1]["start"] if i + 1 < n else duration + 1
        out.append((float(it["start"]), float(end), it["text"]))
    return out


# ------------------------------------------------------------------ main ---

def make_sketch_video(src, out_dir, cfg=None, music=None, music_start=0.0):
    """Render the sketch Reel for `src` into out_dir/reel.mp4 + cover.png."""
    cfg = dict(cfg or {})
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    accent = hex_rgb(cfg.get("accent", DEFAULT_ACCENT))
    fps = int(cfg.get("fps", 12))
    k = int(cfg.get("fighters", 2))
    panel_w, panel_h = W, PANEL_Y1 - PANEL_Y0
    with tempfile.TemporaryDirectory() as tmp:
        path = resolve_video(src, tmp)
        start, end = cfg.get("start"), cfg.get("end")
        src_w, src_h, _ = probe(path)
        seg = Segmenter()

        # pass 1: find where the fighters are over the whole clip, at low res
        small = read_frames(path, fps, start, end, proc_w=480)
        duration = len(small) / fps
        if duration > 60:
            raise RuntimeError(f"clip is {duration:.0f}s; trim it to 60s or less with start/end")
        print(f"sketch: {len(small)} frames at {fps} fps ({duration:.1f}s)")
        # contact sheet of the source (6 frames) so a reviewer can check the clip
        idxs = [int(i * (len(small) - 1) / 11) for i in range(12)]
        th = []
        for i_ in idxs:
            t_ = cv2.resize(small[i_], (320, int(320 * small.shape[1] / small.shape[2])))
            cv2.putText(t_, f"{(start or 0) + i_ / fps:.1f}s", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 0), 2)
            th.append(t_)
        rows = [np.hstack(th[r * 4:(r + 1) * 4]) for r in range(3)]
        Image.fromarray(np.vstack(rows)).save(out_dir / "source.jpg", quality=80)
        det = None
        try:
            det = PersonDetector()
        except Exception as exc:  # ultralytics missing: segmentation only
            print(f"sketch: person detector unavailable ({exc}); using segmentation only")
        proc_w = 720
        proc_h = int(round(proc_w * panel_h / panel_w / 2)) * 2
        big_w = min(src_w, 1440)
        big = read_frames(path, fps, start, end, proc_w=big_w)
        if det is not None:
            guide_big = select_fighters(big, k, det)
            m_small = np.stack([cv2.resize(g.astype(np.uint8), (small.shape[2], small.shape[1]),
                                           interpolation=cv2.INTER_NEAREST).astype(bool) for g in guide_big])
        else:
            guide_big = None
            m_small = fighter_masks(small, k, seg)
        if not m_small.any():
            raise RuntimeError("no fighters found in the clip")
        n_ = min(len(big), len(m_small))
        if cfg.get("crop"):  # manual fixed box, source pixels [x0, y0, x1, y1]
            sx = big_w / src_w
            boxes = np.tile(np.array(cfg["crop"], float) * sx / (big_w / small.shape[2]), (n_, 1))
        else:
            boxes = follow_boxes(m_small, panel_w / panel_h, pad=float(cfg.get("pad", 0.12)), fps=fps)
        f = big_w / small.shape[2]
        frames = np.stack([crop_frame(big[i], boxes[i] * f, proc_w, proc_h) for i in range(n_)])
        if guide_big is not None:
            priors = np.stack([crop_frame(guide_big[i].astype(np.uint8) * 255, boxes[i] * f, proc_w, proc_h) > 127
                               for i in range(n_)])
        else:
            priors = np.stack([crop_frame(m_small[i].astype(np.uint8) * 255, boxes[i], proc_w, proc_h) > 127
                               for i in range(n_)])
        del big
        if cfg.get("mirror"):
            frames = frames[:, :, ::-1].copy()
            priors = priors[:, :, ::-1].copy()
        masks = fighter_masks(frames, k, seg, priors, strict=guide_big is not None)
        drawings = []
        for i, (fr, m) in enumerate(zip(frames, masks)):
            art = draw_frame(fr, m, panel_w / proc_w, cfg.get("colors", True))
            drawings.append(cv2.resize(art, (panel_w, panel_h), interpolation=cv2.INTER_AREA))
            if i % 24 == 0:
                print(f"sketch: drew {i + 1}/{len(frames)}")

        base = chrome(accent, cfg.get("title"), cfg.get("tag"))
        caps = caption_schedule(cfg.get("captions"), duration)
        n_out = int(round(duration * OUT_FPS))
        video_only = Path(tmp) / "video.mp4"
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{H}", "-r", str(OUT_FPS), "-i", "-",
                                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium",
                                "-crf", "19", str(video_only)], stdin=subprocess.PIPE)
        cover, last_key, buf = None, None, None
        for j in range(n_out):
            t = j / OUT_FPS
            di = min(len(drawings) - 1, int(t * fps))
            cap_now = next(((s0, txt) for s0, e0, txt in caps if s0 <= t < e0), None)
            t_in = t - cap_now[0] if cap_now else 0
            key = (di, cap_now[1] if cap_now else None, round(min(1.0, t_in / 0.18), 2))
            if key != last_key:
                im = base.copy()
                im.paste(Image.fromarray(drawings[di]), (0, PANEL_Y0))
                if cap_now:
                    layer = caption_layer(cap_now[1], accent, t_in)
                    im.paste(layer, (0, 0), layer)
                buf = np.asarray(im, np.uint8).tobytes()
                last_key = key
                if cover is None and t >= 0.6:
                    cover = im
            enc.stdin.write(buf)
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError("ffmpeg failed while encoding the sketch video")
        (cover or im).save(out_dir / "cover.png", optimize=True)

        # audio: music from the pool, the clip's own sound, or none
        audio_mode = cfg.get("audio", "music")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video_only)]
        afilter = None
        if audio_mode == "original" and has_audio(path):
            cmd += (["-ss", str(start)] if start else []) + ["-i", str(path)]
            afilter = f"[1:a]atrim=0:{duration:.3f},afade=t=out:st={max(0, duration - 0.5):.3f}:d=0.5[a]"
        elif audio_mode == "music" and music:
            cmd += ["-ss", str(music_start), "-i", str(ROOT / music)]
            afilter = (f"[1:a]atrim=0:{duration:.3f},afade=t=in:d=0.3,"
                       f"afade=t=out:st={max(0, duration - 0.8):.3f}:d=0.8,volume=0.9[a]")
        if afilter:
            cmd += ["-filter_complex", afilter, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                    "-c:a", "aac", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-c:v", "copy", "-an"]
        cmd += ["-movflags", "+faststart", str(out_dir / "reel.mp4")]
        subprocess.run(cmd, check=True)
    print(f"sketch: wrote {out_dir / 'reel.mp4'} ({duration:.1f}s)")
    return out_dir / "reel.mp4"


def make_reel_sketch(spec, out):
    """Entry point used by render.py for "format": "sketch" posts."""
    cfg = dict(spec.get("sketch") or {})
    if not cfg.get("video"):
        raise RuntimeError('sketch post needs "sketch": {"video": ...}')
    cfg.setdefault("captions", [])
    return make_sketch_video(cfg["video"], out, cfg, spec.get("music"), spec.get("music_start", 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", default="sketch/out")
    ap.add_argument("--start", type=float)
    ap.add_argument("--end", type=float)
    ap.add_argument("--caption", action="append", default=[])
    ap.add_argument("--fighters", type=int, default=2)
    ap.add_argument("--fps", type=int, default=12)
    ap.add_argument("--audio", default="original")
    ap.add_argument("--title")
    ap.add_argument("--tag")
    a = ap.parse_args()
    cfg = {"start": a.start, "end": a.end, "captions": a.caption, "fighters": a.fighters,
           "fps": a.fps, "audio": a.audio, "title": a.title, "tag": a.tag}
    make_sketch_video(a.video, a.out, cfg)


if __name__ == "__main__":
    main()
