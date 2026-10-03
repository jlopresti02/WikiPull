#!/usr/bin/env python3
"""Render a WWIT MMA News carousel (4:5 slides) from a post file.

A carousel post file has "carousel": true and a list of slides:

    {
      "carousel": true,
      "headline": "UFC 332 Results",          # for the record and the ledger
      "color": "#d2202f",                     # background for every slide
      "slides": [
        {"type": "cover", "title": "UFC 332 Results", "fighter": "Natalia Silva",
         "kicker": "New champion", "subtitle": "Silva def. Wang Cong"},
        {"type": "hook", "title": "Night Of Finishes", "fighter": "Payton Talbott",
         "kicker": "Best finish", "subtitle": "Talbott KO R1 2:11"},
        {"type": "result", "label": "Main event · Flyweight title",
         "winner": "Natalia Silva", "loser": "Wang Cong",
         "method": "Decision (unanimous)", "detail": "R5 5:00"},
        {"type": "list", "title": "Prelims",
         "rows": [["Marcus McGhee", "Anthony Romero", "KO R2"], ...]},
        {"type": "bonuses", "title": "Bonuses",
         "rows": [["Fight of the Night", "Silva vs Wang"], ...]},
        {"type": "cta", "title": "Who's next for the champ?",
         "lines": ["Comment your pick", "Follow @wwitmma for results"]}
      ],
      "caption": "...", "hashtags": [...5...], "sources": [...]
    }

Fighters are looked up the same way as Reel photos (WikiPull cutouts);
anyone without a photo gets the silhouette graphic, so a slide always
renders. Names in "fighter", "winner" and "loser" can be a list of
alternates: ["Bobby Green", "King Green"].

Output goes to posts/<post name>/:
    slide-01.jpg ... slide-NN.jpg   1080x1350 JPEGs (Instagram's carousel format)
    caption.txt                     caption + sources + photo credits + hashtags
    post.json                       the post file, for the record
"""

import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from render import (DEFAULT_COLOR, MAX_TEXT_W, POST, ROOT, Scene, TAG_SIZE, TAG_X,
                    cap_height, draw_tag, font, hex_rgb, is_light, mystery_graphic,
                    tag_width)

W, H = POST.w, POST.h


# ---------------------------------------------------------------- helpers

def ink(bg):
    return (17, 17, 17) if is_light(bg) else (255, 255, 255)


def fit_size(text, max_w, size):
    while size > 20 and font(size).getlength(text) > max_w:
        size -= 2
    return size


def text_center(d, x, y, text, size, fill):
    """Draw text with its capitals' top at y, centered on x. Returns bottom y."""
    cap = cap_height(size)
    d.text((x, y + cap), text, font=font(size), fill=fill, anchor="ms")
    return y + cap


def pill(d, cx, y, text, size, fill, color):
    text = text.upper()
    size = fit_size(text, W - 200, size)
    cap = cap_height(size)
    pad_x, pad_y = int(size * 0.55), int(size * 0.38)
    w = int(font(size).getlength(text)) + 2 * pad_x
    h = cap + 2 * pad_y
    x0 = int(cx - w / 2)
    d.rounded_rectangle([x0, y, x0 + w, y + h], radius=h // 2, fill=fill)
    d.text((cx, y + pad_y + cap), text, font=font(size), fill=color, anchor="ms")
    return y + h


def chrome(img, bg, index, total):
    """Tag, slide counter and swipe arrow shared by every slide."""
    d = ImageDraw.Draw(img)
    fg = ink(bg)
    draw_tag(d, POST, fg, bg, is_light(bg))
    counter = f"{index}/{total}"
    size = TAG_SIZE
    d.text((W - TAG_X, POST.tag_y + 35 + cap_height(size) / 2), counter,
           font=font(size), fill=fg, anchor="rs")
    if index < total:
        # swipe cue, bottom right: a circle with an arrow
        r, cx, cy = 46, W - 90, H - 90
        d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fg)
        arrow = bg if not is_light(bg) else (255, 255, 255)
        d.line([cx - 22, cy, cx + 18, cy], fill=arrow, width=9)
        d.polygon([(cx + 26, cy), (cx + 6, cy - 18), (cx + 6, cy + 18)], fill=arrow)
    return img


def names(v):
    return v if isinstance(v, list) else [v]


def last_name(full):
    parts = full.split()
    return parts[-1] if len(parts) > 1 else full


# ---------------------------------------------------------------- slides

def slide_feature(spec, bg, get_cut):
    """cover / hook: the Reel post design (big headline, big cutout) plus a
    kicker above and a subtitle pill at the bottom."""
    words = [w.upper() for w in spec["title"].split()]
    if not 1 <= len(words) <= 4:
        raise ValueError("cover/hook titles must be 1 to 4 words")
    cut, credit = get_cut(spec.get("fighter"))
    kind = "fighter" if cut is not None else "graphic"
    scene = Scene(POST, words, bg, cut, kind, "mystery")
    img = scene.frame().convert("RGBA")
    d = ImageDraw.Draw(img)
    fg = ink(bg)
    if spec.get("kicker"):
        k = spec["kicker"].upper()
        size = 34
        w = font(size).getlength(k) + 40
        x0 = TAG_X + tag_width() + 18
        d.rounded_rectangle([x0, POST.tag_y, x0 + w, POST.tag_y + 70], radius=10,
                            outline=fg, width=4)
        d.text((x0 + w / 2, POST.tag_y + 35 + cap_height(size) / 2), k,
               font=font(size), fill=fg, anchor="ms")
    if spec.get("subtitle"):
        pill_fill = (17, 17, 17) if not is_light(bg) else (255, 255, 255)
        pill(d, W / 2 - 40, H - 150, spec["subtitle"], 52, pill_fill,
             (255, 255, 255) if not is_light(bg) else (17, 17, 17))
    return img, [credit] if credit else []


def place(img, cut, cx, bottom, max_w, max_h, gray=False):
    s = min(max_w / cut.width, max_h / cut.height)
    c = cut.resize((max(1, int(cut.width * s)), max(1, int(cut.height * s))), Image.LANCZOS)
    if gray:
        a = c.getchannel("A")
        g = ImageOps.grayscale(c.convert("RGB")).point(lambda v: int(v * 0.72))
        c = Image.merge("RGBA", (g, g, g, a))
    img.alpha_composite(c, (int(cx - c.width / 2), int(bottom - c.height)))


def slide_result(spec, bg, get_cut):
    img = Image.new("RGBA", (W, H), bg + (255,))
    d = ImageDraw.Draw(img)
    fg = ink(bg)
    winner, loser = names(spec["winner"]), names(spec["loser"])
    y = 165
    if spec.get("label"):
        lab = spec["label"].upper()
        size = fit_size(lab, W - 160, 40)
        y = text_center(d, W / 2, y, lab, size, fg) + 34
    name = last_name(winner[0]).upper()
    size = fit_size(name, MAX_TEXT_W, 210)
    y = text_center(d, W / 2, y, name, size, fg) + 30
    defeat = f"DEF. {loser[0].upper()}"
    size = fit_size(defeat, MAX_TEXT_W, 64)
    y = text_center(d, W / 2, y, defeat, size, fg) + 30
    top = y
    bottom = H - 150
    credits = []
    wc, wcred = get_cut(winner)
    lc, lcred = get_cut(loser)
    room = bottom - top + 120  # cutouts may run behind the method pill
    if lc is not None:
        place(img, lc, W * 0.76, H, 600, room * 0.78, gray=True)
        if lcred:
            credits.append(lcred)
    else:
        place(img, mystery_graphic((40, 40, 40)), W * 0.72, H - 40, 440, room * 0.7, gray=True)
    if wc is not None:
        place(img, wc, W * 0.38, H, 900, room)
        if wcred:
            credits.append(wcred)
    else:
        place(img, mystery_graphic(bg), W * 0.36, H - 40, 600, room * 0.9)
    d = ImageDraw.Draw(img)
    method = spec.get("method", "").upper()
    if spec.get("detail"):
        method = f"{method} · {spec['detail'].upper()}" if method else spec["detail"].upper()
    if method:
        pill_fill = (17, 17, 17) if not is_light(bg) else (255, 255, 255)
        pill(d, W / 2 - 40, H - 150, method, 54, pill_fill,
             (255, 255, 255) if not is_light(bg) else (17, 17, 17))
    return img, credits


def slide_list(spec, bg, get_cut):
    """Rows of results (winner, loser, method) or bonuses (award, names)."""
    img = Image.new("RGBA", (W, H), bg + (255,))
    d = ImageDraw.Draw(img)
    fg = ink(bg)
    title = spec["title"].upper()
    y = text_center(d, W / 2, 175, title, fit_size(title, MAX_TEXT_W, 150), fg) + 60
    rows = spec.get("rows", [])
    if not rows:
        return img, []
    avail = H - 170 - y
    row_h = min(230, avail / len(rows))
    big = min(84, int(row_h * 0.44))
    small = int(big * 0.6)
    gap = 14
    block = len(rows) * row_h - (row_h - (cap_height(big) + gap + cap_height(small)))
    y += max(0, (avail - block) / 2 - 20)  # center the rows in the space left
    dim = tuple(int(c * 0.75 + b * 0.25) for c, b in zip(fg, bg))
    for r in rows:
        if spec.get("type") == "bonuses":
            award, who = r[0].upper(), r[1].upper()
            text_center(d, W / 2, y, award, fit_size(award, W - 160, small), dim)
            text_center(d, W / 2, y + cap_height(small) + gap, who,
                        fit_size(who, W - 160, big), fg)
        else:
            win, lose = r[0].upper(), r[1].upper()
            method = r[2].upper() if len(r) > 2 else ""
            line = f"{win}"
            sub = f"DEF. {lose}" + (f"  ·  {method}" if method else "")
            text_center(d, W / 2, y, line, fit_size(line, W - 160, big), fg)
            text_center(d, W / 2, y + cap_height(big) + gap, sub,
                        fit_size(sub, W - 160, small), dim)
        y += row_h
    return img, []


def slide_cta(spec, bg, get_cut):
    img = Image.new("RGBA", (W, H), bg + (255,))
    d = ImageDraw.Draw(img)
    fg = ink(bg)
    words = [w.upper() for w in spec["title"].split()]
    # set the question like a headline: one word per line, as big as fits
    n = len(words)
    size = 260.0
    for w in words:
        size = min(size, size * MAX_TEXT_W / max(1, font(size).getlength(w)))
    ratio = cap_height(100) / 100
    size = min(size, 760 / (ratio * (n + (n - 1) * 0.16)))
    cap = cap_height(size)
    y = 210
    for w in words:
        d.text((W / 2, y + cap), w, font=font(size), fill=fg, anchor="ms")
        y += cap * 1.16
    y += 50
    pill_fill = (17, 17, 17) if not is_light(bg) else (255, 255, 255)
    pill_ink = (255, 255, 255) if not is_light(bg) else (17, 17, 17)
    for line in spec.get("lines", ["Comment your pick", "Follow @wwitmma"]):
        y = pill(d, W / 2, y, line, 50, pill_fill, pill_ink) + 26
    return img, []


SLIDES = {"cover": slide_feature, "hook": slide_feature, "result": slide_result,
          "list": slide_list, "bonuses": slide_list, "cta": slide_cta}


# ---------------------------------------------------------------- post

def render_carousel(spec_path, get_cut):
    """get_cut(name or [names]) -> (RGBA cutout or None, credit or None)."""
    spec_path = Path(spec_path)
    spec = json.loads(spec_path.read_text())
    slides = spec.get("slides") or []
    if not 2 <= len(slides) <= 10:
        sys.exit(f"{spec_path.name}: a carousel needs 2 to 10 slides (Instagram's limit)")
    bg = hex_rgb(spec.get("color", DEFAULT_COLOR))
    out = ROOT / "posts" / spec_path.stem
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("slide-*.jpg"):
        old.unlink()
    credits = []
    for i, s in enumerate(slides, 1):
        kind = s.get("type")
        if kind not in SLIDES:
            sys.exit(f"{spec_path.name}: unknown slide type {kind!r}")
        img, cr = SLIDES[kind](s, bg, get_cut)
        chrome(img, bg, i, len(slides)).convert("RGB").save(
            out / f"slide-{i:02d}.jpg", quality=92, optimize=True)
        credits += [c for c in cr if c and c not in credits]
        print(f"Rendered posts/{spec_path.stem}/slide-{i:02d}.jpg ({kind})")

    lines = [spec["caption"].strip(), ""]
    if spec.get("sources"):
        lines.append("📰 Source: " + ", ".join(spec["sources"]))
    if credits:
        lines.append("📸 Photos: " + "; ".join(credits))
    tags = [t if t.startswith("#") else "#" + t for t in spec.get("hashtags", [])][:5]
    if tags:
        lines += ["", " ".join(tags)]
    caption = "\n".join(lines).strip() + "\n"
    if len(caption) > 2200:
        # drop photo credits to the shortest form rather than fail
        caption = caption.replace("📸 Photos: " + "; ".join(credits),
                                  "📸 Photos: Wikimedia Commons (CC licenses)")
    if len(caption) > 2200:
        sys.exit(f"{spec_path.name}: caption is {len(caption)} characters; Instagram's limit is 2200")
    (out / "caption.txt").write_text(caption)
    (out / "post.json").write_text(json.dumps({**spec, "slide_count": len(slides),
                                               "photo_credits": credits},
                                              indent=2, ensure_ascii=False) + "\n")
    return out
