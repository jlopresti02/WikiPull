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
from pathlib import Path

from PIL import Image
from rembg import new_session, remove

IMAGES_DIR = Path(__file__).resolve().parent / "images"
PHOTO_TYPES = {".jpg", ".jpeg", ".png", ".webp"}
MODEL = "u2net_human_seg"  # tuned for people, which is what fighter photos are


def cut_folder(folder, session):
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
        with Image.open(photo) as im:
            result = remove(im.convert("RGB"), session=session, post_process_mask=True)
        box = result.getbbox()  # crop away the empty transparent margin
        if box:
            result = result.crop(box)
        result.save(dest)
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
    session = new_session(MODEL)
    total = sum(cut_folder(f, session) for f in folders)
    print(f"Done: {total} new cutout(s).")


if __name__ == "__main__":
    main()
