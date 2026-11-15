#!/usr/bin/env python3
"""
ページのアイコン（ブラウザのタブ・ブックマーク・スマホのホーム画面）を作る。

  python scripts/make_icon.py

デザイン：漫画風の吹き出し。6ブランドの色で塗り分けた太い枠（濃い色の縁取りは均一な幅）、
内側は角丸の長方形、中に太い八分音符。公式ロゴ・ジャケットは使わない。

出力
  favicon.ico                 16/32/48px（サイト直下。/favicon.ico を見に来るブラウザ用）
  assets/icon-32.png          タブ用
  assets/icon-192.png         Android のホーム画面など
  assets/apple-touch-icon.png 180px。iPhone は自分で角を丸めるので、背景は四角いまま塗りつぶす
- 要 Pillow / numpy
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
N = 1024  # 大きく描いてから縮小する
CREAM = (251, 248, 243, 255)
INK = (42, 39, 48, 255)
WHITE = (255, 255, 255, 255)
# 12時から時計回り：765PRO ALLSTARS / シンデレラガールズ / ミリオンライブ！ / SideM / シャイニーカラーズ / 学園アイドルマスター
BRAND_COLORS = ["#f34f6d", "#2681c8", "#ffc30b", "#0fbe94", "#8dbbff", "#f39800"]


def hex_rgb(h: str) -> tuple[int, int, int]:
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def bubble_mask(n: int) -> Image.Image:
    """角を大きく丸めた吹き出し（左下に太く短いしっぽ）"""
    m = Image.new("L", (n, n), 0)
    d = ImageDraw.Draw(m)
    x0, y0, x1, y1 = n * 0.05, n * 0.05, n * 0.95, n * 0.79
    d.rounded_rectangle([x0, y0, x1, y1], radius=n * 0.27, fill=255)
    d.polygon([(n * 0.20, y1 - n * 0.08), (n * 0.44, y1 - n * 0.06), (n * 0.12, n * 0.96)], fill=255)
    return m


def erode(mask: Image.Image, d: int) -> Image.Image:
    """mask を d ピクセル均一に内側へ縮める（四角と十字を交互に使う八角形の侵食＝ほぼ円形なので角でも幅がそろう）"""
    a = np.array(mask) > 127
    for i in range(d):
        p = np.pad(a, 1, constant_values=False)
        b = a & p[:-2, 1:-1] & p[2:, 1:-1] & p[1:-1, :-2] & p[1:-1, 2:]
        if i % 2:
            b &= p[:-2, :-2] & p[:-2, 2:] & p[2:, :-2] & p[2:, 2:]
        a = b
    return Image.fromarray((a * 255).astype("uint8"), "L")


def bez(p0, p1, p2, t):
    return ((1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t * t * p2[0],
            (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t * t * p2[1])


def chunky_note(img: Image.Image, cx: float, cy: float, s: float) -> None:
    """太い八分音符（傾いた楕円の玉＋白い光、太い符尾、太くカーブした旗）"""
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    hw, hh = s * 0.30, s * 0.22
    head = Image.new("RGBA", (int(hw * 2.6), int(hw * 2.6)), (0, 0, 0, 0))
    hd = ImageDraw.Draw(head)
    c = head.width / 2
    hd.ellipse([c - hw, c - hh, c + hw, c + hh], fill=INK)
    hd.ellipse([c - hw * 0.55, c - hh * 0.55, c - hw * 0.15, c - hh * 0.05], fill=(255, 255, 255, 230))
    head = head.rotate(22, resample=Image.BICUBIC)
    hx, hy = cx - s * 0.12, cy + s * 0.30
    layer.alpha_composite(head, (int(hx - head.width / 2), int(hy - head.height / 2)))
    sw = s * 0.11
    stem_x = hx + hw * 0.78
    top = cy - s * 0.42
    d.rounded_rectangle([stem_x - sw, top, stem_x, hy - hh * 0.2], radius=sw * 0.4, fill=INK)
    a0, a2 = (stem_x - sw * 0.5, top), (stem_x + s * 0.22, top + s * 0.50)
    pts = [bez(a0, (stem_x + s * 0.30, top + s * 0.10), a2, t / 24) for t in range(25)]
    pts += [bez(a2, (stem_x + s * 0.13, top + s * 0.26), (stem_x - sw * 0.5, top + s * 0.17), t / 24) for t in range(25)]
    d.polygon(pts, fill=INK)
    img.alpha_composite(layer)


def draw(square_bg: bool = False) -> Image.Image:
    img = Image.new("RGBA", (N, N), (0, 0, 0, 0))
    bg = Image.new("L", (N, N), 0)
    if square_bg:
        bg.paste(255, (0, 0, N, N))
    else:
        ImageDraw.Draw(bg).rounded_rectangle([0, 0, N - 1, N - 1], radius=N * 0.22, fill=255)
    img.paste(Image.new("RGBA", (N, N), CREAM), (0, 0), bg)

    # 6色の扇形（中心から角度で塗り分け）
    cx, cy = N / 2, N * 0.41
    yy, xx = np.mgrid[0:N, 0:N]
    ang = (np.degrees(np.arctan2(yy - cy, xx - cx)) + 90 + 360) % 360
    idx = (ang // (360 / len(BRAND_COLORS))).astype(int) % len(BRAND_COLORS)
    pal = np.array([hex_rgb(h) + (255,) for h in BRAND_COLORS], dtype=np.uint8)
    ring = Image.fromarray(pal[idx], "RGBA")

    line = int(N * 0.026)  # 濃い縁取りの太さ（外側・内側とも同じ）
    band = N * 0.095       # 色の帯
    outer = bubble_mask(N)
    color = erode(outer, line)
    x0, y0, x1, y1 = N * 0.05 + line + band, N * 0.05 + line + band, N * 0.95 - line - band, N * 0.79 - line - band
    r = N * 0.27 - line - band
    inner_line = Image.new("L", (N, N), 0)
    ImageDraw.Draw(inner_line).rounded_rectangle([x0, y0, x1, y1], radius=r, fill=255)
    white = Image.new("L", (N, N), 0)
    ImageDraw.Draw(white).rounded_rectangle([x0 + line, y0 + line, x1 - line, y1 - line], radius=r - line, fill=255)

    img.paste(Image.new("RGBA", (N, N), INK), (0, 0), outer)
    img.paste(ring, (0, 0), color)
    img.paste(Image.new("RGBA", (N, N), INK), (0, 0), inner_line)
    img.paste(Image.new("RGBA", (N, N), WHITE), (0, 0), white)
    chunky_note(img, N * 0.50, N * 0.40, N * 0.34)
    return img


def main() -> None:
    icon = draw()
    sized = lambda im, s: im.resize((s, s), Image.LANCZOS)
    (ROOT / "assets").mkdir(exist_ok=True)
    sized(icon, 32).save(ROOT / "assets" / "icon-32.png", optimize=True)
    sized(icon, 192).save(ROOT / "assets" / "icon-192.png", optimize=True)
    sized(draw(square_bg=True), 180).convert("RGB").save(ROOT / "assets" / "apple-touch-icon.png", optimize=True)
    sized(icon, 256).save(ROOT / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    for p in ["favicon.ico", "assets/icon-32.png", "assets/icon-192.png", "assets/apple-touch-icon.png"]:
        print(f"wrote {p} ({(ROOT / p).stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
