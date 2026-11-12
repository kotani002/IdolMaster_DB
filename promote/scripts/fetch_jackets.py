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
}


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


PARSERS = {"official_wp": parse_official_wp, "lantis": parse_lantis}


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
    # 「曲名 [歌唱者]」「曲名 作詞:…」のような後ろの付記を落とす
    t = re.sub(r"\s*\[[^\]]*\]\s*$", "", t)
    t = re.sub(r"\s*(作詞|作曲|編曲)\s*[・:：\s].*$", "", t)
    rank = 0
    if re.search(r"カラオケ|off ?vocal|instrumental|inst\.", t, re.I):
        rank = 2
        t = re.sub(r"\s*(オリジナル・?)?カラオケ.*$|\s*[（(]?off ?vocal.*$|\s*[（(]?instrumental.*$", "", t, flags=re.I)
    if re.search(r"ソロ・?リミックス|ソロ・?(バージョン|ver)", t, re.I):
        rank = max(rank, 1)
        t = re.sub(r"\s*\S*\s*ソロ・?(リミックス|バージョン|ver\.?).*$", "", t, flags=re.I)
    t = VERSION_PAREN.sub("", t)
    return norm(t), rank


def song_key(title: str) -> str:
    return norm(VERSION_PAREN.sub("", unicodedata.normalize("NFKC", title)))


# ---------------------------------------------------------------- main

def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    offline = "--offline" in sys.argv
    brand = args[0] if args else "cg"
    src = SOURCES[brand]

    index = fetch(src["index"], offline) or ""
    urls = list(dict.fromkeys(urllib.parse.urljoin(src["index"], html.unescape(u))
                              for u in re.findall(src["link_re"], index)))
    parse = PARSERS[src["parser"]]
    print(f"[{brand}] {len(urls)} disc pages")

    discs = []
    for i, u in enumerate(urls, 1):
        page = fetch(u, offline)
        if page and (d := parse(page, u)):
            discs.append(d)
        if i % 25 == 0:
            print(f"  {i}/{len(urls)}")
    print(f"[{brand}] parsed {len(discs)} discs")

    # 照合キー -> 最良の (優先度, 発売日, ジャケット, CD名)
    best: dict[str, tuple] = {}
    for d in discs:
        for t in d["tracks"]:
            key, rank = classify(t)
            if not key:
                continue
            prio = max(0 if rank < 2 else 2, d.get("penalty", 0))
            cand = (prio, d["date"], d["jacket"], d["title"])
            if key not in best or cand[:2] < best[key][:2]:
                best[key] = cand

    songs = json.loads((DATA / "songs" / f"{brand}.json").read_text(encoding="utf-8"))
    jf = DATA / "jackets.json"
    jackets = json.loads(jf.read_text(encoding="utf-8")) if jf.exists() else {}
    matched, unmatched = 0, []
    for s in songs:
        hit = best.get(song_key(s["title"]))
        if hit:
            jackets[str(s["id"])] = hit[2]
            matched += 1
        else:
            unmatched.append(s["title"])

    jf.write_text(json.dumps(jackets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (CACHE / f"{brand}_unmatched.txt").write_text("\n".join(unmatched) + "\n", encoding="utf-8")
    print(f"[{brand}] matched {matched}/{len(songs)}  (unmatched list: scripts/.cache/{brand}_unmatched.txt)")


if __name__ == "__main__":
    main()
