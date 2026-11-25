#!/usr/bin/env python3
"""
ジャケットが未設定の曲に表示する「NOW PRINTING...」画像 (assets/now_printing.png, 600x600) を作る。

  python scripts/make_now_printing.py

- シンプルなデザイン：無地の背景の中央に「NOW PRINTING...」と、その下に小さく「ジャケット準備中」。
- どのブランドの曲にも使うので、ブランドカラーは使わない落ち着いた色にする。
- 作り直したら app.js の NOW_PRINTING の ?v= を変える（ブラウザに古い画像が残らないように）。
- 要 Pillow / Windows の游ゴシック（無ければ BIZ UDゴシック・メイリオ）。
"""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "now_printing.png"
SIZE = 600
S = 2  # 2倍で描いて縮小（文字をなめらかにする）

BG = (241, 237, 230)
TEXT = (150, 145, 158)
SUB = (170, 165, 176)

FONT_CANDIDATES = ["C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/BIZ-UDGothicB.ttc", "C:/Windows/Fonts/meiryob.ttc"]
FONT_CANDIDATES_R = ["C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/BIZ-UDGothicR.ttc", "C:/Windows/Fonts/meiryo.ttc"]


def font(cands: list[str], size: int) -> ImageFont.FreeTypeFont:
    for p in cands:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("日本語フォントが見つかりません")


def spaced_text(d: ImageDraw.ImageDraw, cx: float, cy: float, text: str, f, fill, spacing: float) -> None:
    """字間を空けて、上下左右とも中央に描く"""
    widths = [d.textlength(ch, font=f) for ch in text]
    total = sum(widths) + spacing * (len(text) - 1)
    x = cx - total / 2
    for ch, w in zip(text, widths):
        d.text((x, cy), ch, font=f, fill=fill, anchor="lm")
        x += w + spacing


def main() -> None:
    W = SIZE * S
    img = Image.new("RGB", (W, W), BG)
    d = ImageDraw.Draw(img)
    # 2行（英語＋日本語）でまとまりとして中央に来るよう、少し上下に分ける
    spaced_text(d, W / 2, W * 0.47, "NOW PRINTING...", font(FONT_CANDIDATES, 44 * S), TEXT, 4 * S)
    spaced_text(d, W / 2, W * 0.555, "ジャケット準備中", font(FONT_CANDIDATES_R, 24 * S), SUB, 3 * S)
    img = img.resize((SIZE, SIZE), Image.LANCZOS)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, optimize=True)
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
