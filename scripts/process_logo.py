"""emda.png → logo varyantları üretici (deterministik sütun projeksiyonu)."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "brand" / "emda.png"
IMG_DIR = ROOT / "public_html" / "assets" / "img"

CREAM = np.array([248, 244, 240], dtype=np.uint8)
ALPHA_CONTENT = 25


def is_background(r: int, g: int, b: int, a: int) -> bool:
    if a < ALPHA_CONTENT:
        return True
    if abs(int(r) - int(g)) < 18 and abs(int(g) - int(b)) < 18 and min(r, g, b) > 165:
        return True
    return False


def is_gold_color(r: int, g: int, b: int) -> bool:
    return r > 115 and g > 85 and b < 145 and (r - b) > 35 and g > b * 0.75


def is_gold(r: int, g: int, b: int, a: int) -> bool:
    if a < ALPHA_CONTENT or is_background(r, g, b, a):
        return False
    return is_gold_color(r, g, b)


def is_navy_color(r: int, g: int, b: int) -> bool:
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    return lum < 115 and b >= r * 0.55 and b > 25


def to_rgba_array(img: Image.Image) -> np.ndarray:
    return np.array(img.convert("RGBA"))


def make_transparent(arr: np.ndarray) -> np.ndarray:
    out = arr.copy()
    h, w = out.shape[:2]
    for y in range(h):
        for x in range(w):
            r, g, b, a = out[y, x]
            if is_background(int(r), int(g), int(b), int(a)):
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


def segment_columns(alpha: np.ndarray) -> list[tuple[int, int]]:
    """Sütun projeksiyonu: tamamen şeffaf sütun aralıkları ayırıcı."""
    col_max = alpha.max(axis=0)
    has_content = col_max >= ALPHA_CONTENT

    segments: list[tuple[int, int]] = []
    in_seg = False
    start = 0
    for x, filled in enumerate(has_content):
        if filled and not in_seg:
            start = x
            in_seg = True
        elif not filled and in_seg:
            segments.append((start, x))
            in_seg = False
    if in_seg:
        segments.append((start, len(has_content)))
    return segments


def crop_emblem_deterministic(logo_full: np.ndarray) -> np.ndarray:
    alpha = logo_full[:, :, 3]
    segments = segment_columns(alpha)
    if not segments:
        raise RuntimeError("İçerik segmenti bulunamadı")

    x0, x1 = segments[0]
    emblem_slice = logo_full[:, x0:x1]
    bx0, by0, bx1, by1 = content_bbox_alpha(emblem_slice, pad=2)
    cropped = emblem_slice[by0:by1, bx0:bx1]

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
            if is_navy_color(ri, gi, bi) and not is_background(ri, gi, bi, ai):
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


def assert_emblem(emblem: np.ndarray, content_height: int) -> dict[str, float]:
    m = emblem_metrics(emblem, content_height)

    if not (0.95 <= m["aspect_ratio"] <= 1.05):
        print(f"FAIL aspect_ratio={m['aspect_ratio']:.4f} (beklenen 0.95–1.05)", file=sys.stderr)
        sys.exit(1)

    if not (0.85 <= m["left_right_fill_ratio"] <= 1.15):
        print(
            f"FAIL left_right_fill_ratio={m['left_right_fill_ratio']:.4f} (beklenen 0.85–1.15)",
            file=sys.stderr,
        )
        sys.exit(1)

    if m["height_vs_content"] < 0.80:
        print(
            f"FAIL height_vs_content={m['height_vs_content']:.4f} (beklenen >= 0.80)",
            file=sys.stderr,
        )
        sys.exit(1)

    return m


def save_png(arr: np.ndarray, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(arr, "RGBA").save(path, optimize=True)


def make_icon(arr: np.ndarray, size: int) -> Image.Image:
    return Image.fromarray(arr, "RGBA").resize((size, size), Image.Resampling.LANCZOS)


def main() -> None:
    if not SRC.exists():
        print(f"FAIL kaynak yok: {SRC}", file=sys.stderr)
        sys.exit(1)

    raw = to_rgba_array(Image.open(SRC))
    transparent = make_transparent(raw)
    x0, y0, x1, y1 = content_bbox_alpha(transparent)
    logo_full = transparent[y0:y1, x0:x1]
    content_height = logo_full.shape[0]

    emblem = crop_emblem_deterministic(logo_full)
    metrics = assert_emblem(emblem, content_height)

    dark = make_dark_variant(logo_full)

    save_png(logo_full, IMG_DIR / "logo-full.png")
    save_png(dark, IMG_DIR / "logo-full-dark.png")
    save_png(emblem, IMG_DIR / "emblem.png")
    make_icon(emblem, 32).save(IMG_DIR / "favicon.png")
    make_icon(emblem, 180).save(IMG_DIR / "apple-touch-icon.png")

    print("emblem metrics:", metrics)
    print("logo-full:", logo_full.shape[1], "x", logo_full.shape[0])
    print("emblem:", emblem.shape[1], "x", emblem.shape[0])
    print("done")


if __name__ == "__main__":
    main()
