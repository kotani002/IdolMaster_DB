#!/usr/bin/env python3
"""
SNS で URL を貼ったときのカード画像 (assets/ogp.png, 1200x630) を作る。

  python scripts/make_ogp.py

- 公式のジャケットやロゴは使わない（サイト名・ブランドカラー・カードの見本だけ）。
- 要 Pillow / Windows の游ゴシック（無ければ BIZ UDゴシック・メイリオ）。
"""
from __future__ import annotations

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
W, H = 1200, 630
BG = (251, 248, 243)
INK = (42, 39, 48)
MUTED = (138, 133, 147)

FONT_CANDIDATES = {
    "bold": ["C:/Windows/Fonts/YuGothB.ttc", "C:/Windows/Fonts/BIZ-UDGothicB.ttc", "C:/Windows/Fonts/meiryob.ttc"],
    "regular": ["C:/Windows/Fonts/YuGothM.ttc", "C:/Windows/Fonts/BIZ-UDGothicR.ttc", "C:/Windows/Fonts/meiryo.ttc"],
}


def font(kind: str, size: int) -> ImageFont.FreeTypeFont:
    for p in FONT_CANDIDATES[kind]:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    raise SystemExit("日本語フォントが見つかりません")


def hex_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def tint(c, r):
    return tuple(round(v * r + 255 * (1 - r)) for v in c)


def gradient_bg(a, b) -> Image.Image:
    """左上: ブランドA の淡色 → 中央: 生成り → 右下: ブランドB の淡色"""
    img = Image.new("RGB", (W, H), BG)
    px = img.load()
    ta, tb = tint(a, 0.30), tint(b, 0.26)
    for y in range(H):
        for x in range(W):
            t = (x / W * 0.6 + y / H * 0.4)
            if t < 0.38:
                k = t / 0.38
                c = tuple(round(ta[i] * (1 - k) + BG[i] * k) for i in range(3))
            elif t > 0.62:
                k = (t - 0.62) / 0.38
                c = tuple(round(BG[i] * (1 - k) + tb[i] * k) for i in range(3))
            else:
                c = BG
            px[x, y] = c
    return img


def pill(d: ImageDraw.ImageDraw, x, y, text, bg, fg, f, pad_x=22, h=52):
    w = d.textlength(text, font=f) + pad_x * 2
    d.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=bg)
    d.text((x + pad_x, y + h / 2), text, font=f, fill=fg, anchor="lm")
    return x + w


def main() -> None:
    brands = json.loads((ROOT / "data" / "brands.json").read_text(encoding="utf-8"))
    a, b = brands[0], brands[1]
    ca, cb = hex_rgb(a["color"]), hex_rgb(b["color"])
    ia, ib = hex_rgb(a["ink"]), hex_rgb(b["ink"])

    img = gradient_bg(ca, cb)
    d = ImageDraw.Draw(img)

    # --- 左側：タイトル
    x0 = 72
    d.text((x0, 92), "IDOLM@STER 対バン", font=font("bold", 26), fill=MUTED)
    d.text((x0, 128), "楽曲プレゼンシート", font=font("bold", 76), fill=INK)
    fp = font("bold", 26)
    x = pill(d, x0, 240, a["name"], ca, ia, fp)
    d.text((x + 12, 266), "から", font=fp, fill=INK, anchor="lm")
    x = pill(d, x + 12 + d.textlength("から", font=fp) + 12, 240, b["name"], cb, ib, fp)
    d.text((x0, 316), "へのオススメ曲を、1枚の画像に。", font=font("bold", 30), fill=INK)
    d.text((x0, 372), "推し曲を選んで、プレゼン文と", font=font("regular", 24), fill=MUTED)
    d.text((x0, 406), "歌ってほしいアイドルを書くだけ。", font=font("regular", 24), fill=MUTED)

    # --- 右側：カードの見本（ジャケットはプレースホルダー）
    cx, cy, cw, ch = 690, 300, 450, 260
    shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle([cx + 4, cy + 10, cx + cw + 4, cy + ch + 10], radius=26, fill=(60, 40, 0, 28))
    img.paste(shadow, (0, 0), shadow)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([cx, cy, cx + cw, cy + ch], radius=26, fill=(255, 255, 255))
    d.rounded_rectangle([cx, cy, cx + cw, cy + 64], radius=26, fill=tint(ca, 0.2))
    d.rectangle([cx, cy + 40, cx + cw, cy + 64], fill=tint(ca, 0.2))
    d.line([cx, cy + 64, cx + cw, cy + 64], fill=tint(ca, 0.45), width=3)
    d.ellipse([cx + 22, cy + 18, cx + 50, cy + 46], fill=ca)
    d.text((cx + 36, cy + 32), "1", font=font("bold", 18), fill=ia, anchor="mm")
    d.text((cx + 64, cy + 32), "ライブで盛り上がる曲", font=font("bold", 24), fill=INK, anchor="lm")
    jx, jy, js = cx + 24, cy + 86, 150
    d.rounded_rectangle([jx, jy, jx + js, jy + js], radius=14, fill=tint(cb, 0.18))
    d.text((jx + js / 2, jy + js / 2), "♪", font=font("bold", 64), fill=tint(cb, 0.6), anchor="mm")
    tx = jx + js + 22
    d.rounded_rectangle([tx, jy + 6, tx + 210, jy + 30], radius=8, fill=(232, 228, 221))
    d.line([tx, jy + 44, cx + cw - 24, jy + 44], fill=(240, 235, 227), width=3)
    for i, wd in enumerate((230, 200, 160)):
        d.rounded_rectangle([tx, jy + 60 + i * 22, tx + wd, jy + 72 + i * 22], radius=6, fill=(238, 234, 228))
    tagy = jy + 128
    tx2 = tx
    for col in ((234, 91, 118), cb, (88, 166, 220)):
        d.rounded_rectangle([tx2, tagy, tx2 + 64, tagy + 22], radius=11, fill=col)
        tx2 += 72

    # --- 下：注記
    d.text((x0, 560), "非公式ファンメイドツール", font=font("regular", 20), fill=MUTED)

    out = ROOT / "assets" / "ogp.png"
    img.save(out, optimize=True)
    print(f"wrote {out} ({out.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
