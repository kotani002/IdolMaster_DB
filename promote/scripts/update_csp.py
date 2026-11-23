#!/usr/bin/env python3
"""
_headers のセキュリティ設定（Content-Security-Policy）を作り直す。

  python scripts/update_csp.py

index.html・view.html の <script>（src の無い、ページに直接書いたもの）を変えたら必ず実行する。
CSP は「このページで動かしてよいスクリプト」を決める設定で、直接書いたスクリプトは中身のハッシュで許可している。
中身を1文字でも変えるとハッシュが変わり、実行しないと公開サイトでそのスクリプトが動かなくなる。
"""
import base64
import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = ["index.html", "view.html"]
BEGIN, END = "# --- CSP（scripts/update_csp.py が作成。手で直さない）", "# --- CSP ここまで"


def inline_hashes() -> list[str]:
    out = []
    for p in PAGES:
        # 公開されるのはリポジトリの中身（改行は LF）。Windows の作業フォルダは CRLF のことがあるので LF にそろえて計算する
        html = (ROOT / p).read_text(encoding="utf-8").replace("\r\n", "\n")
        for m in re.finditer(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S):
            h = base64.b64encode(hashlib.sha256(m.group(1).encode("utf-8")).digest()).decode()
            if f"'sha256-{h}'" not in out:
                out.append(f"'sha256-{h}'")
    return out


def main() -> None:
    hashes = inline_hashes()
    csp = "; ".join([
        "default-src 'self'",
        # スクリプト：このサイト・画像作成の部品（html2canvas, cdnjs）・ページに直接書いたもの（ハッシュ）
        "script-src 'self' https://cdnjs.cloudflare.com " + " ".join(hashes),
        # 見た目：このサイト・Google Fonts・JavaScript から付ける色（style 属性）
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src https://fonts.gstatic.com",
        # 画像：ジャケットは公式サイトなど配信元がたくさんあるので https 全般・作った画像（blob/data）
        "img-src 'self' https: data: blob:",
        # 通信：ジャケットの読み込み（画像作成時）・画像変換サービス・iTunes の検索
        "connect-src 'self' https:",
        # 音声：Apple Music の試聴
        "media-src https://*.apple.com",
        "object-src 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        # ほかのサイトの枠（iframe）の中に表示させない
        "frame-ancestors 'none'",
    ])
    block = "\n".join([
        BEGIN,
        "/*",
        f"  Content-Security-Policy: {csp}",
        "  X-Frame-Options: DENY",
        "  X-Content-Type-Options: nosniff",
        "  Referrer-Policy: no-referrer",
        "  Permissions-Policy: camera=(), microphone=(), geolocation=()",
        END,
    ])
    f = ROOT / "_headers"
    text = f.read_text(encoding="utf-8")
    if BEGIN in text:
        text = re.sub(re.escape(BEGIN) + r".*?" + re.escape(END), block, text, flags=re.S)
    else:
        text = text.rstrip("\n") + "\n\n" + block + "\n"
    f.write_text(text, encoding="utf-8", newline="\n")
    print(f"_headers updated ({len(hashes)} inline script hashes)")


if __name__ == "__main__":
    main()
