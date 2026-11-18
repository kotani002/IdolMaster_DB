#!/usr/bin/env python3
"""
ふじわらはじめAPI から楽曲・アイドル情報を取得して data/ 以下の JSON を生成する。

  python scripts/fetch_data.py                 # 全ブランド（ユニットも取り直す）
  python scripts/fetch_data.py sc              # そのブランドだけ（ユニットは前回の結果を使い回す）
  python scripts/fetch_data.py sc --units      # そのブランドだけ、ユニットも取り直す
  python scripts/fetch_data.py units           # ユニットだけ取り直す
  python scripts/fetch_data.py sc --no-cache   # 一時保存（24時間）を使わずに取り直す

- 依存ライブラリなし（Python 3.9+ 標準ライブラリのみ）
- ふじわらはじめへの負荷を減らすため、取得した内容は scripts/.cache/fujiwarahaji/ に一時保存し、
  24時間以内に同じURLを取るときは保存したものを使う（--no-cache で使わない）。
  ユニット（約300件）は scripts/.cache/units.json に保存し、1ブランドだけ取り直すときは使い回す。
- データ: アイマス楽曲DB ふじわらはじめ (https://fujiwarahaji.me) / CC BY-NC 4.0
- 先方の案内 (https://fujiwarahaji.me/llms.txt) に従い、API経由・独自UserAgent・
  リクエスト間隔を空けて取得する。
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.error
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
# music_type が None のブランドは楽曲を取得しない（歌って欲しいアイドルの候補だけに使う。brands.json では selectable:false）
BRANDS = {
    "ml": {
        "music_type": "ml",       # 楽曲の種類（API music_type）
        "production": "765",      # 歌って欲しいアイドルに使うアイドルの所属
        "sitemap": "765pro",      # パーソナルカラー取得用ページ（無ければ None）
    },
    "cg": {
        "music_type": "cg",
        "production": "cg",
        "sitemap": "cg",
        # ふじわらはじめには「曲に参加したアイドル」しかいないので、公式の全アイドル一覧で補う（色も公式から）
        "roster": "https://cinderellagirls.idolmaster-official.jp/idol/",
    },
    # 765AS：ミリオンのグループではなく独立したブランドにする（765プロ所属から13人を拾う）。楽曲は music_type=as
    # 歌唱者は曲ごとに取る（旧キャストの「萩原雪歩（初代）」や「双海亜美・真美」で登録された曲があり、アイドル別の参加曲では漏れるため）
    "as": {"music_type": "as", "singers_by_song": True, "pick": [
        {"production": "765", "names": None, "only": "AS_765", "group": "", "sitemap": "765pro"},
    ]},
    "sc": {"music_type": "sc", "production": "sc", "sitemap": "sc"},
    # 876プロ：API に所属区分が無いので、他の所属から集めてグループ分けする
    #   names が None ならその所属の全員。sitemap はパーソナルカラー取得用
    #   秋月涼は SideM 所属で /tax が使えないので、歌唱者は曲ごとに取る
    "876": {"music_type": "876", "singers_by_song": True, "pick": [
        {"production": "765", "names": ["日高愛", "水谷絵理"], "group": "ディアリースターズ"},
        {"production": "315", "names": ["秋月涼"], "group": "ディアリースターズ"},
        {"production": "va-liv", "names": None, "group": "vα-liv", "sitemap": "va-liv"},
    ]},
    # 961プロ：ふじわらはじめに区分が無いので、曲は ID で指定（SONGS_961）。765AS からは外す（ミリオンの ZWEIGLANZ は両方）
    #   アイドルは玲音・詩花・亜夜、Jupiter（SideM にも残る）、961時代の美希・貴音・響（765AS にも残る）（ユーザー判断）
    "961": {"music_type": None, "song_ids": "SONGS_961", "singers_by_song": True, "pick": [
        # 玲音・詩花・亜夜はグループ名を付けない（ブランド名と同じ「961 PRODUCTION」のタグは重複するので出さない：ユーザー判断）
        {"production": "765", "names": ["玲音", "詩花", "亜夜"], "group": "", "sitemap": "765pro"},
        {"production": "315", "names": ["天ヶ瀬冬馬", "伊集院北斗", "御手洗翔太"], "group": "Jupiter"},
        {"production": "765", "names": ["星井美希", "四条貴音", "我那覇響"], "group": "プロジェクト・フェアリー"},
    ]},
    # SideM のアイドルは /tax（アイドル別の参加曲）が API 非対応なので、歌唱者は曲ごとに取る
    # 色はふじわらはじめに無いので imas-db.jp のカラーコード一覧（SideM のタブ）から取る
    "sidem": {"music_type": "sidem", "production": "315", "sitemap": None, "singers_by_song": True, "imasdb_colors": "sidem"},
    # 学マス：楽曲は music_type=gakuen。
    # アイドルは人の並び・顔ぶれを手で作った data/idols/gm.json を正とし、CV・よみ・色 だけ API で埋める
    # （手で付けたIDなので /tax が使えない。歌唱者は SideM と同じく曲ごとに取る）
    "gm": {"music_type": "gakuen", "production": "gakuen", "sitemap": "hatsuboshi", "keep_file": True, "singers_by_song": True},
}

# 961プロの曲（曲ID）。MOVED_961 は 765AS の曲一覧から外す（961プロだけに出す）。ZWEIGLANZ の2曲はミリオンにも残す
MOVED_961 = {
    3117,        # オーバーマスター
    8092,        # KisS
    8055,        # 黒い犬
    8008, 8011, 8012, 8009, 8010,  # Jupiter：Alice or Guilty・恋をはじめよう・BANG×BANG・On Sunday・結晶～Crystal Dust～
    7938, 3484,  # アクセルレーション（我那覇響・玲音／詩花・玲音）
    7918,        # アルティメットアイズ
    2808,        # Blooming Star
    11578,       # REALIZE!!!（961 PRODUCTION presents）
    4593,        # 1st Call（DIAMANT）
    4592,        # EVER RISING（アルバノクト）
}
SONGS_961 = sorted(MOVED_961) + [
    3551,  # アライアンス・スターダスト（ZWEIGLANZ、ミリオンにも）
    3956,  # Shine My Way（ZWEIGLANZ、ミリオンにも）
]

# 876プロ（ディアリースターズ）として別ブランドに出すので、765プロ（ミリオンの「その他」）からは外す
# （秋月涼は SideM にも所属しているので SideM には残す）
DEARLY_STARS_FROM_765 = {"日高愛", "水谷絵理"}

# 765プロ内のグループ分け（ミリオン以外のアイドルを区別するため）
AS_765 = {
    "天海春香", "如月千早", "星井美希", "萩原雪歩", "高槻やよい", "菊地真", "水瀬伊織",
    "四条貴音", "秋月律子", "三浦あずさ", "双海亜美", "双海真美", "我那覇響",
}


# 一時保存（同じURLを24時間以内に取るときは保存したものを使い、相手に取りに行かない）
CACHE = Path(__file__).resolve().parent / ".cache" / "fujiwarahaji"
CACHE_HOURS = 24
USE_CACHE = True  # main() で --no-cache のとき False


def cache_file(url: str) -> Path:
    return CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".bin")


def get(url: str) -> bytes:
    f = cache_file(url)
    if USE_CACHE and f.exists() and time.time() - f.stat().st_mtime < CACHE_HOURS * 3600:
        return f.read_bytes()
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
            CACHE.mkdir(parents=True, exist_ok=True)
            f.write_bytes(body)
            time.sleep(WAIT_SEC)
            return body
        except Exception as e:  # 503 などは少し待って再試行
            if isinstance(e, urllib.error.HTTPError) and 400 <= e.code < 500 and e.code != 429:
                time.sleep(WAIT_SEC)
                raise RuntimeError(f"HTTP {e.code}: {url}")  # 400/404 は再試行しても同じ
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


IMAS_DB_COLORS = "https://imas-db.jp/misc/color.html"


def color_key(name: str) -> str:
    """色の一覧と名前を突き合わせるためのキー（空白・全角半角の違いを吸収。例：＝/=、Ⅱ/II）"""
    return re.sub(r"\s", "", unicodedata.normalize("NFKC", name or ""))


def imas_db_colors(section: str) -> dict[str, str]:
    """imas-db.jp のカラーコード一覧（1リクエスト）から、ブランドのタブ（id="sidem" など）の 名前 -> 色 を作る。
    ふじわらはじめに色が無いブランド（SideM）用。行は「<td>名前(CV)</td> <td><span title="#xxxxxx" …」の形。"""
    page = get(IMAS_DB_COLORS).decode("utf-8", "replace")
    start = page.find(f'id="{section}"')
    if start < 0:
        return {}
    end = page.find('class="tab-pane', start + 10)
    part = page[start:end if end > 0 else len(page)]
    out: dict[str, str] = {}
    for name, color in re.findall(r"<td>([^<]+?)(?:[（(][^)）]*[)）])?</td>\s*<td[^>]*><span title=\"(#[0-9a-fA-F]{6})\"", part):
        out[color_key(html.unescape(name))] = color.lower()
    return out


# ユニット活動が中心のブランドは、歌って欲しいアイドルの一覧をユニットごとに分ける（ユーザー判断）。
# ユニット名・ユニットの色・並びは imas-db.jp のカラーコード一覧（ブランドのタブ → タブの id）
UNIT_GROUP_BRANDS = {"sc": "shinycolors", "sidem": "sidem"}


def imas_db_units(section: str) -> list[dict]:
    """imas-db.jp のカラーコード一覧のブランドのタブから [{name, color, members: [名前キー...]}] を作る。
    行は「<th>ユニット名</th><td><span title="#色">」の見出し行と、その下の「<td>名前(CV)</td>…」のメンバー行。"""
    page = get(IMAS_DB_COLORS).decode("utf-8", "replace")
    start = page.find(f'id="{section}"')
    if start < 0:
        return []
    end = page.find('class="tab-pane', start + 10)
    part = page[start:end if end > 0 else len(page)]
    units: list[dict] = []
    for tag, name, color in re.findall(
            r"<(th|td)>([^<]+?)(?:[（(][^)）]*[)）])?</t[hd]>\s*<td[^>]*><span title=\"(#[0-9a-fA-F]{6})\"", part):
        name = html.unescape(name).strip()
        if tag == "th":
            units.append({"name": name, "color": color.lower(), "members": []})
        elif units:
            units[-1]["members"].append(color_key(name))
    return units


# ユニット名を公式表記にそろえる（ふじわらはじめ・imas-db.jp はカタカナ表記）。ブランド → カタカナ表記 → 公式表記。
# カタカナ表記は units.json の「よみ」に入れるので、カタカナ・ひらがな・略称（「いるみね」など）でも探せる（ユーザー判断）
UNIT_OFFICIAL: dict[str, dict[str, str]] = {
    "sc": {
        "イルミネーションスターズ": "illumination STARS",
        "アンティーカ": "L'Antica",
        "アンティーカ（初代）": "L'Antica",  # 旧キャストでの登録
        "アルストロメリア": "ALSTROEMERIA",
        "ストレイライト": "Straylight",
        "ノクチル": "noctchill",
        "シーズ": "SHHis",
        "コメティック": "CoMETIK",
        # 放課後クライマックスガールズは国内公式も日本語表記のまま
    },
}


def to_hiragana(s: str) -> str:
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def official_unit_kana() -> dict[str, str]:
    """公式表記のユニット名 → よみ（カタカナ表記をひらがなにしたもの。「（初代）」は外す）"""
    return {o: to_hiragana(SHODAI.sub("", ja)) for m in UNIT_OFFICIAL.values() for ja, o in m.items()}


def attach_unit_groups(only: list[str] | None = None) -> None:
    """data/idols/<brand>.json の各アイドルに group（ユニット名）と group_color を付け、ユニット順に並べる。"""
    for b, section in UNIT_GROUP_BRANDS.items():
        f = DATA / "idols" / f"{b}.json"
        if (only and b not in only) or not f.exists():
            continue
        units = imas_db_units(section)
        where = {m: (i, u) for i, u in enumerate(units) for m in u["members"]}
        rows = json.loads(f.read_text(encoding="utf-8"))
        missing = []
        for r in rows:
            i, u = where.get(color_key(r["name"]), (len(units), None))
            r["group"] = UNIT_OFFICIAL.get(b, {}).get(u["name"], u["name"]) if u else ""
            r["group_color"] = u["color"] if u else ""
            r["_order"] = (i, u["members"].index(color_key(r["name"])) if u else 0)
            if not u:
                missing.append(r["name"])
        rows.sort(key=lambda r: r.pop("_order"))
        write(f, rows)
        print(f"[unit groups] {b}: {len(units)} units" + (f" / no unit: {', '.join(missing)}" if missing else ""))


# 歌って欲しいアイドルの候補から外す（アイドル以外・重複表記）
EXCLUDE_IDOLS = {
    "P(赤羽根健治)", "プロデューサー（ぷちます）", "プロデューサー", "高木順二朗", "双海亜美・真美",
    # 事務所スタッフ・社長など
    "千川ちひろ", "七草はづき", "齋藤孝司", "山村賢",
}


SHODAI = re.compile(r"\s*[（(]初代[)）]\s*")


# 2人まとめて登録されている歌唱者（曲ごとに歌唱者を取るときに分ける）
SPLIT_SINGERS = {"双海亜美・真美": ["双海亜美", "双海真美"]}


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


# 他ブランドの曲として登録されている合同曲を、このブランドの曲としても選べるようにする（ブランド → song_id）
EXTRA_SONGS: dict[str, list[int]] = {
    "cg": [
        2812,  # ハーモニクス（ミリオン：ジュリア・最上静香 × シンデレラ：多田李衣菜・木村夏樹。ふじわらはじめではミリオン扱い）
    ],
    # Migratory Echoes はユニットごとに曲調もジャケット（ECHOES 01〜08）も違うので、ユニット版を別の曲として並べる
    # （ふじわらはじめではリミックス扱い。ジャケットは data/jacket_overrides.json で指定）
    "sc": [
        11429,  # イルミネーションスターズVer.
        11430,  # アンティーカVer.
        11431,  # 放課後クライマックスガールズVer.
        11432,  # アルストロメリアVer.
        11433,  # ストレイライトVer.
        11434,  # ノクチルVer.
        11437,  # シーズVer.
        11439,  # コメティックVer.
    ],
    "876": [
        10515,  # RELOADING（ディアリースターズ・vα-liv の6人。ふじわらはじめではリローディングのリミックス扱い）
        # The world is all one !!（5041）は 765AS だけ。Alternative Tracks Collection のカバー版は入れない（ユーザー判断）
    ],
}


# 越境曲：ブランドの垣根を越えた曲（ふじわらはじめでは「合同」）。指定したブランドの曲一覧に入れ、
# 検索ではユニット名の代わりに「越境曲」と出す（曲ID → 入れるブランド）
CROSSOVER = "越境曲"
_ALL = {"as", "cg", "ml", "sidem", "sc", "gm", "961"}
_STARLIT = {"as", "cg", "ml", "sc", "961"}  # スターリットシーズン（765AS・シンデレラ・ミリオン・シャニマス、961プロも出演）
CROSSOVER_SONGS: dict[int, set[str]] = {
    9498: _ALL,                  # アイ NEED YOU (FOR WONDERFUL STORY)
    # 学マス・961プロが歌った音源が無い曲は外す（ユーザー判断。初星音楽祭のカバーは配信に無い）
    4411: _ALL - {"961", "gm"},  # VOY@GER
    3525: _ALL - {"961", "gm"},  # なんどでも笑おう
    5323: _ALL - {"gm"},         # CRYST@LOUD
    3982: _ALL - {"gm", "961"},  # POPLINKS TUNE!!!!!（学マス・961プロを除く）
    2611: {"as", "cg", "ml"},    # IDOL POWER RAINBOW（学マス・SideM・シャニマスを除く）
    2691: {"as", "cg", "ml"},    # アイ MUST GO!（学マス・SideM・シャニマスを除く）
    # SideM・学マスには入れない越境曲
    4072: _STARLIT,              # SESSION!
    4387: _STARLIT,              # 夏のBang!!
    4421: _STARLIT,              # アイシテの呪縛～Je vous aime～
    4422: _STARLIT,              # GR@TITUDE
    4596: _STARLIT,              # ダンス・ダンス・ダンス
    4775: _STARLIT,              # KAWAIIウォーズ
    4801: _STARLIT,              # 全力★ドリーミングガールズ
}
# 越境曲に付ける検索用の名前（「スターリットシーズン」「スタマス」で検索すると出る）。名前 → よみ
STARLIT = {"スターリットシーズン": "すたーりっとしーずん", "スタマス": "すたます"}
CROSSOVER_TAGS: dict[int, list[str]] = {
    sid: list(STARLIT) for sid in (4072, 4387, 4421, 4422, 4596, 4775, 4801)  # アイドルマスター スターリットシーズンの曲
}


def crossover_units(sid: int) -> list[str]:
    return [CROSSOVER] + CROSSOVER_TAGS.get(sid, [])


def extra_song_rows(brand_id: str, have: set[int]) -> list[dict]:
    rows = []
    ids = (EXTRA_SONGS.get(brand_id, []) + (SONGS_961 if brand_id == "961" else [])
           + [sid for sid, bs in CROSSOVER_SONGS.items() if brand_id in bs])
    for sid in ids:
        if sid in have:
            continue
        m = get_json(f"{API}/music?id={sid}")
        # 「曲名 （ユニットVer.）」の全角かっこ・空白の揺れをそろえる → 「曲名 (ユニットVer.)」
        title = re.sub(r"\s*[（(]\s*([^（()）]*?)\s*[）)]\s*$", r" (\1)", m["name"])
        rows.append({
            "id": m["song_id"],
            "title": title,
            # API のよみはカタカナ・空白区切りのことがあるので、他の曲と同じひらがなにそろえる
            "kana": "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c
                            for c in re.sub(r"\s", "", m.get("kana") or "")),
            "url": m["link"],
            "singers": [x["name"] for x in m.get("member") or []],
        })
    return rows


def build_brand(brand_id: str, conf: dict) -> None:
    song_rows = None
    if conf["music_type"] or conf.get("song_ids"):
        print(f"[{brand_id}] songs")
        # 曲を ID で指定するブランド（961プロ）は、一覧の代わりに1曲ずつ取る（extra_song_rows）
        songs = (get_json(f"{API}/list?type=music&music_type={conf['music_type']}&orderby=title&order=asc")
                 if conf["music_type"] else [])
        kana = kana_map(conf["music_type"]) if conf["music_type"] else {}
        # 前回付けた歌唱者は引き継ぐ（ブランドを指定して実行したときは、他ブランドのアイドル分を調べ直さないため）
        old_path = DATA / "songs" / f"{brand_id}.json"
        old = {r["id"]: r.get("singers", []) for r in json.loads(old_path.read_text(encoding="utf-8"))} if old_path.exists() else {}
        song_rows = []
        for s in songs:
            title = s["name"]
            song_rows.append({
                "id": s["song_id"],
                "title": title,
                "kana": kana.get(title, ""),
                "url": s["link"],
                "singers": old.get(s["song_id"], []),
            })
        if brand_id == "as":  # 961プロへ移した曲
            song_rows = [r for r in song_rows if r["id"] not in MOVED_961]
        song_rows += extra_song_rows(brand_id, {r["id"] for r in song_rows})
        # よみが無い「曲名 (○○Ver.)」は元の曲名のよみを使う（ひらがなでも探せるように）
        for r in song_rows:
            if not r["kana"]:
                r["kana"] = kana.get(re.sub(r"\s*\([^()]*\)$", "", r["title"]), "")
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
        if conf.get("imasdb_colors"):  # ふじわらはじめに色が無いブランドは imas-db.jp の一覧で補う
            colors = {**{color_key(k): v for k, v in colors.items()}, **imas_db_colors(conf["imasdb_colors"])}
            colors = {i["name"]: colors[color_key(i["name"])] for i in idols if color_key(i["name"]) in colors}
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

    group_order = {"MILLION STARS": 0, "765AS": 1, "その他": 2, "ディアリースターズ": 0, "vα-liv": 1,
                   "961 PRODUCTION": 0, "Jupiter": 1, "プロジェクト・フェアリー": 2}
    if brand_id == "961":  # Jupiter の色はふじわらはじめに無いので、SideM の一覧（imas-db.jp から取った色）を使う
        sidem = DATA / "idols" / "sidem.json"
        sc = {r["name"]: r.get("color", "") for r in json.loads(sidem.read_text(encoding="utf-8"))} if sidem.exists() else {}
        for r in idol_rows:
            r["color"] = r["color"] or sc.get(r["name"], "")
    idol_rows.sort(key=lambda r: (group_order.get(r["group"], 0), r["kana"] or r["name"]))

    if conf.get("keep_file"):
        # 手で作った一覧はそのまま（並び・人を変えない）。空の CV・よみ・色 だけ API の値で埋める
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
            r["color"] = r.get("color") or a.get("color", "")
        idol_rows = kept

    for r in idol_rows:
        if r["name"] in CV_OVERRIDES and CV_OVERRIDES[r["name"]]:
            r["cv"] = CV_OVERRIDES[r["name"]]

    if song_rows is not None:
        write(DATA / "songs" / f"{brand_id}.json", song_rows)
    write(DATA / "idols" / f"{brand_id}.json", idol_rows)
    print(f"[{brand_id}] {len(song_rows) if song_rows is not None else '-'} songs / {len(idol_rows)} idols")


def attach_singers(only: list[str] | None = None) -> None:
    """各アイドルの参加曲（/tax）を集め、data/songs/<brand>.json の各曲に singers（歌唱メンバー名）を付ける。
    曲名検索で歌唱者名（完全一致）からも曲を探せるようにするため。
    only を指定したときは、そのブランドの曲・アイドルだけを調べ、既存の singers に足す（全ブランドだと約20分かかるため）。"""
    brands = [b for b in BRANDS if only is None or b in only]
    song_files = [DATA / "songs" / f"{b}.json" for b in brands if BRANDS[b]["music_type"] or BRANDS[b].get("song_ids")]
    song_files = [f for f in song_files if f.exists()]
    if not song_files:
        return
    print("[singers] idol songs")
    plain = lambda n: re.sub(r"\s", "", SHODAI.sub("", n or ""))
    singers: dict[int, list[str]] = {}
    seen: set[str] = set()
    for b in brands:
        path = DATA / "idols" / f"{b}.json"
        if not path.exists() or BRANDS[b].get("singers_by_song"):
            continue
        for r in json.loads(path.read_text(encoding="utf-8")):
            name = r["name"]
            if name in seen:
                continue
            seen.add(name)
            # ふじわらはじめ未登録（公式一覧だけから足した CG アイドルなど）は参加曲が無い
            if not isinstance(r["id"], int):
                continue
            data = None
            if isinstance(r["id"], int):
                try:
                    data = get_json(f"{API}/tax?id={r['id']}&limit=3000")
                except Exception:
                    data = None
                if data and plain(data.get("name")) != plain(name):
                    data = None  # 手で付けたID（学マスなど）は別人なので名前で引き直す
            if data is None:
                try:
                    data = get_json(f"{API}/tax?idol_name={urllib.parse.quote(plain(name))}&limit=3000")
                except Exception:
                    continue
                if plain(data.get("name")) != plain(name):
                    continue
            for s in data.get("song") or []:
                lst = singers.setdefault(s["song_id"], [])
                if name not in lst:
                    lst.append(name)
    for f in song_files:
        rows = json.loads(f.read_text(encoding="utf-8"))
        if BRANDS[f.stem].get("singers_by_song"):
            # アイドル別の参加曲（/tax）が API で取れないブランド（SideM）は、曲ごとに歌唱メンバーを取る
            print(f"[singers] {f.stem}: per song ({len(rows)})")
            for s in rows:
                try:
                    m = get_json(f"{API}/music?id={s['id']}")
                except Exception:
                    continue
                # 「萩原雪歩（初代）」（旧キャストでの登録）は今の名前に、「双海亜美・真美」は2人に分ける
                names = [n for x in m.get("member") or []
                         for n in SPLIT_SINGERS.get(SHODAI.sub("", x.get("name", "")), [SHODAI.sub("", x.get("name", ""))])
                         if n and not excluded(n)]
                singers[s["id"]] = list(dict.fromkeys(singers.get(s["id"], []) + names))
        for s in rows:
            found = singers.get(s["id"], [])
            if only is None:
                s["singers"] = found
            else:
                s["singers"] = list(dict.fromkeys((s.get("singers") or []) + found))
        write(f, rows)
        print(f"[singers] {f.name}: {sum(1 for s in rows if s['singers'])}/{len(rows)} songs have singers")


WHOLE_SONG = "全体曲"
# ブランド全員のユニット（これが付いた曲は全体曲）
WHOLE_UNIT_RE = re.compile(r"^シャイニーカラーズ\(|^765 MILLION ALLSTARS$|^765 MILLIONSTARS$|^765THEATER ALLSTARS$|^315 ALLSTARS$")


# 自動の判定では拾えない全体曲（曲ID で指定）
WHOLE_SONG_IDS: dict[str, set[int]] = {
    "cg": {
        26,    # お願い！シンデレラ
        192,   # 輝く世界の魔法
        193,   # We’re the friends!
        194,   # メッセージ
        195,   # Take me☆Take you
        191,   # EVERMORE
        681,   # イリュージョニスタ！
        1166,  # Trust me
        3692,  # Brand new!
        4508,  # EVERLASTING
        4340,  # Let's Sail Away!!!
        4341,  # ココカラミライヘ！
    },
    "sidem": {
        8823,  # DRIVE A LIVE
        8667,  # NEXT STAGE!
        8774,  # Beyond The Dream
        8711,  # MEET THE WORLD!
        8742,  # Reason!!
    },
}


# そのブランドの中だけで「ブランド全員のユニット」とみなすもの
# （765PRO ALLSTARS はミリオンの曲（LEADER!!）にも付いているので、765AS の曲のときだけ全体曲にする）
WHOLE_UNIT_RE_BRAND = {"as": re.compile(r"^(IM@S )?765PRO ALLSTARS$|^IM@S ALLSTARS$")}
# ブランドの全員（ユニット名が付いていなくても、全員が歌っていれば全体曲）
WHOLE_MEMBERS = {"as": AS_765,
                 "876": {"日高愛", "水谷絵理", "秋月涼", "上水流宇宙", "灯里愛夏", "レトラ"}}


# グループの全員が歌う曲に付けるユニット名（ふじわらはじめにユニット登録が無い曲も、グループ名で探せるように）。
# ブランド → [(メンバー, [ユニット名]), ...]。名前 → よみ は GROUP_TAG_KANA
GROUP_TAGS = {"876": [({"日高愛", "水谷絵理", "秋月涼"}, ["Dearly Stars", "ディアリースターズ"]),
                      ({"上水流宇宙", "灯里愛夏", "レトラ"}, ["vα-liv"])]}
GROUP_TAG_KANA = {"Dearly Stars": "でぃありーすたーず", "ディアリースターズ": "でぃありーすたーず", "vα-liv": "ゔぁりぶ"}


def group_tags(brand: str, singers: list[str] | None) -> list[str]:
    plain = {SHODAI.sub("", n) for n in singers or []}
    return [n for members, names in GROUP_TAGS.get(brand, []) if members <= plain for n in names]


def whole_song_units(units: list[str], brand: str = "", singers: list[str] | None = None) -> list[str]:
    """全ユニットで歌う曲（全体曲）は、個別のユニット名で検索しても出ないよう「全体曲」だけにする。

    ブランド全員のユニットが付いている曲か、5ユニット以上が歌っている曲を全体曲とみなす。
    """
    brand_re = WHOLE_UNIT_RE_BRAND.get(brand)
    if (any(WHOLE_UNIT_RE.search(u) or (brand_re and brand_re.search(u)) for u in units) or len(set(units)) >= 5
            or (brand in WHOLE_MEMBERS and WHOLE_MEMBERS[brand] <= {SHODAI.sub("", n) for n in singers or []})):
        return [WHOLE_SONG]
    return units


UNITS_SAVED = Path(__file__).resolve().parent / ".cache" / "units.json"  # ユニットの取得結果（使い回し用）


def fetch_units() -> tuple[dict[int, list[str]], dict[str, str]]:
    """ユニット一覧ページ（1リクエスト）でユニットのIDを集め、ユニットごとに API の /tax で持ち歌を取る（約300リクエスト）。
    よみは IME データ（1リクエスト）でも補う。結果は UNITS_SAVED に保存する。"""
    page = get("https://fujiwarahaji.me/sitemap/unit").decode("utf-8", "replace")
    ids = list(dict.fromkeys(re.findall(r'href="https://fujiwarahaji\.me/unit/(\d+)"', page)))
    print(f"[units] {len(ids)} units")
    by_song: dict[int, list[str]] = {}
    kana: dict[str, str] = {}
    for n, uid in enumerate(ids, 1):
        try:
            u = get_json(f"{API}/tax?id={uid}&limit=3000")
        except RuntimeError as e:
            print(f"  ! unit {uid}: {e}", file=sys.stderr)
            continue
        name = html.unescape(u.get("name") or "").strip()
        if not name:
            continue
        if u.get("kana"):
            kana[name] = u["kana"]
        for s in u.get("song") or []:
            if s.get("song_id"):
                by_song.setdefault(int(s["song_id"]), []).append(name)
        if n % 50 == 0:
            print(f"  {n}/{len(ids)}")
    q = urllib.parse.urlencode({"enc": "utf8", "types": "unit",
                                "brand": "cg,ml,shiny,as,godo,cover,sidem,gakuen,876",
                                "production": "cg,765,sc,315,va-liv,hatsuboshi"})
    for line in get(f"https://fujiwarahaji.me/api/ime/main?{q}").decode("utf-8", "replace").splitlines():
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0] and cols[1] and not cols[0].startswith("!"):
            kana.setdefault(cols[1].strip(), cols[0].strip())
    UNITS_SAVED.parent.mkdir(parents=True, exist_ok=True)
    jst = timezone(timedelta(hours=9))
    UNITS_SAVED.write_text(json.dumps({"fetched_at": datetime.now(jst).isoformat(timespec="seconds"),
                                       "by_song": by_song, "kana": kana}, ensure_ascii=False), encoding="utf-8")
    return by_song, kana


def load_units(refresh: bool) -> tuple[dict[int, list[str]], dict[str, str]]:
    """ユニットは変わることが少ないので、保存した前回の結果があれば使い回す（refresh=True なら取り直す）"""
    if not refresh and UNITS_SAVED.exists():
        saved = json.loads(UNITS_SAVED.read_text(encoding="utf-8"))
        print(f"[units] 前回の取得結果を使います（{saved.get('fetched_at', '?')} 取得。取り直すときは --units）")
        return {int(k): v for k, v in saved["by_song"].items()}, saved["kana"]
    return fetch_units()


def attach_units(only: list[str] | None = None, refresh: bool = True) -> None:
    """曲名検索でユニット名から曲を探せるように、各曲に歌唱ユニット名（songs[].units）を付ける。
    ユニットのよみ（ひらがなで検索できるように）は data/units.json に 名前 -> よみ で書き出す。
    refresh=False なら、保存した前回のユニットの取得結果を使い回す（1ブランドだけ取り直すとき）。
    """
    by_song, kana = load_units(refresh)
    kana = dict(kana)
    names = {x for v in by_song.values() for x in v}
    off = official_unit_kana()  # 公式表記のユニット名（illumination STARS など）
    kana.update(off)
    names |= set(off)
    kana[WHOLE_SONG] = "ぜんたいきょく"
    kana[CROSSOVER] = "えっきょうきょく"
    kana.update(STARLIT)
    kana.update(GROUP_TAG_KANA)
    names |= {WHOLE_SONG, CROSSOVER, *STARLIT, *GROUP_TAG_KANA}
    write(DATA / "units.json", {k: kana[k] for k in sorted(kana) if k in names})
    for b in only or list(BRANDS):
        f = DATA / "songs" / f"{b}.json"
        if not (BRANDS[b].get("music_type") or BRANDS[b].get("song_ids")) or not f.exists():
            continue
        rows = json.loads(f.read_text(encoding="utf-8"))
        for s in rows:
            if not str(s.get("id", "")).isdigit():
                continue  # バージョン別に分けた曲（split_versions）は「全体曲」のまま
            u = by_song.get(int(s["id"]))
            if s.get("id") in CROSSOVER_SONGS:
                s["units"] = crossover_units(s["id"])
            elif s.get("id") in WHOLE_SONG_IDS.get(b, set()):
                s["units"] = [WHOLE_SONG]
            elif u or whole_song_units([], b, s.get("singers")) or group_tags(b, s.get("singers")):
                s["units"] = whole_song_units(u or [], b, s.get("singers"))
                if s["units"] != [WHOLE_SONG]:  # 全体曲はグループ名を付けない（「全体曲」で探す）
                    s["units"] = list(dict.fromkeys(s["units"] + group_tags(b, s.get("singers"))))
            else:
                s.pop("units", None)
        rename_units(b, rows)
        write(f, rows)
        print(f"[units] {f.name}: {sum(1 for s in rows if s.get('units'))}/{len(rows)} songs have units")


def rename_units(brand: str, rows: list[dict]) -> None:
    """曲のユニット名を公式表記にする（UNIT_OFFICIAL。同じユニットが2回にならないようにまとめる）"""
    m = UNIT_OFFICIAL.get(brand, {})
    for s in rows:
        if s.get("units"):
            s["units"] = list(dict.fromkeys(m.get(u, u) for u in s["units"]))


# バージョンごとに歌唱メンバーもジャケットも違う曲は、バージョン別の曲に分けて登録する（元の曲は消す）。
# 曲ID は「元の曲ID-キー」。ジャケットは data/jacket_overrides.json で指定
_JEWEL = [("Ver.Cute", "cute"), ("Ver.Cool", "cool"), ("Ver.Passion", "passion")]
SPLIT_VERSIONS: dict[str, dict[int, list[tuple[str, str]]]] = {
    "cg": {  # CINDERELLA MASTER Cute/Cool/Passion jewelries! と MASTER アルバムで、それぞれ別のメンバーが歌う
        185: _JEWEL + [("Ver.MASTER EVERMORE", "evermore")],    # ゴキゲンParty Night
        180: _JEWEL + [("Ver.MASTER EVERMORE", "evermore")],    # ススメ☆オトメ ～jewel parade～
        190: _JEWEL + [("Ver.MASTER EVERMORE", "evermore")],    # Near to You
        5124: _JEWEL + [("Ver.MASTER EVERAFTER", "everafter")],  # 認めてくれなくたっていいよ（EVERMORE ではなく EVERAFTER に収録）
    },
    "sidem": {  # WORLD TRE@SURE 01〜13 で国ごとにアレンジが違う
        8711: [(f"{c} Ver.", c.lower().replace(" ", "")) for c in (
            "FRANCE", "AMERICA", "SPAIN", "CHINA", "HAWAII", "GERMANY", "FINLAND",
            "CANADA", "RUSSIA", "THAILAND", "INDIA", "UNITED KINGDOM", "JAPAN")],  # MEET THE WORLD!
    },
}
# 分けたあとも元の曲を残す（バージョン無しの版も別にある曲）
SPLIT_KEEP_BASE = {8711}  # MEET THE WORLD!（UNIT COLLECTION 版）


def split_versions(only: list[str] | None = None) -> None:
    for b, conf in SPLIT_VERSIONS.items():
        if only and b not in only:
            continue
        f = DATA / "songs" / f"{b}.json"
        rows = json.loads(f.read_text(encoding="utf-8"))
        out = []
        # 前回分けた版は作り直すので外す（元の曲を残す曲で二重にならないように）
        rows = [s for s in rows if not (isinstance(s["id"], str) and s["id"].split("-")[0].isdigit()
                                         and int(s["id"].split("-")[0]) in conf)]
        for s in rows:
            if s["id"] not in conf or s["id"] in SPLIT_KEEP_BASE:
                out.append(s)
            if s["id"] not in conf:
                continue
            for label, key in conf[s["id"]]:
                out.append({**s, "id": f"{s['id']}-{key}", "title": f"{s['title']} ({label})", "units": [WHOLE_SONG]})
        write(f, out)
        print(f"[versions] {f.name}: split {sum(1 for s in rows if s['id'] in conf)} songs")


# ふじわらはじめに単独で登録されていない曲を手で足す（ブランド → 曲）。曲ID は「元にした曲ID-キー」
_DS = ["日高愛", "水谷絵理", "秋月涼"]
MANUAL_SONGS: dict[str, list[dict]] = {
    "876": [
        # “HELLO!!”（ディアリースターズ、DREAM SYMPHONY 00）。ふじわらはじめには vα-liv のカバー "HELLO!"（6044、
        # 同じ作詞 yura・作曲 神前暁）だけが登録されている。ユーザー判断でディアリースターズの曲として登録し、カバー版は入れない
        {"id": 6044, "title": "“HELLO!!”", "kana": "はろー", "url": "https://fujiwarahaji.me/music/876/6044",
         "singers": _DS, "units": ["Dearly Stars", "ディアリースターズ"]},
    ],
    # IDOL WORLD SUPER FESTIVAL 2026 会場オリジナルCD【961PRODUCTION & KOHAKU & 765PRO ALLSTARS】（SACX-1149～1150）の新曲。
    # ふじわらはじめ未登録なので手で足す（https://columbia.jp/idolmaster/imasnews/260911.html）
    "961": [
        {"id": "961-extreme", "title": "エクストリーム・オーバードライブ", "kana": "えくすとりーむ・おーばーどらいぶ",
         "url": "https://columbia.jp/idolmaster/imasnews/260911.html", "singers": ["玲音"]},
        {"id": "961-flame", "title": "FlaME", "kana": "ふれいむ",
         "url": "https://columbia.jp/idolmaster/imasnews/260911.html", "singers": ["星井美希", "玲音"]},
    ],
}
# 歌唱者・ユニットの手直し（ブランド → 曲ID → 上書きする項目）。ディアリースターズのカバー版（Alternative Tracks
# Collection）は入れず、vα-liv の曲として登録する（ユーザー判断）
_VALIV = ["上水流宇宙", "灯里愛夏", "レトラ"]
SONG_FIXES: dict[str, dict[int, dict]] = {
    "876": {
        10515: {"singers": _VALIV, "units": ["vα-liv"]},  # RELOADING
        11081: {"singers": _VALIV, "units": ["vα-liv"]},  # クリスタライン
    },
    # Jupiter の曲はふじわらはじめでユニット（Jupiter）だけの登録で、歌唱メンバーが空なので3人を入れる
    "961": {sid: {"singers": ["天ヶ瀬冬馬", "伊集院北斗", "御手洗翔太"], "units": ["Jupiter"]}
            for sid in (8008, 8009, 8010, 8011, 8012)},
}


def add_manual_songs(only: list[str] | None = None) -> None:
    for b in set(MANUAL_SONGS) | set(SONG_FIXES):
        songs = MANUAL_SONGS.get(b, [])
        f = DATA / "songs" / f"{b}.json"
        if (only and b not in only) or not f.exists():
            continue
        ids = {s["id"] for s in songs} | {"6044-ds"}  # 6044-ds は以前の分け方（2曲）のときの ID
        rows = [s for s in json.loads(f.read_text(encoding="utf-8")) if s["id"] not in ids] + songs
        for s in rows:
            s.update(SONG_FIXES.get(b, {}).get(s["id"], {}))
        rows.sort(key=lambda r: (r["kana"] or r["title"]))
        write(f, rows)
        print(f"[manual] {f.name}: {len(songs)} songs")


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    global USE_CACHE
    flags = {a for a in sys.argv[1:] if a.startswith("--")}
    USE_CACHE = "--no-cache" not in flags
    only = [a for a in sys.argv[1:] if not a.startswith("--")] or None
    if only == ["units"]:  # ユニット名だけ取り直す
        attach_units()
        return
    for b in only or list(BRANDS):
        build_brand(b, BRANDS[b])
    attach_unit_groups(only)
    attach_singers(only)
    # 全ブランドのときと --units のときはユニットも取り直す。1ブランドだけのときは前回の結果を使い回す
    attach_units(only, refresh=only is None or "--units" in flags)
    split_versions(only)
    add_manual_songs(only)
    jst = timezone(timedelta(hours=9))
    write(DATA / "meta.json", {"updated_at": datetime.now(jst).strftime("%Y-%m-%d")})


if __name__ == "__main__":
    main()
