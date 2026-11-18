#!/usr/bin/env python3
"""
公式サイトのディスコグラフィーから、data/songs/<brand>.json の各曲に対応する
ジャケット画像URLを探して data/jackets.json に書き込む。

  python scripts/fetch_jackets.py cg            # 取得 + 照合
  python scripts/fetch_jackets.py cg --offline  # キャッシュだけで照合をやり直す

- 各CDの詳細ページ（ジャケット・発売日・収録曲）を取得し、曲名で照合する。
- 同じ曲が複数のCDに入っている場合は「本人版（M@STER VERSION 含む）の中で一番早い発売日」の
  CDのジャケットを使う。カラオケ・ソロリミックスしか見つからない曲はそれを使う。
- ページは scripts/.cache/ に保存し、2回目以降は再取得しない。
- 照合できなかった曲は scripts/.cache/<brand>_unmatched.txt に出力する。
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import sys
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from fetch_data import CROSSOVER_SONGS, EXTRA_SONGS  # 越境曲・他ブランドから足した曲（ブランドごとにジャケットを持つ）

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = Path(__file__).resolve().parent / ".cache"
UA = "imas-presen-sheet/1.0 (fan-made static site; jacket lookup script)"
WAIT_SEC = 1.5

# index: CD詳細ページの一覧が載っているページ / link_re: そこから詳細ページURLを拾う正規表現
SOURCES = {
    "cg": {  # シンデレラガールズ公式ポータル
        "index": "https://cinderellagirls.idolmaster-official.jp/wp-sitemap-posts-discography-1.xml",
        "link_re": r"<loc>([^<]+)</loc>",
        "parser": "official_wp",
    },
    "ml": {  # ランティス ミリオンライブ！サイト
        "index": "https://lantis.jp/imas/index.html",
        "link_re": r'href="(release_[^"]+\.html)"',
        "parser": "lantis",
    },
    "sc": {  # ランティス シャイニーカラーズサイト（ミリオンと同じページ構成）
        "index": "https://shinycolors.lantis.jp/discography/",
        "link_re": r'href="(https://shinycolors\.lantis\.jp/releaseinfo/[^"]+)"',
        "parser": "lantis",
    },
    "sidem": {  # ランティス SideM サイト（ミリオンと同じページ構成）
        "index": "https://www.lantis.jp/sidem/index.html",
        "link_re": r'href="(releaseinfo/release_[^"]+\.html)"',
        "parser": "lantis",
    },
    "gm": {  # 学園アイドルマスター 公式レーベルサイト（Next.js + microCMS）
        "index": "https://gakuen-label.idolmaster-official.jp/discography",
        "link_re": r'href="(/discography/[A-Za-z0-9_-]+)"',
        "parser": "gakuen_label",
    },
    "as": {  # 日本コロムビア アイドルマスターサイト（765AS とシンデレラが同じページ。765AS の見出しの範囲だけ使う）
        "index": "https://columbia.jp/idolmaster/",
        "link_re": r'href="([^"#]+\.html)',
        # （開始の目印, 終わりの目印）。ディスコグラフィーの「MASTERPIECE」〜「OTHER」、「STARLIT SEASON」〜「DVD / BD」、
        # ラジオ（RADIO・STATION!!!。DEAD or ALIVE などラジオの曲も 765AS の曲として登録されている）
        "regions": [('id="discography"', "CINDERELLA MASTER Series 001-072"),
                    ("STARLIT SEASON", "CINDERELLA PARTY! Series")],
        "parser": "columbia",
    },
}
# 876プロ（ディアリースターズ）の CD も同じ日本コロムビアのサイト（DREAM SYMPHONY・OTHER など）にある
SOURCES["876"] = SOURCES["as"]


# ---------------------------------------------------------------- fetch

def fetch(url: str, offline: bool) -> str | None:
    CACHE.mkdir(exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".html")
    if f.exists():
        return f.read_text(encoding="utf-8")
    if offline:
        return None
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read()
                cs = r.headers.get_content_charset()
            # ランティスは Shift_JIS のページがあるので、ヘッダー → meta の順に文字コードを判定
            if not cs:
                mm = re.search(rb'charset=["\']?([\w-]+)', raw[:3000], re.I)
                cs = mm.group(1).decode() if mm else "utf-8"
            if cs.lower() in ("shift_jis", "sjis", "x-sjis", "shift-jis"):
                cs = "cp932"
            body = raw.decode(cs, "replace")
            f.write_text(body, encoding="utf-8")
            time.sleep(WAIT_SEC)
            return body
        except Exception as e:
            print(f"  ! {url}: {e}", file=sys.stderr)
            time.sleep(5 * (attempt + 1))
    return None


# ---------------------------------------------------------------- parse

def text(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def clean_url(u: str, base: str) -> str:
    u = urllib.parse.urljoin(base, html.unescape(u))
    return urllib.parse.quote(u, safe=":/%?=&#~+")


def parse_lantis(page: str, url: str) -> dict | None:
    """lantis.jp/imas/release_*.html"""
    # ジャケットは通常 release_img の中だが、枠の外（直前）に置かれたページもある。
    # リリース情報の範囲（id="release" 〜 タイトル）の中で、見出しアイコン(parts/)・サムネイル以外の最初の画像を使う
    start = page.find('id="release"')
    end = page.find('class="titles"', max(start, 0))
    region = page[start:end] if start >= 0 and end > start else ""
    cands = [s for s in re.findall(r'<img[^>]+src="([^"]+)"', region)
             if "parts/" not in s and "/thumb/" not in s]
    if not cands:
        return None
    m = re.match(r"(.*)", cands[0])
    d = (re.search(r"発売日[：:]\s*(\d{4})\s*[/.年]\s*(\d{1,2})\s*[/.月]\s*(\d{1,2})", page)
         or re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*RELEASE", page))
    date = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else "9999-99-99"
    title = re.search(r'<div class="titles">.*?<h2>(.*?)</h2>', page, re.S)
    # 収録曲は「index」見出しの後ろに「01：曲名<br>」の形で並ぶ
    tracks = []
    i = page.find("h3_index")
    if i < 0:
        i = page.find("release_index")  # シャイニーカラーズのサイトは見出し画像の名前が違う
    if i < 0:
        i = page.find('h3_tit">Index<')  # SideM のサイトは見出しが文字
    if i >= 0:
        seg = page[i:]
        end = re.search(r"<h3|<section|class=\"CD_area\"", seg[10:])
        seg = re.sub(r"<!--.*?-->", "", seg[: end.start() + 10 if end else 6000], flags=re.S)
        for line in re.split(r"<br\s*/?>|</p>|<p[^>]*>|\n", seg):
            t = text(line)
            m2 = re.match(r"^(?:disc\s*\d+\s*[-‐]?\s*)?m?\d{1,2}\s*[：:．.]\s*(.+)$", unicodedata.normalize("NFKC", t), re.I)
            if m2:
                tracks.append(m2.group(1).strip())
        if not tracks:
            # 番号なし形式：<p>曲名<br>作詞…<br>歌…</p> → 各 <p> の1行目が曲名
            for para in re.findall(r"<p[^>]*>(.*?)</p>", seg, re.S):
                first = text(re.split(r"<br\s*/?>", para)[0])
                if first and not re.match(r"^(作詞|作曲|編曲|歌|…|※|&nbsp;)", first) and "」" not in first[:1]:
                    tracks.append(first)
    return {
        "url": url,
        "title": text(title.group(1)) if title else "",
        "jacket": clean_url(m.group(1), url),
        "date": date,
        "tracks": tracks,
        # ライブBD（LABX）のジャケットはCDで見つからない曲にだけ使う
        "penalty": 2 if "LABX" in url.upper() else 0,
    }


def parse_official_wp(page: str, url: str) -> dict | None:
    """各ブランド公式ポータル（WordPress）の /discography/<slug>/"""
    m = re.search(r'<img[^>]+src="([^"]*/wp-content/uploads/[^"]+)"', page)
    if not m:
        return None
    jacket = clean_url(m.group(1), url)
    d = re.search(r'tracklist-onsale">\s*<span>\s*(\d{4})\.(\d{1,2})\.(\d{1,2})', page)
    date = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else "9999-99-99"
    tracks = [text(t) for t in re.findall(
        r'<dl class="discography-detail__tracklist-song">\s*<dt>\s*<span>[^<]*</span>(.*?)</dt>', page, re.S)]
    title = re.search(r"<title>(.*?)</title>", page, re.S)
    return {
        "url": url,
        "title": text(title.group(1)).split(" | ")[0] if title else "",
        "jacket": jacket,
        "date": date,
        "tracks": tracks,
    }


def parse_gakuen_label(page: str, url: str) -> dict | None:
    """gakuen-label.idolmaster-official.jp/discography/<id>"""
    # 新譜は figure の先頭に「NEW」バッジの画像があるので、microCMS の画像を探す
    m = re.search(r'<figure class="detail_thumb_item[^"]*">.*?<img src="(https://images\.microcms-assets\.io/[^"]+)"', page, re.S)
    if not m:
        return None
    # microCMS（imgix）の画像。webp 指定を外し、画像出力（html2canvas）向けに JPEG・600px にする
    jacket = html.unescape(m.group(1)).split("?")[0] + "?fm=jpg&w=600&q=85"
    d = re.search(r'detail_releaseDate[^"]*"[^>]*>\s*(\d{4})\.(\d{1,2})\.(\d{1,2})', page)
    date = f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d else "9999-99-99"
    title = re.search(r'<h1 class="detail_ttl[^"]*"[^>]*>(.*?)</h1>', page, re.S)
    tracks = [text(t) for t in re.findall(
        r'<li class="detail_track_item[^"]*"[^>]*><span[^>]*>[^<]*</span><span[^>]*>(.*?)</span>', page, re.S)]
    title = text(title.group(1)) if title else ""
    # 配信シングルのページは収録曲リストが無く、タイトルがそのまま曲名
    if not tracks and title:
        tracks = [title]
    return {
        "url": url,
        "title": title,
        "jacket": jacket,
        "date": date,
        "tracks": tracks,
    }


COLUMBIA_NOTE = re.compile(r"[（(][^（()）]*(より|新曲|カバー|新録|収録|共通|用\s*[)）]|試聴)[^（()）]*([)）]|$)")


def columbia_track(s: str) -> str:
    """コロムビアの収録曲1行から、照合に使う曲名（＋カラオケ・ソロリミックスの区別）だけを残す"""
    t = text(re.sub(r"<br\s*/?>", " ", s, flags=re.I))
    t = re.sub(r"\s+", " ", t).strip()
    t = re.sub(r"^ボーナス・?トラック\s*|^M\d+\.\s*", "", t)  # 「M11. はっぴぃ☆ほりっく」
    t = re.sub(r"\s*[（(]([^（()）]*ソロ・?リミックス)[)）]", r" \1", t)  # 「君のままで（春香ソロ・リミックス）」→ 空白区切りに
    t = re.sub(r"\s*\[試聴\].*$", "", t)
    t = re.sub(r"\s*歌\s*[：:].*$", "", t)  # 「曲名　歌：天海春香」
    t = re.sub(r"\s*[（(]?\s*(作詞|作曲|編曲)\s*[：:].*$", "", t)  # 「団結（作詞：…」
    t = re.sub(r"\s*「[^」]*」\s*で選ばれた.*$", "", t)  # 「…REQUEST FESTIVAL！」で選ばれたカバー曲
    t = re.sub(r"^.*?(テーマ|劇中歌|挿入歌|主題歌|新曲)\s*「", "", t)  # 「#6劇中歌「SMOKY THRILL…」「新曲「空」」
    t = re.sub(r"\s*[-－‐]\s*[^-－‐]*(バージョン|Ver\.?)\s*[-－‐]\s*$", "", t, flags=re.I)  # 「-765PRO ALLSTARS バージョン-」
    t = re.sub(r"\s+\S*バージョン$", "", t)  # 「VOY＠GER 765PRO ALLSTARSバージョン」
    t = re.sub(r"\s+新曲$|\s*\*$", "", t)  # 「ふるふるフューチャー☆ 新曲」「GO MY WAY!! *」
    t = COLUMBIA_NOTE.sub("", t)  # 「（春香用新曲)」「（アルバム「Your Song」より)」などの説明
    t = re.sub(r"\s*[（(]\s*$", "", t)
    return t.strip(" 　「」")


# 使わないページ（ジャケット画像が 120px と小さい：RADIO～歌姫楽園～／MASTER MOVIE）
COLUMBIA_SKIP = ("/2006/33906-4585.html",)


def parse_columbia(page: str, url: str) -> list[dict]:
    """columbia.jp/idolmaster/ の CD ページ。年代でページの作りが違う（2006〜2010年は表組み、
    2011年以降は discoTitle / section.CD）。1ページに複数の CD が載っていることがあるので CD ごとのリストで返す"""
    for mark in ('id="ContentNav"', "<footer", 'id="footer"'):  # 下の「ほかの CD」一覧は除く
        i = page.find(mark)
        if i > 0:
            page = page[:i]
    # CD ごとの区切り（MASTER ARTIST 4 のページは class="cinderella" という名前の枠）
    starts = [m.start() for m in re.finditer(r'class="discoTitle"|<section class="CD"|<div class="cinderella"', page)]
    blocks = [page[a:b] for a, b in zip(starts, starts[1:] + [len(page)])] if starts else [page]
    page_title = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    page_title = re.sub(r"^.*?[｜|]\s*", "", text(page_title.group(1))) if page_title else ""
    year_dir = re.search(r"/idolmaster/(\d{4})(?:new)?/", url)
    if any(url.endswith(s) for s in COLUMBIA_SKIP):
        return []
    out = []
    for blk in blocks:
        m = (re.search(r'class="jacket"[^>]*>\s*<img[^>]+src="([^"]+)"', blk)
             # 古いページ：images/COCX-34387.jpg のように品番だけの名前の画像がジャケット（png は飾り付きの合成画像なので使わない）
             or re.search(r'<img[^>]+src="((?:[^"]*/)?[A-Z]{2,4}-?\d{3,5}\.jpg)"', blk, re.I))
        # 2009年ごろのページ（RADIO LONG TIME・歌道場・STATION!!! FIRST TRAVEL など）は、ジャケットを CSS の背景画像
        # （#jacket { background: url(images/COCX-35616.png) }）で出している。画像は 924×561 の透過 PNG で、
        # 左上の 494px 四方がジャケット（下は鏡の映り込み）なので、画像変換サービスでその部分だけ切り出して使う。
        # ほかの CD に入っていない曲（ラジオの曲・ディアリースターズの曲など）にだけ使う（下の penalty。
        # 同じ作りの DREAM SYMPHONY などに入っている 765AS の曲は、今の公式ジャケットのままにする）
        bg = None if m else re.search(r"#jacket\s*\{[^}]*url\(([^)]+\.png)\)", page)
        # DREAM SYMPHONY（ディアリースターズ、/idolmaster/ds/）は <img src="images/COCX-35795.png" class="jacket">（四角いジャケット）
        ds = None if m or bg else re.search(r'<img[^>]+src="([^"]+\.png)"[^>]*class="jacket"', blk)
        if not m and not bg and not ds:
            continue
        jacket = (clean_url((m or ds).group(1), url) if m or ds else
                  "https://wsrv.nl/?url=" + clean_url(bg.group(1).strip("'\""), url).split("://", 1)[1]
                  + "&cx=30&cy=0&cw=494&ch=494&output=jpg&q=90")
        d = (re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*on\s*sale", blk, re.I)
             or re.search(r"(\d{4})年\s*(\d{1,2})月\s*(\d{1,2})日\s*(?:[（(][^）)]*[）)])?\s*発売", blk)
             or re.search(r"(\d{4})\.(\d{1,2})\.(\d{1,2})\s*on\s*sale", page, re.I))
        # 日付の無い古いページは、置き場所の年（/2007new/ など）の年末として扱う
        date = (f"{d.group(1)}-{int(d.group(2)):02d}-{int(d.group(3)):02d}" if d
                else f"{year_dir.group(1)}-12-31" if year_dir else "9999-99-99")
        blk2 = re.sub(r"<!--.*?-->", "", blk, flags=re.S)
        # メドレーの中身（MASTER ARTIST 3 Prologue の「ソロ新曲メドレー」）は曲として数えない
        blk2 = re.sub(r'<ul id="medley">.*?</ul>', "", blk2, flags=re.S)
        blk2 = re.sub(r"<a\s[^>]*>.*?</a>", "", blk2, flags=re.S | re.I)  # 試聴リンク
        rows = []
        for tag, ol in re.findall(r"<(ol|ul)[^>]*>(.*?)</(?:ol|ul)>", blk2, re.S | re.I):
            for li in re.split(r"<li[^>]*>", ol, flags=re.I)[1:]:
                h = re.search(r"<h\d[^>]*>(.*?)</h\d>", li, re.S | re.I)
                if h:
                    rows.append(h.group(1))
                elif tag.lower() == "ol":  # <ul> は曲名の見出し（<h3>）がある行だけ（メニューなどを拾わない）
                    rows.append(re.split(r"<br\s*/?>", li, flags=re.I)[0])
        rows += re.findall(r'<td class="no">\s*\d+\.?\s*</td>\s*<td[^>]*>(.*?)</td>', blk2, re.S | re.I)
        rows += [re.split(r"<br\s*/?>", r, flags=re.I)[0]
                 for r in re.findall(r"<dt>\s*\d+\.?\s*</dt>\s*<dd>(.*?)</dd>", blk2, re.S | re.I)]
        tracks = [t for t in (columbia_track(r) for r in rows) if t]
        # 「紅白応援V(ビクトリー)」「灯（あかし)」のような読み・副題のかっこを外した形でも照合できるようにする
        # （カラオケ・バージョン・ソロリミックスのかっこは外さない）
        tracks += [v for t in tracks
                   if (v := re.sub(r"\s*[（(](?![^（()）]*(カラオケ|vocal|instrumental|ver|mix|size|ソロ|m@ster))[^（()）]*[)）]\s*",
                                   "", t, flags=re.I).strip()) and v != t]
        h = re.search(r"<h[12][^>]*>(.*?)</h[12]>", blk, re.S)
        title = re.sub(r"\s+", " ", text(re.sub(r"<br[^>]*>", " ", h.group(1)))) if h and starts else page_title
        cat = re.search(r"([A-Z]{2,4})-?\d+", (m or bg or ds).group(1).split("/")[-1])
        out.append({
            "url": url,
            "title": title or page_title,
            "jacket": jacket,
            "date": date,
            "tracks": tracks,
            # Blu-ray・DVD（COXC/COBC/XT）のジャケットは CD で見つからない曲にだけ使う。
            # ラジオの CD（歌姫楽園・STATION!!! など）は、ほかの CD に無い曲（ラジオの曲）にだけ使う
            "penalty": (2 if cat and cat.group(1).upper() in ("COXC", "COBC", "COBA", "XT")
                        else 1 if bg or ds or re.search(r"RADIO|STATION", title or page_title, re.I) else 0),
        })
    return out


PARSERS = {"official_wp": parse_official_wp, "lantis": parse_lantis, "gakuen_label": parse_gakuen_label,
           "columbia": parse_columbia}


# ---------------------------------------------------------------- match

VERSION_PAREN = re.compile(
    r"[（(［\[〔][^）)］\]〕]*?(version|ver\.?|mix|edit|size|arrange|remaster|m@ster)[^）)］\]〕]*[）)］\]〕]", re.I)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s).lower()
    s = "".join(c for c in s if unicodedata.category(c)[0] in "LN")
    # カタカナ → ひらがな（表記ゆれ対策）
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def classify(track: str) -> tuple[str, int]:
    """収録曲名 -> (照合キー, ランク)  0:本人版 1:ソロリミックス等 2:カラオケ"""
    t = unicodedata.normalize("NFKC", track)
    # カラオケ判定は付記を落とす前に行う（学マスは「曲名 [Instrumental]」の形）
    karaoke = re.search(r"カラオケ|off ?vocal|instrumental|inst\.", t, re.I)
    # 「曲名 [歌唱者]」「曲名 作詞:…」のような後ろの付記を落とす
    t = re.sub(r"\s*\[[^\]]*\]\s*$", "", t)
    t = re.sub(r"\s*(作詞|作曲|編曲)\s*[・:：\s].*$", "", t)
    # 「曲名 / アイドル名 (CV.声優)」（シャイニーカラーズ HOPEFUL FE@THERS など）の歌唱者部分を落とす
    t = re.sub(r"\s+/\s+[^/]*\(CV\.[^)]*\)\s*$", "", t)
    rank = 0
    if karaoke:
        rank = 2
        t = re.sub(r"\s*(オリジナル・?)?カラオケ.*$|\s*[（(]?off ?vocal.*$|\s*[（(]?instrumental.*$", "", t, flags=re.I)
    if re.search(r"ソロ・?リミックス|ソロ・?(バージョン|ver)", t, re.I):
        rank = max(rank, 1)
        t = re.sub(r"\s*\S*\s*ソロ・?(リミックス|バージョン|ver\.?).*$", "", t, flags=re.I)
    t = VERSION_PAREN.sub("", t)
    return norm(t), rank


def song_key(title: str) -> str:
    return norm(VERSION_PAREN.sub("", unicodedata.normalize("NFKC", title)))


# ---------------------------------------------------------------- 選べる公式ジャケット

# 2つのユニットが同じ曲をそれぞれのCDで出すシリーズ。曲ごとに両方のジャケットを data/jacket_alts.json に書き、
# サイトのジャケット画面で選べるようにする（例：ムゲンダイグロウアップ！ → FRAME盤 / もふもふえん盤）
ALT_SERIES = {"sidem": re.compile(r"F[@＠]NTASTIC COMBINATION")}
# 手で決めた「選べるジャケット」（ブランド → 曲ID → 盤のリスト）。1つ目は jacket_overrides.json の既定と同じにする
_DS_ALT = "https://columbia.jp/idolmaster/imasnews/images/SACX-1148L.jpg"
_DS_ALT_CD = "876 PRODUCTION FES. Alternative Tracks Collection【Dearly Stars盤】（SACX-1148）"
_VALIV_ALT = ("https://wsrv.nl/?url=https%3A%2F%2Fpbs.twimg.com%2Fmedia%2FHLgCCwAbsAAUxqz%3Fformat%3Djpg%26name%3Dlarge"
              "&cx=142&cy=164&cw=427&ch=427&output=jpg&q=90")
_VALIV_PORTAL = "https://images.microcms-assets.io/assets/baf766c5604941f6b3f05d92db6ab7e8/"  # vα-liv 公式ディスコグラフィー
MANUAL_ALTS = {
    "876": {
        # “HELLO!!”：ディアリースターズ盤（DREAM SYMPHONY 00）と vα-liv盤（876 PRODUCTION FES. Alternative Tracks
        # Collection【vα-liv盤】）。vα-liv盤は公式サイトに画像が無いので、ASOBINOTES（レーベル）の X の告知画像
        # （https://x.com/ASOBINOTES876/status/2069406367241392191）からジャケット部分を画像変換サービスで切り出す
        "6044": [
            {"jacket": "https://columbia.jp/idolmaster/ds/images/COCC-16298.png", "label": "Dearly Stars盤",
             "cd": "THE IDOLM@STER DREAM SYMPHONY 00 “HELLO!!”"},
            {"jacket": _VALIV_ALT,
             "label": "vα-liv盤", "cd": "876 PRODUCTION FES. Alternative Tracks Collection【vα-liv盤】"},
        ],
        # ディアリースターズも歌った曲（876 PRODUCTION FES. Alternative Tracks Collection【Dearly Stars盤】SACX-1148）は、
        # vα-liv（または元）の盤と選べるようにする（ユーザー判断）。The world is all one !! は 765AS の曲なので「876:曲ID」
        "876:5041": [
            {"jacket": _DS_ALT, "label": "Dearly Stars盤", "cd": _DS_ALT_CD},
            {"jacket": _VALIV_ALT, "label": "vα-liv盤", "cd": "876 PRODUCTION FES. Alternative Tracks Collection【vα-liv盤】"},
        ],
        "10515": [  # RELOADING（vα-liv 版は配信でリローディングの曲名）
            {"jacket": _VALIV_PORTAL + "1bbb5bddfa5f4427a144273ef3e9adef/58ced8645b3590cbce39715a69f533062ca8cc552015349942d6fcfa04a99400.jpg?fm=jpg&w=600&q=85",
             "label": "vα-liv盤", "cd": "vα-liv Project 1st song『リローディング』"},
            {"jacket": _DS_ALT, "label": "Dearly Stars盤", "cd": _DS_ALT_CD},
        ],
        "11081": [  # クリスタライン
            {"jacket": _VALIV_PORTAL + "164eafa44cb241b7ba230b6a179f596a/%E3%82%AF%E3%83%AA%E3%82%B9%E3%82%BF%E3%83%A9%E3%82%A4%E3%83%B3_resize.jpg?fm=jpg&w=600&q=85",
             "label": "vα-liv盤", "cd": "vα-liv Project 2nd song『クリスタライン』"},
            {"jacket": _DS_ALT, "label": "Dearly Stars盤", "cd": _DS_ALT_CD},
        ],
    },
}


def write_alts(brand: str, discs: list, songs: list, best: dict) -> None:
    pat = ALT_SERIES.get(brand)
    af = DATA / "jacket_alts.json"
    alts = json.loads(af.read_text(encoding="utf-8")) if af.exists() else {}
    ids = {str(s["id"]) for s in songs}
    alts = {k: v for k, v in alts.items() if k not in ids}  # このブランドの分は作り直す
    if pat:
        found: dict[str, dict[str, tuple]] = {}
        for d in discs:
            if not pat.search(d["title"]) or d.get("penalty", 0):
                continue
            title = re.sub(r"\s+", " ", d["title"]).strip()
            label = re.split(r"[～\-]\s", title)[-1].strip()  # CD名の最後のユニット名
            for t in d["tracks"]:
                key, rank = classify(t)
                if key and rank < 2:
                    found.setdefault(key, {})[d["jacket"]] = (d["date"], label, title)
        for s in songs:
            key = song_key(s["title"])
            js = found.get(key, {})
            hit = best.get(key)
            # そのシリーズが初出の合同曲だけ（2枚あって、自動で選ぶジャケットもその中にある曲）。全体曲などは除く
            if len(js) == 2 and hit and hit[2] in js:
                alts[str(s["id"])] = [{"jacket": j, "label": f"{lb}盤", "cd": t}
                                      for j, (dt, lb, t) in sorted(js.items(), key=lambda kv: (kv[1][0], kv[0]))]
    alts.update(MANUAL_ALTS.get(brand, {}))
    af.write_text(json.dumps(alts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(1 for k in alts if k in ids)
    if n:
        print(f"[{brand}] {n} songs with selectable jackets (data/jacket_alts.json)")


# ---------------------------------------------------------------- main

def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    offline = "--offline" in sys.argv
    brand = args[0] if args else "cg"
    src = SOURCES[brand]

    index = fetch(src["index"], offline) or ""
    if src.get("regions"):  # 一覧ページの一部（そのブランドの見出しの範囲）だけ使う
        parts, pos = [], 0
        for a, b in src["regions"]:
            s = index.find(a, pos)
            e = index.find(b, s + 1) if s >= 0 else -1
            if s < 0 or e < 0:
                print(f"  ! region not found: {a} 〜 {b}", file=sys.stderr)
                continue
            parts.append(index[s:e])
            pos = e
        index = "\n".join(parts)
    urls = list(dict.fromkeys(urllib.parse.urljoin(src["index"], html.unescape(u))
                              for u in re.findall(src["link_re"], index)))
    parse = PARSERS[src["parser"]]
    print(f"[{brand}] {len(urls)} disc pages")

    discs = []
    for i, u in enumerate(urls, 1):
        page = fetch(u, offline)
        if page and (d := parse(page, u)):
            discs.extend(d if isinstance(d, list) else [d])  # 1ページに複数の CD があるサイト（コロムビア）はリスト
        if i % 25 == 0:
            print(f"  {i}/{len(urls)}")
    print(f"[{brand}] parsed {len(discs)} discs")

    # 照合キー -> 最良の (優先度, 発売日, ジャケット, CD名)
    best: dict[str, tuple] = {}
    # 越境曲用：ライブ映像を除いて一番早いCD（各ブランド盤のシングルはカラオケ版しか拾えないことがあるので、版は問わない）
    first_cd: dict[str, tuple] = {}
    for d in discs:
        for t in d["tracks"]:
            key, rank = classify(t)
            if not key:
                continue
            prio = max(0 if rank < 2 else 2, d.get("penalty", 0))
            cand = (prio, d["date"], d["jacket"], d["title"])
            if key not in best or cand[:2] < best[key][:2]:
                best[key] = cand
            c2 = (d.get("penalty", 0), d["date"], d["jacket"], d["title"])
            if re.search(r"SOLO COLLECTION", d["title"], re.I):  # ライブ会場限定のソロ集は越境曲のジャケットにしない
                continue
            if key not in first_cd or c2[:2] < first_cd[key][:2]:
                first_cd[key] = c2

    songs = json.loads((DATA / "songs" / f"{brand}.json").read_text(encoding="utf-8"))
    write_alts(brand, discs, songs, best)
    jf = DATA / "jackets.json"
    jackets = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
    matched, unmatched = 0, []
    for s in songs:
        if s["id"] in CROSSOVER_SONGS:
            # 越境曲はブランドごとに別の盤が出るので「ブランド:曲ID」に、そのブランドの盤のジャケットを入れる
            hit = first_cd.get(song_key(s["title"]))
            if hit and hit[0] == 0:
                jackets[f"{brand}:{s['id']}"] = hit[2]
                matched += 1
            continue
        hit = best.get(song_key(s["title"]))
        if hit and s["id"] in EXTRA_SONGS.get(brand, []):
            # 他ブランドの曲として足した曲（ハーモニクスなど）は、元のブランドのジャケットを上書きしないよう「ブランド:曲ID」に入れる
            jackets[f"{brand}:{s['id']}"] = hit[2]
            matched += 1
        elif hit:
            jackets[str(s["id"])] = hit[2]
            matched += 1
        else:
            unmatched.append(s["title"])

    # 手で指定したジャケット（data/jacket_overrides.json）は自動の照合より優先する。
    # "_all" は越境曲などの既定のジャケット（そのブランドの盤が無いときに使う）
    of = DATA / "jacket_overrides.json"
    all_ov = json.loads(of.read_text(encoding="utf-8")) if of.exists() else {}
    overrides = all_ov.get(brand, {})
    for sid, o in overrides.items():
        # 越境曲・他ブランドから足した曲は、元のブランドのジャケットを上書きしないよう「ブランド:曲ID」に入れる
        own = sid.isdigit() and (int(sid) in CROSSOVER_SONGS or int(sid) in EXTRA_SONGS.get(brand, []))
        jackets[f"{brand}:{sid}" if own else sid] = o["jacket"]
    for sid, o in all_ov.get("_all", {}).items():
        jackets[sid] = o["jacket"]
    if overrides:
        print(f"[{brand}] {len(overrides)} jackets from jacket_overrides.json")

    jf.write_text(json.dumps(jackets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (CACHE / f"{brand}_unmatched.txt").write_text("\n".join(unmatched) + "\n", encoding="utf-8")
    print(f"[{brand}] matched {matched}/{len(songs)}  (unmatched list: scripts/.cache/{brand}_unmatched.txt)")


if __name__ == "__main__":
    main()
