"""Weigh-in scale pause-challenge Reel.

A triple-beam balance never settles: the beam rocks up and down, the readout
swings over and under the limit. On exactly ONE frame per loop the beam is
dead level, the pointer sits in the dashed zero box, and the fighter on the
pan is revealed with WINNER.

    python3 scale_pause.py posts/<name>
"""
import math, subprocess, sys, wave
from pathlib import Path
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
W, H = 1080, 1920
FPS = 30
SLOW, FAST = 40, 21          # frames for the slow rise / fast drop
LOOP = SLOW + FAST           # 61 frames, ~2 s
LOOPS = 4                    # ~8.1 s Reel
PERFECT = SLOW // 2          # level on the slow rise (frame 20)
A = 18.0                     # beam swing, degrees
LIMIT = 265.0                # heavyweight limit, lbs
LBS_PER_DEG = 0.5

FIGHTER = ROOT / "images/alexander-volkov-fighter/ufc/volkov-ufc.png"
NAME = "VOLKOV"

ANTON = str(ROOT / "fonts/Anton-Regular.ttf")
BARLOW = str(ROOT / "fonts/BarlowCondensed-ExtraBold.ttf")
BARLOW_B = str(ROOT / "fonts/BarlowCondensed-Bold.ttf")


def font(p, s):
    return ImageFont.truetype(p, s)


def text_c(d, xy, s, f, fill, stroke=0, sfill="black", anchor="mm"):
    d.text(xy, s, font=f, fill=fill, stroke_width=stroke, stroke_fill=sfill, anchor=anchor)


# ---------------------------------------------------------------- motion
def beam_angle(f):
    """Degrees, + = pointer up (over the limit). Slow rise, fast drop."""
    if f < SLOW:
        phi = math.pi * f / SLOW
    else:
        phi = math.pi + math.pi * (f - SLOW) / FAST
    return -A * math.cos(phi)


def reading(f):
    return LIMIT + beam_angle(f) * LBS_PER_DEG


# ---------------------------------------------------------------- geometry
PIV = (300, 1150)            # beam pivot
TIP_X = 1010                 # pointer tip x (level)
R_TIP = TIP_X - PIV[0]
PAN_X, PAN_Y = 270, 1040     # pan centre (top surface)


def rot(pt, ang):
    """Rotate pt about the pivot; ang in degrees, + lifts the right end."""
    a = math.radians(ang)
    x, y = pt[0] - PIV[0], pt[1] - PIV[1]
    return (PIV[0] + x * math.cos(a) + y * math.sin(a), PIV[1] - x * math.sin(a) + y * math.cos(a))


# ---------------------------------------------------------------- static art
def background():
    y, x = np.mgrid[0:H, 0:W].astype(np.float32)
    ang = np.arctan2(y - 1000, x - W / 2)
    stripes = (np.floor(ang / (math.pi / 16)) % 2).astype(np.float32)
    a = np.array([18, 120, 230], np.float32)
    b = np.array([30, 150, 250], np.float32)
    img = stripes[..., None] * a + (1 - stripes[..., None]) * b
    d = np.sqrt(((x - W / 2) / W) ** 2 + ((y - 1000) / H) ** 2)
    img *= (1 - np.clip(d - 0.2, 0, 1) * 1.1)[..., None]
    return Image.fromarray(img.clip(0, 255).astype(np.uint8)).convert("RGBA")


def header_layer():
    lay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(lay)
    d.rounded_rectangle((W / 2 - 130, 60, W / 2 + 130, 104), 22, fill=(20, 16, 30))
    text_c(d, (W / 2, 82), "WWIT MMA NEWS", font(BARLOW, 30), "white")
    f_h = font(ANTON, 104)
    text_c(d, (W / 2, 175), "PAUSE TO STOP", f_h, "white", 10, (10, 20, 50))
    text_c(d, (W / 2, 290), "VOLKOV'S SCALE", f_h, (255, 214, 0), 10, (10, 20, 50))
    d.rounded_rectangle((W / 2 - 250, 362, W / 2 + 250, 412), 25, fill=(214, 32, 45), outline="white", width=4)
    text_c(d, (W / 2, 387), "ONLY 1% CAN PAUSE PERFECTLY", font(BARLOW, 36), "white")
    return lay


def fighter_images():
    im = Image.open(FIGHTER).convert("RGBA")
    h = 560
    im = im.resize((int(im.width * h / im.height), h), Image.LANCZOS)
    sil = Image.new("RGBA", im.size, (14, 22, 48, 255))
    sil.putalpha(im.getchannel("A"))
    return im, sil


def static_layer():
    bg = background()
    d = ImageDraw.Draw(bg, "RGBA")
    # floor shadow + base body
    d.ellipse((90, 1500, 1060, 1570), fill=(0, 0, 0, 90))
    d.rounded_rectangle((110, 1395, 1050, 1530), 40, fill=(235, 238, 245), outline=(30, 40, 70), width=8)
    d.rounded_rectangle((140, 1420, 1020, 1446), 12, fill=(200, 205, 220))
    text_c(d, (580, 1488), "OFFICIAL WEIGH-IN", font(ANTON, 44), (30, 40, 70))
    # pan column
    d.rectangle((PAN_X - 26, PAN_Y + 20, PAN_X + 26, 1400), fill=(170, 175, 190), outline=(30, 40, 70), width=6)
    # pointer post with the zero window
    d.rounded_rectangle((TIP_X - 10, 905, TIP_X + 60, 1400), 16, fill=(235, 238, 245), outline=(30, 40, 70), width=6)
    for k in range(-6, 7):
        y = PIV[1] + k * 22
        w = 30 if k == 0 else 14
        d.line((TIP_X + 46 - w, y, TIP_X + 46, y), fill=(30, 40, 70), width=4 if k == 0 else 3)
    text_c(d, (TIP_X + 25, 880), "0", font(ANTON, 40), (30, 40, 70))
    # pivot housing
    d.polygon([(PIV[0] - 50, 1400), (PIV[0], PIV[1]), (PIV[0] + 50, 1400)], fill=(30, 40, 70))
    return bg


def readout_box(d, f, perfect):
    val = reading(f)
    x0, y0, x1, y1 = 590, 450, 1040, 580
    d.rounded_rectangle((x0 + 8, y0 + 10, x1 + 8, y1 + 10), 26, fill=(0, 0, 0, 110))
    d.rounded_rectangle((x0, y0, x1, y1), 26, fill=(12, 16, 26), outline=(255, 214, 0) if not perfect else (60, 255, 120), width=7)
    if perfect:
        col = (60, 255, 120)
    elif val > LIMIT:
        col = (255, 70, 80)
    else:
        col = (90, 180, 255)
    text_c(d, ((x0 + x1) / 2, (y0 + y1) / 2 - 14), f"{val:.1f} LBS", font(ANTON, 80), col)
    text_c(d, ((x0 + x1) / 2, y1 + 32), f"LIMIT {LIMIT:.0f}", font(BARLOW, 40), "white", 5, (10, 20, 50))


# ---------------------------------------------------------------- per-frame bits
def draw_beam(d, f):
    ang = beam_angle(f)
    # three beams, stacked, rotating together
    for i, (dy, th) in enumerate(((-34, 22), (0, 26), (34, 22))):
        p = [rot((PIV[0] - 110, PIV[1] + dy - th / 2), ang), rot((TIP_X - 20, PIV[1] + dy - th / 2), ang),
             rot((TIP_X - 20, PIV[1] + dy + th / 2), ang), rot((PIV[0] - 110, PIV[1] + dy + th / 2), ang)]
        d.polygon(p, fill=(250, 250, 255), outline=(30, 40, 70))
        d.line(p + [p[0]], fill=(30, 40, 70), width=5)
        for k in range(0, 16):
            x = PIV[0] + 20 + k * 42
            a_, b_ = rot((x, PIV[1] + dy - th / 2), ang), rot((x, PIV[1] + dy - th / 2 + 9), ang)
            d.line((a_, b_), fill=(30, 40, 70), width=3)
        # rider (poise); the middle one drifts with the swing
        rx = {0: 470, 1: 640 - ang * 6, 2: 820}[i]
        c = rot((rx, PIV[1] + dy), ang)
        rp = [rot((rx - 18, PIV[1] + dy - th / 2 - 10), ang), rot((rx + 18, PIV[1] + dy - th / 2 - 10), ang),
              rot((rx + 18, PIV[1] + dy + th / 2 + 10), ang), rot((rx - 18, PIV[1] + dy + th / 2 + 10), ang)]
        d.polygon(rp, fill=(255, 196, 30))
        d.line(rp + [rp[0]], fill=(120, 80, 0), width=4)
    # pointer
    tip = rot((TIP_X + 40, PIV[1]), ang)
    base_t, base_b = rot((TIP_X - 20, PIV[1] - 26), ang), rot((TIP_X - 20, PIV[1] + 26), ang)
    d.polygon([base_t, tip, base_b], fill=(214, 32, 45), outline=(30, 40, 70))
    # counterweight + pivot pin
    cw = rot((PIV[0] - 120, PIV[1]), ang)
    d.ellipse((cw[0] - 34, cw[1] - 34, cw[0] + 34, cw[1] + 34), fill=(60, 70, 100), outline=(30, 40, 70), width=5)
    d.ellipse((PIV[0] - 16, PIV[1] - 16, PIV[0] + 16, PIV[1] + 16), fill=(255, 196, 30), outline=(30, 40, 70), width=4)


def dashed_rect(d, box, color, w=6, dash=16, gap=10):
    x0, y0, x1, y1 = box
    for (ax, ay, bx, by) in ((x0, y0, x1, y0), (x0, y1, x1, y1), (x0, y0, x0, y1), (x1, y0, x1, y1)):
        L = math.hypot(bx - ax, by - ay)
        t = 0
        while t < L:
            t2 = min(t + dash, L)
            d.line((ax + (bx - ax) * t / L, ay + (by - ay) * t / L, ax + (bx - ax) * t2 / L, ay + (by - ay) * t2 / L), fill=color, width=w)
            t += dash + gap


def draw_target(d, perfect):
    box = (TIP_X - 30, PIV[1] - 34, TIP_X + 52, PIV[1] + 34)
    if perfect:
        d.rounded_rectangle((box[0] - 12, box[1] - 12, box[2] + 12, box[3] + 12), 18, fill=(60, 255, 120, 110))
        dashed_rect(d, box, (60, 255, 120), 8)
    else:
        dashed_rect(d, box, (255, 225, 0), 6)


def draw_pan(lay, f, fighter, sil, perfect):
    d = ImageDraw.Draw(lay, "RGBA")
    bob = -beam_angle(f) * 0.8          # pan dips a touch when the beam lifts
    py = PAN_Y + bob
    if perfect:  # spotlight + rays
        for i in range(18):
            a0 = math.radians(i * 20)
            a1 = a0 + math.radians(10)
            cx, cy, R = PAN_X, py - 300, 520
            d.polygon([(cx, cy), (cx + R * math.cos(a0), cy + R * math.sin(a0)), (cx + R * math.cos(a1), cy + R * math.sin(a1))],
                      fill=(255, 225, 60, 120))
    img = fighter if perfect else sil
    lay.alpha_composite(img, (int(PAN_X - img.width / 2), int(py - img.height + 70)))
    d = ImageDraw.Draw(lay, "RGBA")
    # pan (front lip hides the crop at the thighs)
    d.ellipse((PAN_X - 230, py - 26, PAN_X + 230, py + 40), fill=(205, 210, 225), outline=(30, 40, 70), width=6)
    d.rounded_rectangle((PAN_X - 230, py + 6, PAN_X + 230, py + 80), 24, fill=(235, 238, 245), outline=(30, 40, 70), width=6)
    if not perfect:
        text_c(d, (PAN_X, py - 330), "?", font(ANTON, 170), (255, 214, 0), 8, (10, 20, 50))
    else:
        text_c(d, (815, 730), "WINNER", font(ANTON, 140), (60, 255, 120), 10, (10, 20, 50))
        d.rounded_rectangle((815 - 150, 815, 815 + 150, 885), 16, fill=(214, 32, 45), outline="white", width=5)
        text_c(d, (815, 850), NAME, font(ANTON, 54), "white")


VERDICTS = {
    "perfect": [("WINNER!", "265.0 on the dot. Drago makes weight")],
    "close_under": [("SO CLOSE", "One frame light")],
    "close_over": [("JUST OVER", "Should've skipped the borscht")],
    "under": [("TOO LIGHT", "Welcome to light heavyweight, Drago"),
              ("UNDER", "Hokit's 205 plan, not Volkov's"),
              ("WAY UNDER", "Did he skip leg day too?")],
    "over": [("OVERWEIGHT", "Missed weight. Hokit's already posting"),
             ("TOO HEAVY", "One too many pelmeni"),
             ("WAY OVER", "6'7\" of pure water weight")],
}


def verdict(f):
    if f == PERFECT:
        return "perfect", 0
    if abs(f - PERFECT) == 1 or abs(beam_angle(f)) < 1.5:
        return ("close_over" if beam_angle(f) > 0 else "close_under"), 0
    return ("over" if beam_angle(f) > 0 else "under"), f // 3


def draw_verdict(lay, f):
    d = ImageDraw.Draw(lay)
    kind, k = verdict(f)
    opts = VERDICTS[kind]
    big, small = opts[k % len(opts)]
    col = {"perfect": (60, 230, 110), "under": (90, 180, 255), "close_under": (90, 180, 255),
           "over": (255, 70, 80), "close_over": (255, 70, 80)}[kind]
    y = 1680
    d.rounded_rectangle((70, y - 70, W - 70, y + 150), 34, fill=(12, 16, 30, 230), outline=col, width=6)
    text_c(d, (W / 2, y), big, font(ANTON, 104), col, 6, (10, 6, 20))
    text_c(d, (W / 2, y + 100), small, font(BARLOW_B, 46), "white")
    text_c(d, (950, 1590), f"frame {f + 1:02d}/{LOOP}", font(BARLOW_B, 34), "white", 4, (10, 20, 50))


def draw_confetti(d, f):
    rng = np.random.default_rng(3)
    cols = [(255, 214, 0), (60, 255, 120), (255, 70, 80), (255, 255, 255)]
    for i in range(70):
        x, y = rng.uniform(0, W), rng.uniform(450, 1450)
        s = rng.uniform(8, 18)
        a = rng.uniform(0, math.pi)
        c = cols[i % 4]
        d.polygon([(x + s * math.cos(a), y + s * math.sin(a)), (x - s * math.sin(a) * 0.5, y + s * math.cos(a) * 0.5),
                   (x - s * math.cos(a), y - s * math.sin(a)), (x + s * math.sin(a) * 0.5, y - s * math.cos(a) * 0.5)], fill=c)


# ---------------------------------------------------------------- audio
def synth_boom(path, n_frames):
    sr = 44100
    total = int(sr * n_frames / FPS)
    out = np.zeros(total, np.float32)
    t = np.arange(int(sr * 0.7)) / sr
    rng = np.random.default_rng(7)
    boom = np.sin(2 * np.pi * (50 + 90 * np.exp(-t * 16)) * t) * np.exp(-t * 5)
    boom += rng.normal(0, 1, t.size) * np.exp(-t * 35) * 0.5
    out[: t.size] += boom * 0.95
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr)
        w.writeframes((np.clip(out, -1, 1) * 32000).astype(np.int16).tobytes())


# ---------------------------------------------------------------- main
def render(out_dir, music="music/sports/01-sport-is-cool.mp3", music_start=160.5):
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    base = static_layer()
    head = header_layer()
    fighter, sil = fighter_images()
    frames = []
    for f in range(LOOP):
        perfect = f == PERFECT
        im = base.copy()
        d = ImageDraw.Draw(im, "RGBA")
        if perfect:
            draw_confetti(d, f)
        draw_pan(im, f, fighter, sil, perfect)
        d = ImageDraw.Draw(im, "RGBA")
        draw_target(d, perfect)
        draw_beam(d, f)
        im.alpha_composite(head)
        d = ImageDraw.Draw(im, "RGBA")
        readout_box(d, f, perfect)
        draw_verdict(im, f)
        frames.append(im.convert("RGB"))
    frames[PERFECT].save(out / "check.png")
    frames[PERFECT - 6].save(out / "cover.png")

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
    synth_boom(fx, LOOP * LOOPS)
    dur = LOOP * LOOPS / FPS
    delay = 250  # music right after the boom
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video_only), "-i", str(fx),
                    "-ss", str(music_start), "-i", str(ROOT / music),
                    "-filter_complex",
                    f"[2:a]atrim=0:{dur},volume=0.6,adelay={delay}|{delay},afade=t=out:st={dur - 0.4}:d=0.4[m];"
                    f"[m][1:a]amix=inputs=2:normalize=0:duration=longest,atrim=0:{dur}[a]",
                    "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-t", str(dur), str(out / "reel.mp4")], check=True)
    video_only.unlink(); fx.unlink()


if __name__ == "__main__":
    lvl = [f for f in range(LOOP) if abs(beam_angle(f)) < 0.5]
    assert lvl == [PERFECT], lvl
    render(sys.argv[1])
