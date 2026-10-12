#!/usr/bin/env python3
"""Pause Challenge Reels: "pause it when he fits the outline".

Added Oct 12 at the user's request. A ~2 second moment from a fight (a KO,
a head kick, a slam) plays on an endless loop, with a dashed outline drawn
over it in the exact shape the fighter makes on ONE frame (the "perfect
frame"). Viewers try to pause the Reel on that frame and screenshot it, so
they replay it over and over (replays push a Reel to more people).

Three looks, same pipeline (pick with "style"):
  - "footage": the real clip, cropped to the fighters, outline on top.
  - "cutout":  the fighters cut out of the clip onto a bright colour-burst
               background (the v2 look), white edge, outline on top.
  - "sketch":  the fighters redrawn as ink drawings on white (sketch.py),
               outline on top.

Instagram won't take a Reel shorter than 3 seconds, so the 2 s loop is
written several times back to back ("loops", 4 by default = 8 s). Every
loop is identical, so on Instagram it still plays as one endless loop.

Post file (posts/queue/<name>.json), on top of the usual fields:

    "format": "pause",
    "headline": "Pause It",                 # 1-3 words, used for post.png
    "pause": {
      "video": "drive:1AbC...",              # Drive id/link, repo path or https link
      "moment": 7.20,                        # seconds into the clip: the perfect frame
      "before": 1.4, "after": 0.6,           # loop = moment-before .. moment+after (2 s)
      "fighter": "left",                     # whose shape: "left", "right", "biggest"
                                             # or [x, y] (0-1, where he is on that frame)
      "fighters": 2,                         # people kept in cutout/sketch looks (1-2)
      "style": "footage",                    # "footage", "cutout" or "sketch"
      "title": "KHABIB VS MCGREGOR",         # line under the logo
      "tag": "UFC 229",                      # box at top right
      "loops": 4,                            # copies of the loop in the file (>= 3 s total)
      "audio": "music",                      # "music" (pool), "original" or "none"
      "outline": "#FFC21A",                  # outline colour (sketch default: red)
      "crop": [x0, y0, x1, y1],              # optional fixed box, source pixels
      "who": "HE",                           # "WHEN HE FITS..." (\"SHE\" for women)
      "mirror": false
    },
    "footage_credit": "UFC"

Outputs posts/<name>/reel.mp4 and cover.png like every other format, plus
check.png (the perfect frame with the outline over it: the fighter should
sit exactly inside) and source.jpg (frames of the loop with timestamps).

Run by hand: python pause.py <clip.mp4> --moment 7.2 [--style footage]
    [--fighter left] [--out dir]
"""

import argparse
import math
import subprocess
import tempfile
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from sketch import (Segmenter, PersonDetector, resolve_video, probe, has_audio, read_frames,
                    select_fighters, fighter_masks, fill_holes, draw_frame, crop_frame, hex_rgb,
                    _fonts, ROOT)

W, H, FPS = 1080, 1920, 30
HEADER_H = 300
PANEL_Y0, PANEL_Y1 = 300, 1380
BAND = (11, 11, 13)
INK = (11, 11, 13)
WHITE = (255, 255, 255)
DEFAULT_ACCENT = "#FFC21A"
SKETCH_OUTLINE = "#E4202C"
SIDE_L, SIDE_R = 120, 140          # Instagram crops the edges on tall phones


# ------------------------------------------------------------- the people ---

def people_at(frame, det, seg):
    """[(mask bool, box)] for each person on one frame, biggest first."""
    out = []
    if det is not None:
        for m, box, conf in det.people(frame):
            if m.sum() > 0.004 * m.size:
                out.append((m, box))
    else:
        prob = seg(frame)
        m = (prob > 0.5).astype(np.uint8)
        m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((5, 5), np.uint8))
        n, lab, stats, _ = cv2.connectedComponentsWithStats(m, 8)
        for i in range(1, n):
            if stats[i, cv2.CC_STAT_AREA] > 0.004 * m.size:
                x, y, w, h = stats[i, :4]
                out.append((lab == i, np.array([x, y, x + w, y + h], float)))
    out.sort(key=lambda p: -p[0].sum())
    return out


def pick_target(people, how, shape):
    """The person whose shape becomes the outline."""
    if not people:
        raise RuntimeError("no fighter found on the perfect frame (check 'moment')")
    h, w = shape
    if isinstance(how, (list, tuple)) and len(how) == 2:
        px, py = how[0] * w, how[1] * h
        def dist(p):
            m, box = p
            if m[min(h - 1, int(py)), min(w - 1, int(px))]:
                return -1
            cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
            return math.hypot(cx - px, cy - py)
        return min(people, key=dist)
    two = people[:2]
    if how == "left":
        return min(two, key=lambda p: p[1][0] + p[1][2])
    if how == "right":
        return max(two, key=lambda p: p[1][0] + p[1][2])
    return people[0]


def refine(mask, seg_prob=None):
    """Smooth, hole-free silhouette. With the segmenter's map, snap the
    detector's rough mask to the real edges near it."""
    m = mask.astype(np.uint8)
    if seg_prob is not None:
        near = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (21, 21))).astype(bool)
        snapped = (seg_prob > 0.5) & near
        if snapped.sum() > 0.6 * m.sum():
            m = snapped.astype(np.uint8)
    m = cv2.GaussianBlur(m * 255, (0, 0), 2.0) > 127
    m = fill_holes(m.astype(np.uint8)).astype(bool)
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), 8)
    if n > 2:
        big = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        m = lab == big
    return m


def fixed_box(boxes, aspect, src_w, src_h, pad=0.14, focus=None, inside=False):
    """One crop box for the whole loop (the outline must not move), around
    every frame's fighters, padded and fitted to the panel's aspect (w/h),
    kept inside the frame where possible."""
    b = np.array(boxes, float)
    x0, y0 = np.percentile(b[:, 0], 2), np.percentile(b[:, 1], 2)
    x1, y1 = np.percentile(b[:, 2], 98), np.percentile(b[:, 3], 98)
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    bw, bh = (x1 - x0) * (1 + 2 * pad), (y1 - y0) * (1 + 2 * pad)
    if bw / bh > aspect:
        bh = bw / aspect
    else:
        bw = bh * aspect
    if inside and (bh > src_h or bw > src_w):
        # real footage: no bars; shrink to the frame and centre on the
        # target fighter (the opponent may be cut at the edge)
        s_ = min(src_h / bh, src_w / bw)
        bw, bh = bw * s_, bh * s_
        if focus is not None:
            fx, fy = (focus[0] + focus[2]) / 2, (focus[1] + focus[3]) / 2
            cx, cy = 0.5 * cx + 0.5 * fx, 0.5 * cy + 0.5 * fy
    # slide inside the frame where it fits
    if bw <= src_w:
        cx = min(max(cx, bw / 2), src_w - bw / 2)
    if bh <= src_h:
        cy = min(max(cy, bh / 2), src_h - bh / 2)
    return np.array([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2])


# --------------------------------------------------------------- drawing ---

def contour_points(mask):
    """The silhouette's outer edge as a smoothed closed polyline (N x 2)."""
    cs, _ = cv2.findContours(mask.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not cs:
        return None
    c = max(cs, key=cv2.contourArea)[:, 0, :].astype(float)
    if len(c) < 20:
        return c
    # circular moving average: removes pixel stair-steps, keeps the pose
    k = max(3, len(c) // 160) | 1
    ker = np.ones(k) / k
    xs = np.convolve(np.r_[c[-k:, 0], c[:, 0], c[:k, 0]], ker, "same")[k:-k]
    ys = np.convolve(np.r_[c[-k:, 1], c[:, 1], c[:k, 1]], ker, "same")[k:-k]
    return np.stack([xs, ys], 1)


def dashed(d, pts, color, width, dash=30, gap=18):
    """Dashed closed polyline (dash pattern runs along the arc length)."""
    pts = np.vstack([pts, pts[:1]])
    seg = np.hypot(*np.diff(pts, axis=0).T)
    pos, on, left = 0.0, True, dash
    cur = [tuple(pts[0])]
    for i, L in enumerate(seg):
        a, b = pts[i], pts[i + 1]
        t0 = 0.0
        while L - t0 * L > 1e-6 and L > 0:
            remain = L * (1 - t0)
            if remain <= left:
                left -= remain
                if on:
                    cur.append(tuple(b))
                break
            t1 = t0 + left / L
            p = a + (b - a) * t1
            if on:
                cur.append(tuple(p))
                if len(cur) > 1:
                    d.line(cur, fill=color, width=width, joint="curve")
                cur = []
            else:
                cur = [tuple(p)]
            on = not on
            left = dash if on else gap
            t0 = t1
    if on and len(cur) > 1:
        d.line(cur, fill=color, width=width, joint="curve")


def outline_layer(mask_panel, color, fill_alpha=0.10):
    """RGBA overlay (panel size): faint tint inside the target shape, a dark
    shadow line and a dashed bright line on its edge."""
    h, w = mask_panel.shape
    pts = contour_points(mask_panel)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    if pts is None:
        return layer
    if fill_alpha > 0:
        tint = Image.new("RGBA", (w, h), color + (int(255 * fill_alpha),))
        layer.paste(tint, (0, 0), Image.fromarray((mask_panel * 255).astype(np.uint8)))
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).line([tuple(p) for p in np.vstack([pts, pts[:1]])],
                                fill=(0, 0, 0, 170), width=20, joint="curve")
    shadow = shadow.filter(ImageFilter.GaussianBlur(4))
    layer = Image.alpha_composite(layer, shadow)
    d = ImageDraw.Draw(layer)
    dashed(d, pts, color + (255,), 11)
    return layer


def chrome(accent, title=None, tag=None, who="HE"):
    """Header band with the logo, the panel area, and the challenge text."""
    anton, barlow, cap, draw_spaced, spaced_width, _ = _fonts()
    im = Image.new("RGB", (W, H), BAND)
    d = ImageDraw.Draw(im)
    for x in range(-H, W, 22):
        d.line([(x, 0), (x + HEADER_H, HEADER_H)], fill=(20, 20, 24), width=2)
        d.line([(x, PANEL_Y1), (x + (H - PANEL_Y1), H)], fill=(20, 20, 24), width=2)
    top, left = 112, SIDE_L
    f_box = anton(64)
    bw = int(spaced_width("WWIT", f_box, 2)) + 44
    bh = 96
    d.rectangle([left, top, left + bw, top + bh], fill=accent)
    draw_spaced(d, (left + 22, top + bh / 2 + cap(f_box) / 2), "WWIT", f_box, INK, 2)
    f_lab = barlow(50, 800)
    draw_spaced(d, (left + bw + 20, top + bh / 2 + cap(f_lab) / 2), "PAUSE CHALLENGE", f_lab, WHITE, 5)
    if title:
        f_t = barlow(40, 700)
        draw_spaced(d, (left, top + bh + 58), title.upper(), f_t, (190, 190, 196), 5)
    if tag:
        f_tag = barlow(34, 700)
        tw = spaced_width(tag.upper(), f_tag, 4)
        x1 = W - SIDE_R
        x0 = x1 - tw - 40
        ty = top + bh + 22                  # on the title line, right side
        d.rectangle([x0, ty, x1, ty + 56], outline=accent, width=4)
        draw_spaced(d, (x0 + 20, ty + 28 + cap(f_tag) / 2), tag.upper(), f_tag, accent, 4)
    d.rectangle([0, PANEL_Y0 - 6, W, PANEL_Y0], fill=accent)
    d.rectangle([0, PANEL_Y1, W, PANEL_Y1 + 6], fill=accent)
    # the challenge, under the panel
    f1 = anton(150)
    y = PANEL_Y1 + 60 + cap(f1)
    draw_spaced(d, (SIDE_L, y), "PAUSE IT", f1, WHITE, 3)
    f2 = barlow(64, 800)
    y2 = y + 34 + cap(f2)
    x = SIDE_L
    lead = f"WHEN {who.upper()} FITS THE "
    draw_spaced(d, (x, y2), lead, f2, WHITE, 3)
    x += spaced_width(lead, f2, 3)
    draw_spaced(d, (x, y2), "OUTLINE", f2, accent, 3)
    f3 = barlow(38, 700)
    draw_spaced(d, (SIDE_L, y2 + 30 + cap(f3) + 10), "SCREENSHOT IT + DROP IT IN THE COMMENTS", f3,
                (170, 170, 176), 3)
    return im


def cutout_panel(frame, mask, bg, edge=8):
    """Fighters cut out of the frame onto `bg`, with a white edge."""
    m = mask.astype(np.uint8) * 255
    soft = cv2.GaussianBlur(m, (0, 0), 1.2)
    ring = cv2.dilate(m, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * edge + 1, 2 * edge + 1)))
    ring = cv2.GaussianBlur(ring, (0, 0), 1.2)
    out = bg.astype(np.float32)
    a = ring[..., None] / 255.0
    out = out * (1 - a) + 255 * a
    a = soft[..., None] / 255.0
    out = out * (1 - a) + frame.astype(np.float32) * a
    return out.clip(0, 255).astype(np.uint8)


def opposite_hue(frames, masks):
    """Background hue opposite the fighters' own colours (blue by default)."""
    sx = sy = wt = 0.0
    for f, m in zip(frames[::6], masks[::6]):
        hsv = cv2.cvtColor(f, cv2.COLOR_RGB2HSV)[m]
        if not len(hsv):
            continue
        s, v = hsv[:, 1] / 255.0, hsv[:, 2] / 255.0
        ang = hsv[:, 0] / 180.0 * 2 * math.pi
        w = s * v
        sx += float((np.cos(ang) * w).sum())
        sy += float((np.sin(ang) * w).sum())
        wt += float(w.sum())
    if wt < 1 or math.hypot(sx, sy) / wt < 0.08:
        return 0.58
    return ((math.atan2(sy, sx) / (2 * math.pi)) % 1.0 + 0.5) % 1.0


# ---------------------------------------------------------------- render ---

def make_pause_video(src, out_dir, cfg=None, music=None, music_start=0.0):
    cfg = dict(cfg or {})
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    style = cfg.get("style", "footage")
    if style not in ("footage", "cutout", "sketch"):
        raise RuntimeError(f"unknown pause style {style!r} (footage, cutout or sketch)")
    accent = hex_rgb(cfg.get("accent", DEFAULT_ACCENT))
    line_col = hex_rgb(cfg.get("outline", SKETCH_OUTLINE if style == "sketch" else cfg.get("accent", DEFAULT_ACCENT)))
    if cfg.get("moment") is None:
        raise RuntimeError('pause post needs "moment": the second of the perfect frame')
    moment = float(cfg["moment"])
    before, after = float(cfg.get("before", 1.4)), float(cfg.get("after", 0.6))
    start = max(0.0, moment - before)
    before = moment - start
    loops = max(1, int(cfg.get("loops", 4)))
    k = int(cfg.get("fighters", 2))
    panel_w, panel_h = W, PANEL_Y1 - PANEL_Y0

    with tempfile.TemporaryDirectory() as tmp:
        path = resolve_video(src, tmp)
        src_w, src_h, dur = probe(path)
        if moment > dur:
            raise RuntimeError(f"moment {moment}s is past the end of the clip ({dur:.1f}s)")
        proc_w = min(src_w, 1280)
        frames = read_frames(path, FPS, start, start + before + after, proc_w=proc_w)
        n = len(frames)
        ti = min(n - 1, int(round(before * FPS)))
        print(f"pause: {n} frames at {FPS} fps, perfect frame #{ti} ({start + ti / FPS:.2f}s)")
        if cfg.get("mirror"):
            frames = frames[:, :, ::-1].copy()
        fh, fw = frames.shape[1:3]
        sc = fw / src_w

        seg = Segmenter()
        det = None
        try:
            det = PersonDetector()
        except Exception as exc:
            print(f"pause: person detector unavailable ({exc}); using segmentation only")

        # the target shape, on the perfect frame
        people = people_at(frames[ti], det, seg)
        tgt_mask, tgt_box = pick_target(people, cfg.get("fighter", "biggest"), (fh, fw))
        tgt_mask = refine(tgt_mask, seg(frames[ti]))
        print(f"pause: {len(people)} people on the perfect frame; target box {np.round(tgt_box).tolist()}")

        # where the fighters are over the loop -> one fixed crop
        guide = None
        if cfg.get("crop"):
            box = np.array(cfg["crop"], float) * sc
        else:
            boxes = []
            step = 3
            if det is not None and style != "footage":
                guide = select_fighters(frames, k, det)
            for i in range(0, n, step):
                if guide is not None:
                    gm = guide[i]
                    ys, xs = np.nonzero(gm)
                    if len(xs):
                        boxes.append([xs.min(), ys.min(), xs.max(), ys.max()])
                    continue
                ps = people_at(frames[i], det, seg)[:k]
                if ps:
                    bb = np.array([p[1] for p in ps])
                    boxes.append([bb[:, 0].min(), bb[:, 1].min(), bb[:, 2].max(), bb[:, 3].max()])
            ys, xs = np.nonzero(tgt_mask)
            tb = [xs.min(), ys.min(), xs.max(), ys.max()]
            boxes.append(tb)
            box = fixed_box(boxes, panel_w / panel_h, fw, fh, pad=float(cfg.get("pad", 0.14)),
                            focus=tb, inside=style == "footage")
            # the target shape itself must stay fully in the panel
            if style == "footage":
                box[0], box[2] = min(box[0], tb[0] - 10) , max(box[2], tb[2] + 10)
                if box[2] - box[0] > (box[3] - box[1]) * panel_w / panel_h:
                    extra = (box[2] - box[0]) * panel_h / panel_w - (box[3] - box[1])
                    box[1] -= extra / 2; box[3] += extra / 2
        print(f"pause: crop box {np.round(box / sc).tolist()} (source px)")

        fill = 0 if style == "footage" else 255
        crops = np.stack([crop_frame(f, box, panel_w, panel_h, fill) for f in frames])
        tgt_panel = crop_frame(tgt_mask.astype(np.uint8) * 255, box, panel_w, panel_h, 0) > 127
        outline = outline_layer(tgt_panel, line_col, 0.10 if style == "footage" else 0.0)

        # the fighters on every frame (cutout and sketch looks)
        panels = []
        if style == "footage":
            panels = list(crops)
        else:
            proc_pw = 720
            proc_ph = int(round(proc_pw * panel_h / panel_w / 2)) * 2
            small = np.stack([cv2.resize(c, (proc_pw, proc_ph), interpolation=cv2.INTER_AREA) for c in crops])
            priors = None
            if guide is not None:
                priors = np.stack([cv2.resize(crop_frame(g.astype(np.uint8) * 255, box, panel_w, panel_h, 0),
                                              (proc_pw, proc_ph), interpolation=cv2.INTER_NEAREST) > 127
                                   for g in guide])
            masks = fighter_masks(small, k, seg, priors, strict=priors is not None)
            # the target fighter must be complete on the perfect frame
            tm = cv2.resize(tgt_panel.astype(np.uint8), (proc_pw, proc_ph), interpolation=cv2.INTER_NEAREST).astype(bool)
            masks[ti] = masks[ti].astype(bool) | tm
            if style == "cutout":
                from reel_v2 import burst_panel
                hue = cfg.get("hue")
                hue = float(hue) if hue is not None else opposite_hue(small, masks.astype(bool))
                bg = np.asarray(burst_panel(hue, panel_w, panel_h).convert("RGB"))
                for c, m in zip(crops, masks):
                    mb = cv2.resize(m.astype(np.uint8), (panel_w, panel_h), interpolation=cv2.INTER_LINEAR) > 0
                    panels.append(cutout_panel(c, mb, bg))
            else:
                for i, (c, m) in enumerate(zip(small, masks)):
                    art = draw_frame(c, m, panel_w / proc_pw, cfg.get("colors", True))
                    panels.append(cv2.resize(art, (panel_w, panel_h), interpolation=cv2.INTER_AREA))
                    if i % 24 == 0:
                        print(f"pause: drew {i + 1}/{n}")

        base = chrome(accent, cfg.get("title"), cfg.get("tag"), cfg.get("who", "HE"))
        rendered = []
        for p in panels:
            im = base.copy()
            pan = Image.fromarray(p).convert("RGBA")
            pan = Image.alpha_composite(pan, outline)
            im.paste(pan.convert("RGB"), (0, PANEL_Y0))
            rendered.append(np.asarray(im, np.uint8))

        # check image: the perfect frame with the outline (should sit exactly)
        Image.fromarray(rendered[ti]).save(out_dir / "check.png", optimize=True)
        # cover: the first frame (fighter not yet in the shape)
        Image.fromarray(rendered[0]).save(out_dir / "cover.png", optimize=True)
        # contact sheet of the loop
        idxs = [int(i * (n - 1) / 11) for i in range(12)]
        th = []
        for i_ in idxs:
            t_ = cv2.resize(rendered[i_][PANEL_Y0:PANEL_Y1], (270, int(270 * panel_h / panel_w)))
            t_ = np.ascontiguousarray(t_)
            cv2.putText(t_, f"{start + i_ / FPS:.2f}s" + (" *" if i_ == ti else ""), (6, 24),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 0), 2)
            th.append(t_)
        Image.fromarray(np.vstack([np.hstack(th[r * 4:(r + 1) * 4]) for r in range(3)])).save(
            out_dir / "source.jpg", quality=80)

        total = n * loops / FPS
        video_only = Path(tmp) / "video.mp4"
        enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                                "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                                "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "18",
                                "-g", str(FPS), str(video_only)], stdin=subprocess.PIPE)
        for _ in range(loops):
            for fr in rendered:
                enc.stdin.write(fr.tobytes())
        enc.stdin.close()
        if enc.wait():
            raise RuntimeError("ffmpeg failed while encoding the pause video")

        audio = cfg.get("audio", "music")
        cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(video_only)]
        af = None
        if audio == "original" and has_audio(path):
            # the clip's own sound for the loop, repeated with the picture
            cmd += ["-ss", f"{start:.3f}", "-t", f"{n / FPS:.3f}", "-i", str(path)]
            af = f"[1:a]aloop=loop={loops - 1}:size={int(48000 * n / FPS)},atrim=0:{total:.3f}[a]"
        elif audio == "music" and music:
            cmd += ["-ss", str(music_start), "-i", str(ROOT / music)]
            af = (f"[1:a]atrim=0:{total:.3f},afade=t=in:d=0.2,"
                  f"afade=t=out:st={max(0, total - 0.4):.3f}:d=0.4,volume=0.9[a]")
        if af:
            cmd += ["-filter_complex", af, "-map", "0:v", "-map", "[a]", "-c:v", "copy",
                    "-c:a", "aac", "-ar", "48000", "-b:a", "192k", "-shortest"]
        else:
            cmd += ["-c:v", "copy", "-an"]
        cmd += ["-movflags", "+faststart", str(out_dir / "reel.mp4")]
        subprocess.run(cmd, check=True)
    print(f"pause: wrote {out_dir / 'reel.mp4'} ({style}, {n / FPS:.2f}s loop x{loops} = {total:.1f}s)")
    return out_dir / "reel.mp4"


def make_reel_pause(spec, out):
    """Entry point used by render.py for "format": "pause" posts."""
    cfg = dict(spec.get("pause") or {})
    if not cfg.get("video"):
        raise RuntimeError('pause post needs "pause": {"video": ...}')
    return make_pause_video(cfg["video"], out, cfg, spec.get("music"), spec.get("music_start", 0))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--moment", type=float, required=True)
    ap.add_argument("--before", type=float, default=1.4)
    ap.add_argument("--after", type=float, default=0.6)
    ap.add_argument("--style", default="footage")
    ap.add_argument("--fighter", default="biggest")
    ap.add_argument("--fighters", type=int, default=2)
    ap.add_argument("--loops", type=int, default=4)
    ap.add_argument("--audio", default="original")
    ap.add_argument("--title")
    ap.add_argument("--tag")
    ap.add_argument("--out", default="sketch/out-pause")
    a = ap.parse_args()
    make_pause_video(a.video, a.out, {"moment": a.moment, "before": a.before, "after": a.after,
                                      "style": a.style, "fighter": a.fighter, "fighters": a.fighters,
                                      "loops": a.loops, "audio": a.audio, "title": a.title, "tag": a.tag})


if __name__ == "__main__":
    main()
