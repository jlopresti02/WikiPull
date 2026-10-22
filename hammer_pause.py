"""Carnival hammer (high striker) pause-challenge Reel.

The hammer slams, the puck flies up the tower, rings the bell and drops back.
On exactly ONE frame per loop the puck sits inside the dashed outline on the
target fighter's tier. Viewers try to pause on it.

    python3 hammer_pause.py posts/<name>
"""
import json, math, subprocess, sys, wave, random
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1920
FPS = 30
LOOP = 72            # 2.4 s per loop
LOOPS = 3            # 7.2 s Reel (IG needs 3 s+)
IMPACT = 6           # hammer hits the pad
TOP = 21             # puck rings the bell
DOWN = 40            # puck back on the pad
PERFECT = 13         # the one frame on target (rising)

ANTON = str(ROOT / "fonts/Anton-Regular.ttf")
BARLOW = str(ROOT / "fonts/BarlowCondensed-ExtraBold.ttf")
BARLOW_B = str(ROOT / "fonts/BarlowCondensed-Bold.ttf")


def font(p, s):
    return ImageFont.truetype(p, s)


# ---------------------------------------------------------------- geometry
CX = 560                     # tower centre line
RAIL_TOP, RAIL_BOT = 530, 1270
BELL_Y = 468
PUCK_W, PUCK_H = 96, 54
PAD_Y = 1470

TIERS = [  # (label, y) bottom -> top; the target tier is added separately
    ("WEAK", 1200),
    ("PURE BORING", 1090),
    ("NEVER GETS IT", 980),
    ("PAVLOVICH PTSD", 870),
    ("STILL WAITING", 680),
    ("NEXT IN LINE", 585),
]


def puck_y(f):
    """Centre y of the puck on loop frame f."""
    rest = RAIL_BOT - PUCK_H / 2
    top = RAIL_TOP + PUCK_H / 2 + 6
    if f < IMPACT or f >= DOWN:
        if f >= DOWN:  # small settle bounce
            k = f - DOWN
            return rest - 26 * abs(math.sin(k * 0.55)) * math.exp(-k * 0.35)
        return rest
    if f <= TOP:  # rising, ease-out
        t = (f - IMPACT) / (TOP - IMPACT)
        return rest - (rest - top) * (1 - (1 - t) ** 1.9)
    t = (f - TOP - 0.1) / (DOWN - TOP - 0.1)  # falling, gravity (half-frame offset keeps the drop off the target)
    return top + (rest - top) * t ** 2


TARGET_Y = puck_y(PERFECT)


def hammer_angle(f):
    """Degrees; 0 = mallet head resting on the pad, positive = raised."""
    if f < IMPACT:
        return 95 * (1 - (f / IMPACT) ** 2.2)
    if f < IMPACT + 3:
        return -4 * (IMPACT + 3 - f) / 3
    if f < 50:
        return 0
    t = (f - 50) / (LOOP - 50)
    return 95 * (0.5 - 0.5 * math.cos(math.pi * t))


# ---------------------------------------------------------------- static art
def radial_bg():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    ang = np.arctan2(y + 300, x - W / 2)
    stripes = (np.floor(ang / (math.pi / 18)) % 2).astype(np.float32)
    red = np.array([214, 32, 45], np.float32)
    cream = np.array([255, 242, 214], np.float32)
    img = stripes[..., None] * red + (1 - stripes[..., None]) * cream
    # vignette
    d = np.sqrt(((x - W / 2) / W) ** 2 + ((y - H * 0.45) / H) ** 2)
    img *= (1 - np.clip(d - 0.25, 0, 1) * 0.9)[..., None]
    return Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")


def text_c(d, xy, s, f, fill, stroke=0, sfill="black", anchor="mm"):
    d.text(xy, s, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill, anchor=anchor)


def volkov_head(size):
    im = Image.open(ROOT / "images/alexander-volkov-fighter/ufc/volkov-ufc.png").convert("RGBA")
    head = im.crop((135, 0, 335, 250))  # hair to chin (UFC roster photo)
    head = head.resize((size, int(size * 250 / 200)), Image.LANCZOS)
    return head


def static_layer():
    bg = radial_bg()
    d = ImageDraw.Draw(bg)

    # string lights across the top (drawn per-frame for the blink) -> just wire
    for k in range(2):
        pts = [(x, 330 + k * 40 + 40 * math.sin(x / W * math.pi)) for x in range(-20, W + 21, 10)]
        d.line(pts, fill=(40, 20, 20), width=4)

    # ---- tower
    board = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    bd = ImageDraw.Draw(board)
    x0, x1 = CX - 230, CX + 130
    bd.rounded_rectangle((x0 + 10, RAIL_TOP - 30 + 12, x1 + 10, RAIL_BOT + 30 + 12), 28, fill=(0, 0, 0, 110))
    bd.rounded_rectangle((x0, RAIL_TOP - 30, x1, RAIL_BOT + 30), 28, fill=(28, 24, 52, 255), outline=(255, 210, 60, 255), width=8)
    # heat meter beside the rail
    mx0, mx1 = CX - 210, CX - 70
    n = 60
    for i in range(n):
        ya = RAIL_BOT - (RAIL_BOT - RAIL_TOP) * i / n
        yb = RAIL_BOT - (RAIL_BOT - RAIL_TOP) * (i + 1) / n
        t = i / (n - 1)
        col = (int(60 + 195 * min(1, t * 2)), int(200 - 170 * max(0, t * 2 - 1)), 60, 255)
        bd.rectangle((mx0, yb + 1, mx1, ya), fill=col)
    # rail
    bd.rounded_rectangle((CX - 16, RAIL_TOP - 10, CX + 16, RAIL_BOT + 10), 12, fill=(200, 200, 214, 255), outline=(90, 90, 110, 255), width=3)
    for yy in range(RAIL_TOP, RAIL_BOT, 22):
        bd.line((CX + 30, yy, CX + 44, yy), fill=(255, 210, 60, 160), width=3)
    bg.alpha_composite(board)
    d = ImageDraw.Draw(bg)

    # tier labels on the meter
    f_t = font(BARLOW, 34)
    for label, y in TIERS:
        d.line((mx0, y, CX - 30, y), fill=(255, 255, 255), width=3)
        text_c(d, ((mx0 + mx1) / 2 - 2, y - 22), label, f_t, "white", 4, (20, 10, 30))

    # target tier
    ty = TARGET_Y
    d.line((mx0, ty, CX + 120, ty), fill=(255, 225, 0), width=5)

    # base post joining the tower to the striking pad
    d.rectangle((CX - 60, RAIL_BOT + 30, CX + 60, PAD_Y - 20), fill=(28, 24, 52), outline=(255, 210, 60), width=6)
    # bell
    d.rectangle((CX - 8, BELL_Y + 20, CX + 8, RAIL_TOP - 20), fill=(90, 70, 20))
    return bg


def target_panel():
    """Volkov's head in a medallion, to the right of the target tier."""
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    cx, cy, r = 870, int(TARGET_Y), 118
    d.ellipse((cx - r - 10, cy - r - 10 + 10, cx + r + 10, cy + r + 10 + 10), fill=(0, 0, 0, 120))
    d.ellipse((cx - r - 10, cy - r - 10, cx + r + 10, cy + r + 10), fill=(255, 210, 40, 255))
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=(30, 110, 230, 255))
    head = volkov_head(2 * r + 10)
    mask = Image.new("L", (W, H), 0)
    ImageDraw.Draw(mask).ellipse((cx - r, cy - r, cx + r, cy + r), fill=255)
    tmp = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    tmp.alpha_composite(head, (cx - head.width // 2, int(cy - head.height * 0.52)))
    tmp.putalpha(Image.fromarray(np.minimum(np.array(tmp.getchannel("A")), np.array(mask))))
    lay.alpha_composite(tmp)
    # name plate
    f = font(ANTON, 54)
    d.rounded_rectangle((cx - 120, cy + r + 22, cx + 120, cy + r + 92), 14, fill=(214, 32, 45), outline="white", width=5)
    text_c(d, (cx, cy + r + 57), "VOLKOV", f, "white")
    # arrow to the slot
    d.polygon([(CX + 70, TARGET_Y), (CX + 112, TARGET_Y - 26), (CX + 112, TARGET_Y + 26)], fill=(255, 225, 0))
    return lay


def dashed_rect(d, box, color, w=6, dash=16, gap=10):
    x0, y0, x1, y1 = box
    def seg(a, b, horiz, fixed):
        p = a
        while p < b:
            q = min(p + dash, b)
            if horiz:
                d.line((p, fixed, q, fixed), fill=color, width=w)
            else:
                d.line((fixed, p, fixed, q), fill=color, width=w)
            p += dash + gap
    seg(x0, x1, True, y0); seg(x0, x1, True, y1)
    seg(y0, y1, False, x0); seg(y0, y1, False, x1)


def header_layer():
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    f_b = font(BARLOW, 30)
    d.rounded_rectangle((W / 2 - 130, 60, W / 2 + 130, 104), 22, fill=(20, 16, 30))
    text_c(d, (W / 2, 82), "WWIT MMA NEWS", f_b, "white")
    f_h = font(ANTON, 104)
    text_c(d, (W / 2, 175), "PAUSE TO LAND", f_h, "white", 10, (20, 10, 30))
    text_c(d, (W / 2, 290), "ON VOLKOV", f_h, (255, 214, 0), 10, (20, 10, 30))
    d.rounded_rectangle((W / 2 - 250, 362, W / 2 + 250, 412), 25, fill=(214, 32, 45), outline="white", width=4)
    text_c(d, (W / 2, 387), "ONLY 1% CAN PAUSE PERFECTLY", font(BARLOW, 36), "white")
    return lay


# ---------------------------------------------------------------- per-frame bits
def draw_lights(d, f):
    for k in range(2):
        for i, x in enumerate(range(20, W, 70)):
            y = 330 + k * 40 + 40 * math.sin(x / W * math.pi) + 14
            on = (i + k + f // 4) % 2 == 0
            col = (255, 230, 120) if on else (130, 90, 40)
            if on:
                d.ellipse((x - 16, y - 16, x + 16, y + 16), fill=(255, 220, 120, 70))
            d.ellipse((x - 9, y - 9, x + 9, y + 9), fill=col)


def draw_bell(lay, f):
    d = ImageDraw.Draw(lay)
    ring = 0 <= f - TOP < 10
    shake = 10 * math.sin((f - TOP) * 2.4) * math.exp(-(f - TOP) * 0.3) if ring else 0
    bx, by = CX + shake, BELL_Y
    if ring:
        for r, a in ((150, 50), (110, 90)):
            d.ellipse((bx - r, by - r + 20, bx + r, by + r + 20), fill=(255, 230, 80, a))
    d.pieslice((bx - 70, by - 50, bx + 70, by + 90), 180, 360, fill=(255, 196, 30), outline=(120, 80, 0), width=5)
    d.rectangle((bx - 76, by + 16, bx + 76, by + 34), fill=(230, 160, 20), outline=(120, 80, 0), width=4)
    d.ellipse((bx - 12, by + 28, bx + 12, by + 52), fill=(120, 80, 0))
    if ring:
        text_c(d, (bx + 190, by - 10), "DING!", font(ANTON, 70), (255, 230, 0), 7, (20, 10, 30))


def draw_hammer(lay, f):
    """Big mallet pivoting from the lower right onto the pad."""
    ang = hammer_angle(f)
    m = Image.new("RGBA", (700, 700), (0, 0, 0, 0))
    md = ImageDraw.Draw(m)
    # pivot at (600, 350); handle extends left to the head at x~150
    md.rounded_rectangle((180, 336, 610, 364), 12, fill=(150, 95, 45), outline=(70, 40, 15), width=4)
    md.rounded_rectangle((100, 275, 220, 425), 24, fill=(214, 32, 45), outline=(70, 10, 10), width=6)
    md.rectangle((100, 310, 220, 334), fill=(255, 242, 214))
    md.rectangle((100, 366, 220, 390), fill=(255, 242, 214))
    rot = m.rotate(-ang, center=(600, 350), resample=Image.BICUBIC)
    # place so the mallet head lands on the pad when ang == 0
    px, py = CX + 440, PAD_Y - 36 - 75
    lay.alpha_composite(rot, (int(px - 600), int(py - 350)))


def draw_pad(d, f):
    hit = 0 <= f - IMPACT < 5
    squash = 8 if hit else 0
    d.ellipse((CX - 150, PAD_Y + 30, CX + 150, PAD_Y + 80), fill=(0, 0, 0, 90))
    d.rounded_rectangle((CX - 120, PAD_Y - 20 + squash, CX + 120, PAD_Y + 50), 16, fill=(60, 60, 75), outline=(20, 20, 30), width=5)
    d.rounded_rectangle((CX - 90, PAD_Y - 36 + squash, CX + 90, PAD_Y - 10 + squash), 10, fill=(255, 196, 30), outline=(120, 80, 0), width=4)
    if hit:
        k = f - IMPACT
        for a in range(-60, 241, 30):
            r0, r1 = 130 + k * 25, 190 + k * 35
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            d.line((CX + ca * r0, PAD_Y - 20 - sa * r0 * 0.6, CX + ca * r1, PAD_Y - 20 - sa * r1 * 0.6), fill=(255, 240, 120), width=8)
        if k < 4:
            text_c(d, (CX - 290, PAD_Y - 120), "BOOM!", font(ANTON, 84), (255, 240, 0), 8, (20, 10, 30))


def draw_puck(lay, f):
    d = ImageDraw.Draw(lay)
    y = puck_y(f)
    prev = puck_y((f - 1) % LOOP)
    v = y - prev
    if abs(v) > 12 and f != PERFECT:  # motion streak (none on the perfect frame)
        for i in range(1, 5):
            yy = y - v * i * 0.22
            a = int(70 - 15 * i)
            d.rounded_rectangle((CX - PUCK_W / 2 + 6, yy - PUCK_H / 2, CX + PUCK_W / 2 - 6, yy + PUCK_H / 2), 14, fill=(255, 255, 255, a))
    d.rounded_rectangle((CX - PUCK_W / 2, y - PUCK_H / 2, CX + PUCK_W / 2, y + PUCK_H / 2), 16, fill=(250, 250, 255), outline=(20, 20, 30), width=5)
    d.rounded_rectangle((CX - PUCK_W / 2 + 10, y - 8, CX + PUCK_W / 2 - 10, y + 8), 6, fill=(214, 32, 45))


VERDICTS = {
    "wait": [("WAIT FOR IT", "Drago is warming up the hammer")],
    "early": [("TOO EARLY", "Hokit says he'll never get there"),
              ("WAY TOO EARLY", "Still stuck behind the line"),
              ("EARLY", "That's a Pavlovich flashback")],
    "close_early": [("SO CLOSE", "One frame short of the title shot")],
    "perfect": [("PERFECT!", "Volkov finally gets his shot")],
    "close_late": [("JUST LATE", "Right past him. Classic.")],
    "late": [("TOO LATE", "Bell rang, title went to someone else"),
             ("WAY LATE", "Pereira skipped the line again"),
             ("MISSED IT", "6'7\" and you still missed him")],
}


def verdict(f):
    if f < IMPACT or f >= DOWN:
        return "wait", 0
    if f == PERFECT:
        return "perfect", 0
    if f == PERFECT - 1:
        return "close_early", 0
    if f == PERFECT + 1:
        return "close_late", 0
    if f < PERFECT:
        return "early", f
    return "late", f


def draw_verdict(lay, f):
    d = ImageDraw.Draw(lay)
    kind, k = verdict(f)
    opts = VERDICTS[kind]
    big, small = opts[k % len(opts)]
    col = {"perfect": (40, 220, 90), "early": (60, 150, 255), "close_early": (60, 150, 255),
           "late": (255, 60, 70), "close_late": (255, 60, 70), "wait": (255, 255, 255)}[kind]
    y = 1680
    d.rounded_rectangle((70, y - 70, W - 70, y + 150), 34, fill=(20, 14, 34, 225), outline=col, width=6)
    text_c(d, (W / 2, y), big, font(ANTON, 104), col, 6, (10, 6, 20))
    text_c(d, (W / 2, y + 100), small, font(BARLOW_B, 46), "white")
    # frame counter
    text_c(d, (126, 1470), f"frame {f + 1:02d}/{LOOP}", font(BARLOW_B, 34), "white", 4, (20, 10, 30))


def draw_target(lay, f):
    d = ImageDraw.Draw(lay)
    hit = f == PERFECT
    box = (CX - PUCK_W / 2 - 8, TARGET_Y - PUCK_H / 2 - 8, CX + PUCK_W / 2 + 8, TARGET_Y + PUCK_H / 2 + 8)
    if hit:
        d.rounded_rectangle((box[0] - 14, box[1] - 14, box[2] + 14, box[3] + 14), 22, fill=(60, 255, 120, 110))
        dashed_rect(d, box, (60, 255, 120), 8)
        cx, cy, r = 870, TARGET_Y, 140
        d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(60, 255, 120), width=10)
    else:
        dashed_rect(d, box, (255, 225, 0), 6)


# ---------------------------------------------------------------- audio
def synth_fx(path, n_frames):
    sr = 44100
    total = int(sr * n_frames / FPS)
    out = np.zeros(total, np.float32)
    rng = np.random.default_rng(7)
    for L in range(LOOPS):
        base = L * LOOP
        # impact boom
        s = int(sr * (base + IMPACT) / FPS)
        t = np.arange(int(sr * 0.6)) / sr
        boom = np.sin(2 * np.pi * (55 + 90 * np.exp(-t * 18)) * t) * np.exp(-t * 6)
        boom += rng.normal(0, 1, t.size) * np.exp(-t * 40) * 0.5
        out[s:s + t.size] += boom[: max(0, total - s)] * 0.9
        # whoosh up
        s2 = int(sr * (base + IMPACT + 1) / FPS)
        t2 = np.arange(int(sr * (TOP - IMPACT) / FPS)) / sr
        wn = rng.normal(0, 1, t2.size)
        wn = np.convolve(wn, np.ones(30) / 30, mode="same")
        env = np.sin(np.pi * t2 / t2[-1]) * 0.35
        out[s2:s2 + t2.size] += (wn * env)[: max(0, total - s2)]
        # bell ding
        s3 = int(sr * (base + TOP) / FPS)
        t3 = np.arange(int(sr * 1.2)) / sr
        ding = sum(a * np.sin(2 * np.pi * fr * t3) for fr, a in ((1320, 0.5), (2640, 0.25), (3960, 0.12), (1980, 0.2)))
        ding *= np.exp(-t3 * 3.5)
        out[s3:s3 + t3.size] += ding[: max(0, total - s3)] * 0.6
    out = np.clip(out, -1, 1)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((out * 32000).astype(np.int16).tobytes())


# ---------------------------------------------------------------- main
def render(out_dir, music="music/sports/01-sport-is-cool.mp3", music_start=160.5):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    base = static_layer()
    tgt = target_panel()
    head = header_layer()
    frames = []
    for f in range(LOOP):
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        draw_lights(d, f)
        im.alpha_composite(tgt)
        draw_target(im, f)
        draw_bell(im, f)
        draw_pad(ImageDraw.Draw(im, "RGBA"), f)
        draw_puck(im, f)
        draw_hammer(im, f)
        im.alpha_composite(head)
        draw_verdict(im, f)
        frames.append(im.convert("RGB"))
    frames[PERFECT].save(out / "check.png")
    frames[PERFECT - 3].save(out / "cover.png")

    video_only = out / "_video.mp4"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                            "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264",
                            "-pix_fmt", "yuv420p", "-crf", "18", "-preset", "medium", str(video_only)],
                           stdin=subprocess.PIPE)
    for _ in range(LOOPS):
        for fr in frames:
            enc.stdin.write(fr.tobytes())
    enc.stdin.close(); enc.wait()

    fx = out / "_fx.wav"
    synth_fx(fx, LOOP * LOOPS)
    dur = LOOP * LOOPS / FPS
    music_delay = int(1000 * (IMPACT + 2) / FPS)  # music kicks in right after the first boom
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video_only), "-i", str(fx),
                    "-ss", str(music_start), "-i", str(ROOT / music),
                    "-filter_complex",
                    f"[2:a]atrim=0:{dur},volume=0.55,adelay={music_delay}|{music_delay},afade=t=out:st={dur - 0.4}:d=0.4[m];"
                    f"[1:a]volume=1.0[f];[m][f]amix=inputs=2:normalize=0:duration=longest,atrim=0:{dur}[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", str(dur), str(out / "reel.mp4")], check=True)
    video_only.unlink(); fx.unlink()


if __name__ == "__main__":
    # sanity: only one frame per loop lands within a few px of the target
    near = [f for f in range(LOOP) if abs(puck_y(f) - TARGET_Y) < 18]
    assert near == [PERFECT], near
    render(sys.argv[1])
