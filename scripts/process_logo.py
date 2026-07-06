"""emda.png → logo varyantları üretici."""
from __future__ import annotations

from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "brand" / "emda.png"
BRAND_DIR = ROOT / "docs" / "brand"
IMG_DIR = ROOT / "public_html" / "assets" / "img"

CREAM = np.array([248, 244, 240], dtype=np.uint8)


def is_background(r: int, g: int, b: int, a: int) -> bool:
    if a < 25:
        return True
    # Şeffaflık yerine gömülü dama tahtası / açık gri zemin
    if abs(int(r) - int(g)) < 18 and abs(int(g) - int(b)) < 18 and min(r, g, b) > 165:
        return True
    return False


def is_gold_color(r: int, g: int, b: int) -> bool:
    return r > 115 and g > 85 and b < 145 and (r - b) > 35 and g > b * 0.75


def is_gold(r: int, g: int, b: int, a: int) -> bool:
    if a < 25 or is_background(r, g, b, a):
        return False
    return is_gold_color(r, g, b)


def is_navy_color(r: int, g: int, b: int) -> bool:
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return lum < 115 and b >= r * 0.55 and b > 25


def is_navy(r: int, g: int, b: int, a: int) -> bool:
    if a < 25 or is_background(r, g, b, a) or is_gold(r, g, b, a):
        return False
    return is_navy_color(r, g, b)


def to_rgba_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGBA"))


def content_bbox(arr: np.ndarray, pad: int = 4) -> tuple[int, int, int, int]:
    h, w = arr.shape[:2]
    mask = np.zeros((h, w), dtype=bool)
    for y in range(h):
        for x in range(w):
            r, g, b, a = arr[y, x]
            if not is_background(int(r), int(g), int(b), int(a)):
                mask[y, x] = True
    ys, xs = np.where(mask)
    if len(xs) == 0:
        return 0, 0, w, h
    return (
        max(0, int(xs.min()) - pad),
        max(0, int(ys.min()) - pad),
        min(w, int(xs.max()) + pad + 1),
        min(h, int(ys.max()) + pad + 1),
    )


def make_transparent(arr: np.ndarray) -> np.ndarray:
    out = arr.copy()
    h, w = out.shape[:2]
    for y in range(h):
        for x in range(w):
            r, g, b, a = out[y, x]
            if is_background(int(r), int(g), int(b), int(a)):
                out[y, x] = (0, 0, 0, 0)
    return out


def make_dark_variant(arr: np.ndarray) -> np.ndarray:
    out = arr.copy()
    h, w = out.shape[:2]
    for y in range(h):
        for x in range(w):
            r, g, b, a = out[y, x]
            ri, gi, bi, ai = int(r), int(g), int(b), int(a)
            if ai < 25:
                continue
            if is_gold(ri, gi, bi, ai) or is_gold_color(ri, gi, bi):
                continue
            # Tam opak ve yarı şeffaf lacivert kenar pikselleri kreme çevir
            if is_navy_color(ri, gi, bi) and not is_background(ri, gi, bi, ai):
                out[y, x] = (CREAM[0], CREAM[1], CREAM[2], ai)
    return out


def find_divider_x(arr: np.ndarray) -> int:
    """Dikey altın ayraç sütununu bul."""
    h, w = arr.shape[:2]
    y0, y1 = int(h * 0.15), int(h * 0.85)
    best_x, best_score = w // 3, 0
    for x in range(int(w * 0.18), int(w * 0.45)):
        score = 0
        for y in range(y0, y1):
            r, g, b, a = arr[y, x]
            if is_gold(int(r), int(g), int(b), int(a)):
                score += 1
        if score > best_score:
            best_score = score
            best_x = x
    return best_x


def crop_emblem(arr: np.ndarray) -> np.ndarray:
    divider_x = find_divider_x(arr)
    pad = 6
    emblem = arr[:, : max(divider_x - pad, 1)]
    x0, y0, x1, y1 = content_bbox(emblem, pad=2)
    cropped = emblem[y0:y1, x0:x1]
    ch, cw = cropped.shape[:2]
    size = max(ch, cw)
    square = np.zeros((size, size, 4), dtype=np.uint8)
    oy = (size - ch) // 2
    ox = (size - cw) // 2
    square[oy : oy + ch, ox : ox + cw] = cropped
    return square


def save_png(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path, optimize=True)


def make_icon(arr: np.ndarray, size: int) -> Image.Image:
    img = Image.fromarray(arr, "RGBA")
    return img.resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)
    IMG_DIR.mkdir(parents=True, exist_ok=True)

    # Orijinal kaynak
    if not SRC.exists():
        raise FileNotFoundError(f"Logo kaynağı bulunamadı: {SRC}")

    archive = BRAND_DIR / "emda.png"
    if not archive.exists():
        Image.open(SRC).save(archive)

    raw = to_rgba_array(Image.open(SRC))
    transparent = make_transparent(raw)
    x0, y0, x1, y1 = content_bbox(transparent)
    logo_full = transparent[y0:y1, x0:x1]

    dark = make_dark_variant(logo_full)
    emblem = crop_emblem(logo_full)

    save_png(logo_full, IMG_DIR / "logo-full.png")
    save_png(dark, IMG_DIR / "logo-full-dark.png")
    save_png(emblem, IMG_DIR / "emblem.png")

    emblem_img = Image.fromarray(emblem, "RGBA")
    make_icon(emblem, 32).save(IMG_DIR / "favicon.png")
    make_icon(emblem, 180).save(IMG_DIR / "apple-touch-icon.png")

    print("logo-full:", logo_full.shape[1], "x", logo_full.shape[0])
    print("emblem:", emblem.shape[1], "x", emblem.shape[0])
    print("done")


if __name__ == "__main__":
    main()
