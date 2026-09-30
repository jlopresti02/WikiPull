#!/usr/bin/env python3
"""Make transparent cutouts of the fighter in each fetched photo.

Usage:
    python cutout.py                      # every image folder that lacks cutouts
    python cutout.py images/jiri-prochazka

For images/<slug>/01-name.jpg this writes images/<slug>/cutouts/01-name.png:
the person with the background removed, cropped to the person, ready to drop
onto the MMA news post template. Needs: pip install "rembg[cpu]"
"""

import sys
import traceback
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

IMAGES_DIR = Path(__file__).resolve().parent / "images"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
# BiRefNet portrait: sharp edges on people, and it leaves out chairs, mics and
# backdrop decor. Falls back to the smaller people model if it can't load.
MODELS = ["birefnet-portrait", "u2net_human_seg"]
FADE = 0.14  # share of the width/height used to fade a frame-chopped edge


def keep_main_shape(a):
    """Drop stray blobs of leftover background: keep only the biggest shape
    (the fighter) plus anything large that touches it."""
    import cv2

    solid = (a > 0.3).astype(np.uint8)
    count, labels, stats, _ = cv2.connectedComponentsWithStats(solid, connectivity=8)
    if count <= 2:
        return a
    areas = stats[1:, cv2.CC_STAT_AREA]
    biggest = 1 + int(areas.argmax())
    keep = labels == biggest
    # Grow the kept area a little so soft edges around it survive.
    keep = cv2.dilate(keep.astype(np.uint8), np.ones((9, 9), np.uint8)) > 0
    return a * keep


def finish(cut):
    """Clean up a raw cutout so it sits naturally on a solid background.

    1. Shrink the mask slightly and soften it, which removes the thin halo of
       the old background (e.g. a blue fringe) around hair, ears and shoulders.
    2. Where the fighter ran into the photo's left, right or top border, the
       body ends in a hard straight line. Fade those edges out instead. The
       bottom edge is left alone: it sits on the bottom of the post.
    """
    cut = cut.convert("RGBA")
    alpha = cut.getchannel("A").filter(ImageFilter.MinFilter(5))
    alpha = alpha.filter(ImageFilter.GaussianBlur(1.2))
    a = np.asarray(alpha, dtype=np.float32) / 255.0
    a = keep_main_shape(a)
    h, w = a.shape

    def ramp(n):  # 0 at the border rising smoothly to 1
        t = np.linspace(0.0, 1.0, n, dtype=np.float32)
        return t * t * (3 - 2 * t)

    for side in ("left", "right", "top"):
        edge = {"left": a[:, 0], "right": a[:, -1], "top": a[0, :]}[side]
        touching = np.where(edge > 0.5)[0]
        if len(touching) < 8:
            continue  # subject doesn't meaningfully touch this border
        if side == "top":
            n = max(8, int(h * FADE))
            a[:n, :] *= ramp(n)[:, None]
            continue
        n = max(8, int(w * FADE))
        # Only fade the rows near and below where the body hits the border,
        # easing in over n rows so the fade doesn't start with a hard line.
        mask_rows = np.zeros(h, dtype=np.float32)
        start = touching.min()
        mask_rows[start:] = 1.0
        lead = min(n, start)
        if lead:
            mask_rows[start - lead:start] = ramp(lead)
        cols = 1.0 - (1.0 - ramp(n))[None, :] * mask_rows[:, None]
        if side == "left":
            a[:, :n] *= cols
        else:
            a[:, -n:] *= cols[:, ::-1]

    cut.putalpha(Image.fromarray((a * 255).clip(0, 255).astype(np.uint8)))
    box = cut.getbbox()
    return cut.crop(box) if box else cut


def cut_folder(folder, session):
    from rembg import remove

    out_dir = folder / "cutouts"
    photos = sorted(p for p in folder.iterdir() if p.suffix.lower() in PHOTO_TYPES)
    if not photos:
        return 0
    out_dir.mkdir(exist_ok=True)
    made = 0
    for photo in photos:
        dest = out_dir / (photo.stem + ".png")
        if dest.exists() and dest.stat().st_mtime >= photo.stat().st_mtime:
            continue  # already cut, and the photo hasn't changed since
        try:
            with Image.open(photo) as im:
                result = remove(im.convert("RGB"), session=session, post_process_mask=True)
            result = finish(result)  # still photo-sized here, so real borders are detected
            result.save(dest)
        except Exception:
            # One bad photo shouldn't stop the rest; the log says what went wrong.
            print(f"  FAILED {photo.name}:", file=sys.stderr)
            traceback.print_exc()
            continue
        made += 1
        print(f"  cutout {dest.relative_to(IMAGES_DIR.parent)}")
    # Drop cutouts whose source photo is gone (e.g. after a refetch).
    names = {p.stem for p in photos}
    for old in out_dir.glob("*.png"):
        if old.stem not in names:
            old.unlink()
    return made


def main():
    if sys.argv[1:]:
        folders = [Path(a) for a in sys.argv[1:]]
    elif IMAGES_DIR.exists():
        folders = sorted(p for p in IMAGES_DIR.iterdir() if p.is_dir())
    else:
        folders = []
    if not folders:
        print("No image folders to process.")
        return
    from rembg import new_session

    session = None
    for model in MODELS:
        try:
            session = new_session(model)
            print(f"Using background-removal model: {model}")
            break
        except Exception as exc:
            print(f"  could not load {model}: {exc}", file=sys.stderr)
    if session is None:
        sys.exit("No background-removal model could be loaded.")
    total = sum(cut_folder(f, session) for f in folders)
    print(f"Done: {total} new cutout(s).")


if __name__ == "__main__":
    main()
