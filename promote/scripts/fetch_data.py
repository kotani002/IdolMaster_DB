#!/usr/bin/env python3
"""
ふじわらはじめAPI から楽曲・アイドル情報を取得して data/ 以下の JSON を生成する。

  python scripts/fetch_data.py

- 依存ライブラリなし（Python 3.9+ 標準ライブラリのみ）
- データ: アイマス楽曲DB ふじわらはじめ (https://fujiwarahaji.me) / CC BY-NC 4.0
- 先方の案内 (https://fujiwarahaji.me/llms.txt) に従い、API経由・独自UserAgent・
  リクエスト間隔を空けて取得する。
"""
from __future__ import annotations

import html
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
UA = "imas-presen-sheet/1.0 (fan-made static site; data fetch script)"
API = "https://api.fujiwarahaji.me/v4"
WAIT_SEC = 1.5

# サイトで扱うブランド。追加するときはここと data/brands.json に足す。
BRANDS = {
    "ml": {
        "music_type": "ml",       # 楽曲の種類（API music_type）
        "production": "765",      # 歌唱予想メンバーに使うアイドルの所属
        "sitemap": "765pro",      # パーソナルカラー取得用ページ
    },
    "cg": {
        "music_type": "cg",
        "production": "cg",
        "sitemap": "cg",
    },
}

# 765プロ内のグループ分け（ミリオン以外のアイドルを区別するため）
AS_765 = {
    "天海春香", "如月千早", "星井美希", "萩原雪歩", "高槻やよい", "菊地真", "水瀬伊織",
    "四条貴音", "秋月律子", "三浦あずさ", "双海亜美", "双海真美", "我那覇響",
}


def get(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            time.sleep(WAIT_SEC)
            return body
        except Exception as e:  # 503 などは少し待って再試行
            wait = 5 * (attempt + 1)
            print(f"  ! {e} -> retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    raise RuntimeError(f"failed: {url}")


def get_json(url: str):
    return json.loads(get(url).decode("utf-8"))


def kana_map(brand_music_type: str) -> dict[str, str]:
    """IMEデータ（タブ区切り: よみ / 単語 / 品詞）から 曲名 -> よみ を作る。"""
    q = urllib.parse.urlencode({"enc": "utf8", "types": "music", "brand": brand_music_type})
    text = get(f"https://fujiwarahaji.me/api/ime/main?{q}").decode("utf-8", "replace")
    m: dict[str, str] = {}
    for line in text.splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0] and cols[1]:
            m.setdefault(cols[1].strip(), cols[0].strip())
    return m


def idol_colors(sitemap: str) -> dict[str, str]:
    """アイドル一覧ページ（1リクエスト）から 名前 -> パーソナルカラー を作る。"""
    page = get(f"https://fujiwarahaji.me/sitemap/idol/{sitemap}").decode("utf-8", "replace")
    out: dict[str, str] = {}
    for card in re.findall(r'<div class="[^"]*idol_card.*?</a>', page, re.S):
        color = re.search(r"background:\s*(#[0-9a-fA-F]{3,8})", card)
        h5 = re.search(r"<h5[^>]*>(.*?)</h5>", card, re.S)
        if color and h5:
            # <ruby>名前<rt>よみ</rt></ruby> の場合も、ルビなしの場合も名前だけ取り出す
            name = re.sub(r"<rt>.*?</rt>|<[^>]+>", "", h5.group(1))
            out[html.unescape(name).strip()] = color.group(1).lower()
    return out


# 歌唱予想メンバーの候補から外す（アイドル以外・重複表記）
EXCLUDE_IDOLS = {
    "P(赤羽根健治)", "プロデューサー（ぷちます）", "高木順二朗", "萩原雪歩(初代)", "双海亜美・真美",
}


def idol_group(production: str, name: str, count: int) -> str:
    if production == "765":
        if name in AS_765:
            return "765AS"
        # 39人のミリオンスターズは参加曲数が多い。それ以外（詩花・玲音・876など）は「その他」
        return "MILLION STARS" if count >= 40 else "その他"
    return ""


def build_brand(brand_id: str, conf: dict) -> None:
    print(f"[{brand_id}] songs")
    songs = get_json(f"{API}/list?type=music&music_type={conf['music_type']}&orderby=title&order=asc")
    kana = kana_map(conf["music_type"])
    song_rows = []
    for s in songs:
        title = s["name"]
        song_rows.append({
            "id": s["song_id"],
            "title": title,
            "kana": kana.get(title, ""),
            "url": s["link"],
        })
    song_rows.sort(key=lambda r: (r["kana"] or r["title"]))

    print(f"[{brand_id}] idols")
    idols = get_json(f"{API}/list?type=idol&production={conf['production']}&orderby=name&order=asc")
    colors = idol_colors(conf["sitemap"])
    idol_rows = []
    for i in idols:
        name = i["name"]
        if name in EXCLUDE_IDOLS:
            continue
        group = idol_group(conf["production"], name, i.get("count", 0))
        idol_rows.append({
            "id": i["tax_id"],
            "name": name,
            "kana": i.get("kana") or "",
            "cv": i.get("cv") or "",
            "color": colors.get(name, ""),
            "group": group,
            "count": i.get("count", 0),
        })
    group_order = {"MILLION STARS": 0, "765AS": 1, "その他": 2}
    idol_rows.sort(key=lambda r: (group_order.get(r["group"], 0), r["kana"] or r["name"]))

    write(DATA / "songs" / f"{brand_id}.json", song_rows)
    write(DATA / "idols" / f"{brand_id}.json", idol_rows)
    print(f"[{brand_id}] {len(song_rows)} songs / {len(idol_rows)} idols")


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    targets = sys.argv[1:] or list(BRANDS)
    for b in targets:
        build_brand(b, BRANDS[b])
    jst = timezone(timedelta(hours=9))
    write(DATA / "meta.json", {"updated_at": datetime.now(jst).strftime("%Y-%m-%d")})


if __name__ == "__main__":
    main()
