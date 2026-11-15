#!/usr/bin/env python3
"""
ジャケットが未設定の曲に表示する「NOW PRINTING...」画像 (assets/now_printing.png, 600x600) を作る。

  python scripts/make_now_printing.py

- どのブランドの曲にも使うので、ブランドカラーは使わない落ち着いた色にする。
- 要 Pillow / Windows の游ゴシック（無ければ BIZ UDゴシック・メイリオ）。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "now_printing.png"
SIZE = 600
S = 2  # 2倍で描いて縮小（円・文字をなめらかにする）

BG_TOP = (246, 243, 237)
BG_BOTTOM = (236, 231, 222)
DISC = (226, 220, 210)
DISC_RING = (214, 207, 196)
DISC_SHINE = (238, 234, 227)
HOLE_RING = (205, 198, 186)
TEXT = (138, 133, 147)
SUB = (168, 162, 172)

FONT_CANDIDATES = ["C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/BIZ-UDGothicB.ttc", "C:/Windows/Fonts/meiryob.ttc"]
FONT_CANDIDATES_R = ["C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/BIZ-UDGothicR.ttc", "C:/Windows/Fonts/meiryo.ttc"]


def font(cands: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in cands:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("日本語フォントが見つかりません")


def spaced_text(d: ImageDraw.ImageDraw, cx: float, y: float, text: str, f, fill, spacing: float) -> None:
    """字間を空けて中央揃えで描く"""
    widths = [d.textlength(ch, font=f) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        d.text((x, y), ch, font=f, fill=fill, anchor="ls")
        x += w + spacing


def main() -> None:
    W = SIZE * S
    img = Image.new("RGB", (W, W), BG_TOP)
    d = ImageDraw.Draw(img)
    for y in range(W):  # 上から下へうっすらグラデーション
        t = y / (W - 1)
        d.line([(0, y), (W, y)], fill=tuple(round(BG_TOP[i] * (1 - t) + BG_BOTTOM[i] * t) for i in range(3)))

    # CD のシルエット
    cx, cy, r = W / 2, W * 0.42, W * 0.30
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=DISC)
    for k in (0.92, 0.80, 0.68, 0.56):  # 溝
        rr = r * k
        d.ellipse([cx - rr, cy - rr, cx + rr, cy + rr], outline=DISC_RING, width=S * 2)
    # 光の反射（左上に細い弧）
    d.arc([cx - r * 0.86, cy - r * 0.86, cx + r * 0.86, cy + r * 0.86], 200, 250, fill=DISC_SHINE, width=S * 10)
    # 中心
    rh = r * 0.30
    d.ellipse([cx - rh, cy - rh, cx + rh, cy + rh], fill=BG_TOP, outline=HOLE_RING, width=S * 3)
    rh2 = r * 0.11
    d.ellipse([cx - rh2, cy - rh2, cx + rh2, cy + rh2], fill=BG_BOTTOM, outline=HOLE_RING, width=S * 2)

    # 文字
    spaced_text(d, W / 2, W * 0.86, "NOW PRINTING...", font(FONT_CANDIDATES, 46 * S), TEXT, 4 * S)
    spaced_text(d, W / 2, W * 0.935, "ジャケット準備中", font(FONT_CANDIDATES_R, 22 * S), SUB, 3 * S)

    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
