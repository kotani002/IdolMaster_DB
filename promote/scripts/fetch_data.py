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
# music_type が None のブランドは楽曲を取得しない（歌唱予想メンバーの候補だけに使う。brands.json では selectable:false）
BRANDS = {
    "ml": {
        "music_type": "ml",       # 楽曲の種類（API music_type）
        "production": "765",      # 歌唱予想メンバーに使うアイドルの所属
        "sitemap": "765pro",      # パーソナルカラー取得用ページ（無ければ None）
    },
    "cg": {
        "music_type": "cg",
        "production": "cg",
        "sitemap": "cg",
        # ふじわらはじめには「曲に参加したアイドル」しかいないので、公式の全アイドル一覧で補う（色も公式から）
        "roster": "https://cinderellagirls.idolmaster-official.jp/idol/",
    },
    # 765AS：ミリオンのグループではなく独立したブランドのタグにする（765プロ所属から13人を拾う）
    "as": {"music_type": None, "pick": [
        {"production": "765", "names": None, "only": "AS_765", "group": "", "sitemap": "765pro"},
    ]},
    "sc": {"music_type": None, "production": "sc", "sitemap": "sc"},
    # 876プロ：API に所属区分が無いので、他の所属から集めてグループ分けする
    #   names が None ならその所属の全員。sitemap はパーソナルカラー取得用
    "876": {"music_type": None, "pick": [
        {"production": "765", "names": ["日高愛", "水谷絵理"], "group": "ディアリースターズ"},
        {"production": "315", "names": ["秋月涼"], "group": "ディアリースターズ"},
        {"production": "va-liv", "names": None, "group": "vα-liv", "sitemap": "va-liv"},
    ]},
    "sidem": {"music_type": None, "production": "315", "sitemap": None},
    # 学マス：楽曲は music_type=gakuen。
    # アイドルは人の並び・顔ぶれを手で作った data/idols/gm.json を正とし、CV・よみ だけ API で埋める
    "gm": {"music_type": "gakuen", "production": "gakuen", "sitemap": None, "keep_file": True},
}

# 876プロ（ディアリースターズ）として別ブランドに出すので、765プロ（ミリオンの「その他」）からは外す
# （秋月涼は SideM にも所属しているので SideM には残す）
DEARLY_STARS_FROM_765 = {"日高愛", "水谷絵理"}

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
    "P(赤羽根健治)", "プロデューサー（ぷちます）", "プロデューサー", "高木順二朗", "双海亜美・真美",
    # 事務所スタッフ・社長など
    "千川ちひろ", "七草はづき", "齋藤孝司", "山村賢",
}


SHODAI = re.compile(r"\s*[（(]初代[)）]\s*")


def excluded(name: str) -> bool:
    return name in EXCLUDE_IDOLS


def merge_shodai(rows: list[dict]) -> list[dict]:
    """「○○（初代）」は旧キャストでの登録。
    現キャストの同名エントリがあれば1人にまとめ、CV を「旧CV/新CV」にする（例：萩原雪歩 落合祐里香/浅倉杏美）。
    無ければ（例：姫野かのん）「（初代）」を外して残す。"""
    by_name = {r["name"]: r for r in rows if not SHODAI.search(r["name"])}
    out = []
    for r in rows:
        if SHODAI.search(r["name"]):
            base = SHODAI.sub("", r["name"])
            cur = by_name.get(base)
            if cur:
                if r["cv"] and cur["cv"] and r["cv"] != cur["cv"]:
                    cur["cv"] = f"{r['cv']}/{cur['cv']}"
                continue
            r = {**r, "name": base}
            by_name[base] = r
        out.append(r)
    return out


# ふじわらはじめに載っていない・最新でない CV を手で補う（名前 → 表示するCV）。
# CV が途中で変わった人は「旧CV/新CV」の形で書く。
CV_OVERRIDES: dict[str, str] = {
    "姫野かのん": "村瀬歩/伊能幸輝",   # 2026-08-28 新キャスト発表。ふじわらはじめは旧キャストのみ
    "氷渡香名江": "安倍彩野夏",        # 学マス：2026-11-08 発表。ふじわらはじめ未登録
}


def cg_official_roster(url: str) -> list[dict]:
    """シンデレラガールズ公式ポータルのアイドル一覧（1リクエスト・全190人）から 名前・よみ・CV・色 を取る。"""
    page = get(url).decode("utf-8", "replace")
    out = []
    for li in re.findall(r'<li class="idol__item"(.*?)</li>', page, re.S):
        attr = lambda k: html.unescape((re.search(rf'data-{k}="([^"]*)"', li) or [None, ""])[1]).strip()
        name = re.search(r'<p class="idol__name">(.*?)</p>', li, re.S)
        slug = re.search(r'/idol/([^/"]+)/?"', li)
        if not name:
            continue
        cv = attr("cv")
        out.append({
            "slug": slug.group(1) if slug else "",
            "name": html.unescape(re.sub(r"<[^>]+>|\s", "", name.group(1))),
            "kana": attr("furigana"),
            "cv": "" if cv in ("-", "－", "") else cv,
            "color": attr("color").lower(),
        })
    return out


def idol_group(production: str, name: str, count: int) -> str:
    if production == "765":
        # （765AS・876プロは別ブランドに分けたので、ここには来ない）
        # 39人のミリオンスターズは参加曲数が多い。それ以外（詩花・玲音など）は「その他」
        return "MILLION STARS" if count >= 40 else "その他"
    return ""


def build_brand(brand_id: str, conf: dict) -> None:
    song_rows = None
    if conf["music_type"]:
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
    group_of: dict[str, str] = {}
    colors: dict[str, str] = {}
    if conf.get("pick"):
        # 複数の所属から集めて、指定のグループに分ける（876プロ用）
        idols = []
        for p in conf["pick"]:
            names = AS_765 if p.get("only") == "AS_765" else p["names"]
            # 「○○（初代）」も拾う（旧CV/新CV の表記に使うため）
            found = [i for i in get_json(f"{API}/list?type=idol&production={urllib.parse.quote(p['production'])}&orderby=name&order=asc")
                     if names is None or SHODAI.sub("", i["name"]) in names]
            missing = set(names or []) - {SHODAI.sub("", i["name"]) for i in found}
            if missing:
                print(f"  ! not found in {p['production']}: {', '.join(missing)}")
            for i in found:
                group_of[i["name"]] = p["group"]
            idols += found
            if p.get("sitemap"):
                colors.update(idol_colors(p["sitemap"]))
    else:
        idols = get_json(f"{API}/list?type=idol&production={urllib.parse.quote(conf['production'])}&orderby=name&order=asc")
        colors = idol_colors(conf["sitemap"]) if conf.get("sitemap") else {}
    idol_rows = []
    for i in idols:
        name = i["name"]
        if excluded(name):
            continue
        if conf.get("production") == "765" and SHODAI.sub("", name) in (DEARLY_STARS_FROM_765 | AS_765):
            continue  # 876プロ・765AS はそれぞれ別ブランドのタグに出す
        group = group_of.get(name) or idol_group(conf.get("production", ""), name, i.get("count", 0))
        idol_rows.append({
            "id": i["tax_id"],
            "name": name,
            "kana": i.get("kana") or "",
            "cv": i.get("cv") or "",
            "color": colors.get(name, ""),
            "group": group,
            "count": i.get("count", 0),
        })
    idol_rows = merge_shodai(idol_rows)

    if conf.get("roster"):
        # 公式の全員リストを基準にし、ふじわらはじめの情報（ID・参加曲数）を名前で結び付ける
        official = cg_official_roster(conf["roster"])
        by_name = {r["name"]: r for r in idol_rows}
        merged = []
        for o in official:
            f = by_name.pop(o["name"], None)
            merged.append({
                "id": f["id"] if f else f"{brand_id}-{o['slug']}",
                "name": o["name"],
                "kana": o["kana"] or (f["kana"] if f else ""),
                "cv": o["cv"] or (f["cv"] if f else ""),
                "color": o["color"] or (f["color"] if f else ""),
                "group": "",
                "count": f["count"] if f else 0,
            })
        if by_name:  # 表記ゆれ等で公式一覧と結び付かなかったもの（消さずに残して報告）
            print(f"  ! not in official roster: {', '.join(by_name)}")
            merged.extend(by_name.values())
        idol_rows = merged

    group_order = {"MILLION STARS": 0, "765AS": 1, "その他": 2, "ディアリースターズ": 0, "vα-liv": 1}
    idol_rows.sort(key=lambda r: (group_order.get(r["group"], 0), r["kana"] or r["name"]))

    if conf.get("keep_file"):
        # 手で作った一覧はそのまま（並び・人・色を変えない）。空の CV・よみ だけ API の値で埋める
        path = DATA / "idols" / f"{brand_id}.json"
        api = {re.sub(r"\s", "", r["name"]): r for r in idol_rows}
        kept = json.loads(path.read_text(encoding="utf-8"))
        for r in kept:
            a = api.get(re.sub(r"\s", "", r["name"]))
            if not a:
                print(f"  ! not in fujiwarahaji (CV は手入力): {r['name']}")
                continue
            r["cv"] = a["cv"] or r.get("cv", "")
            r["kana"] = r.get("kana") or a["kana"]
        idol_rows = kept

    for r in idol_rows:
        if r["name"] in CV_OVERRIDES and CV_OVERRIDES[r["name"]]:
            r["cv"] = CV_OVERRIDES[r["name"]]

    if song_rows is not None:
        write(DATA / "songs" / f"{brand_id}.json", song_rows)
    write(DATA / "idols" / f"{brand_id}.json", idol_rows)
    print(f"[{brand_id}] {len(song_rows) if song_rows is not None else '-'} songs / {len(idol_rows)} idols")


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
