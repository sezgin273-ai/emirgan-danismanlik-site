"""emblem-source.png → emblem.png + emblem-dark.png (hero amblemi)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "brand" / "emblem-source.png"
IMG_DIR = ROOT / "public_html" / "assets" / "img"

CREAM = np.array([248, 244, 240], dtype=np.uint8)
NAVY_CENTER = (16, 24, 44)
NAVY_TOL = 25
ALPHA_CONTENT = 25


def is_checkerboard(r: int, g: int, b: int, a: int) -> bool:
    if a < ALPHA_CONTENT:
        return True
    if abs(int(r) - int(g)) < 18 and abs(int(g) - int(b)) < 18 and min(r, g, b) > 165:
        return True
    return False


def is_gold_color(r: int, g: int, b: int) -> bool:
    return r > 115 and g > 85 and b < 145 and (r - b) > 35 and g > b * 0.75


def is_gold(r: int, g: int, b: int, a: int) -> bool:
    if a < ALPHA_CONTENT or is_checkerboard(r, g, b, a):
        return False
    return is_gold_color(r, g, b)


def is_navy_color(r: int, g: int, b: int) -> bool:
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return lum < 115 and b >= r * 0.55 and b > 25


def is_navy_band(r: int, g: int, b: int, a: int, tol: int = NAVY_TOL) -> bool:
    if a < ALPHA_CONTENT:
        return False
    return all(abs(int(c) - n) <= tol for c, n in zip((r, g, b), NAVY_CENTER))


def to_rgba_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGBA"))


def clean_transparency(arr: np.ndarray) -> np.ndarray:
    out = arr.copy()
    h, w = out.shape[:2]
    for y in range(h):
        for x in range(w):
            r, g, b, a = out[y, x]
            if is_checkerboard(int(r), int(g), int(b), int(a)):
                out[y, x] = (0, 0, 0, 0)
    return out


def content_bbox_alpha(arr: np.ndarray, pad: int = 4) -> tuple[int, int, int, int]:
    alpha = arr[:, :, 3]
    ys, xs = np.where(alpha >= ALPHA_CONTENT)
    if len(xs) == 0:
        h, w = arr.shape[:2]
        return 0, 0, w, h
    return (
        max(0, int(xs.min()) - pad),
        max(0, int(ys.min()) - pad),
        min(arr.shape[1], int(xs.max()) + pad + 1),
        min(arr.shape[0], int(ys.max()) + pad + 1),
    )


def crop_to_square_emblem(arr: np.ndarray) -> np.ndarray:
    x0, y0, x1, y1 = content_bbox_alpha(arr, pad=2)
    cropped = arr[y0:y1, x0:x1]
    ch, cw = cropped.shape[:2]
    size = max(ch, cw)
    square = np.zeros((size, size, 4), dtype=np.uint8)
    oy = (size - ch) // 2
    ox = (size - cw) // 2
    square[oy : oy + ch, ox : ox + cw] = cropped
    return square


def make_dark_variant(arr: np.ndarray) -> np.ndarray:
    out = arr.copy()
    h, w = out.shape[:2]
    for y in range(h):
        for x in range(w):
            r, g, b, a = out[y, x]
            ri, gi, bi, ai = int(r), int(g), int(b), int(a)
            if ai < ALPHA_CONTENT:
                continue
            if is_gold(ri, gi, bi, ai) or is_gold_color(ri, gi, bi):
                continue
            if is_navy_color(ri, gi, bi) and not is_checkerboard(ri, gi, bi, ai):
                out[y, x] = (CREAM[0], CREAM[1], CREAM[2], ai)
    return out


def emblem_metrics(emblem: np.ndarray, content_height: int) -> dict[str, float]:
    alpha = emblem[:, :, 3]
    mask = alpha >= ALPHA_CONTENT
    ys, xs = np.where(mask)
    if len(xs) == 0:
        raise RuntimeError("Amblem maskesi boş")

    w = int(xs.max() - xs.min() + 1)
    h = int(ys.max() - ys.min() + 1)
    aspect = w / h if h else 0.0

    mid = emblem.shape[1] // 2
    left = int(mask[:, :mid].sum())
    right = int(mask[:, mid:].sum())
    lr_ratio = left / right if right else 0.0

    height_ratio = h / content_height if content_height else 0.0

    return {
        "aspect_ratio": aspect,
        "left_right_fill_ratio": lr_ratio,
        "height_vs_content": height_ratio,
        "bbox_width": w,
        "bbox_height": h,
    }


def cleaning_metrics(cleaned: np.ndarray) -> dict[str, int | float]:
    h, w = cleaned.shape[:2]
    corners = [
        cleaned[0, 0, 3],
        cleaned[0, w - 1, 3],
        cleaned[h - 1, 0, 3],
        cleaned[h - 1, w - 1, 3],
    ]
    x0, y0, x1, y1 = content_bbox_alpha(cleaned)
    mask = np.zeros((h, w), dtype=bool)
    mask[y0:y1, x0:x1] = True
    alpha = cleaned[:, :, 3]
    outside_opaque = int(np.sum((alpha >= ALPHA_CONTENT) & ~mask))
    return {
        "corner_alphas": [int(a) for a in corners],
        "opaque_outside_bbox": outside_opaque,
    }


def dark_navy_band_count(arr: np.ndarray) -> int:
    h, w = arr.shape[:2]
    count = 0
    for y in range(h):
        for x in range(w):
            r, g, b, a = arr[y, x]
            if is_navy_band(int(r), int(g), int(b), int(a)):
                count += 1
    return count


def assert_emblem(emblem: np.ndarray, content_height: int) -> dict[str, float]:
    m = emblem_metrics(emblem, content_height)
    if not (0.95 <= m["aspect_ratio"] <= 1.05):
        print(f"FAIL aspect_ratio={m['aspect_ratio']:.4f}", file=sys.stderr)
        sys.exit(1)
    if not (0.85 <= m["left_right_fill_ratio"] <= 1.15):
        print(f"FAIL left_right_fill_ratio={m['left_right_fill_ratio']:.4f}", file=sys.stderr)
        sys.exit(1)
    if m["height_vs_content"] < 0.80:
        print(f"FAIL height_vs_content={m['height_vs_content']:.4f}", file=sys.stderr)
        sys.exit(1)
    return m


def assert_cleaning(cleaned: np.ndarray) -> dict:
    m = cleaning_metrics(cleaned)
    if any(a != 0 for a in m["corner_alphas"]):
        print(f"FAIL corner_alphas={m['corner_alphas']}", file=sys.stderr)
        sys.exit(1)
    if m["opaque_outside_bbox"] != 0:
        print(f"FAIL opaque_outside_bbox={m['opaque_outside_bbox']}", file=sys.stderr)
        sys.exit(1)
    return m


def save_png(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path, optimize=True)


def main() -> None:
    if not SRC.exists():
        print(f"FAIL kaynak yok: {SRC}", file=sys.stderr)
        sys.exit(1)

    raw = to_rgba_array(Image.open(SRC))
    cleaned = clean_transparency(raw)
    assert_cleaning(cleaned)

    x0, y0, x1, y1 = content_bbox_alpha(cleaned)
    content_height = y1 - y0

    emblem = crop_to_square_emblem(cleaned)
    metrics = assert_emblem(emblem, content_height)

    emblem_dark = make_dark_variant(emblem)
    navy_remaining = dark_navy_band_count(emblem_dark)
    if navy_remaining != 0:
        print(f"FAIL emblem_dark navy_band_pixels={navy_remaining}", file=sys.stderr)
        sys.exit(1)

    save_png(emblem, IMG_DIR / "emblem.png")
    save_png(emblem_dark, IMG_DIR / "emblem-dark.png")

    print("cleaning:", cleaning_metrics(cleaned))
    print("emblem metrics:", metrics)
    print("emblem_dark navy_band_pixels:", navy_remaining)
    print("emblem:", emblem.shape[1], "x", emblem.shape[0])
    print("done")


if __name__ == "__main__":
    main()
