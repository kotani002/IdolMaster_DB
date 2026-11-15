#!/usr/bin/env python3
"""
ジャケットが未設定の曲を iTunes Search API（Apple）で探して data/jackets.json に足す。

  python scripts/fetch_jackets_itunes.py            # 探すだけ（結果は scripts/.cache/itunes_report.txt）
  python scripts/fetch_jackets_itunes.py --apply    # 見つかったものを jackets.json に書き込む
  python scripts/fetch_jackets_itunes.py sc sidem   # ブランドを指定

- 公式ディスコグラフィーで見つからなかった曲だけが対象（設定済みのジャケットは変えない）。
- 曲名が一致し、さらに次のどれかを満たす結果だけを使う（同名の別アーティストの曲を拾わないため）
    ・アーティスト名に歌唱者の名前が入っている
    ・アルバム名・アーティスト名に「アイドルマスター」「IDOLM@STER」などが入っている
    ・アルバムの著作権表記がアイマスのレーベル（BANDAI NAMCO / Lantis）
- 候補が複数あれば、本人歌唱（カラオケ等でない）の中で一番早く発売されたものを使う。
- Apple の画像は「Apple Music・iTunes の紹介」としての利用が前提。サイトの下部に出典を書いている。
- API は1分あたり約20回までなので、間を空けて問い合わせる。結果は scripts/.cache/itunes/ に保存。
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_jackets import classify, norm, song_key  # noqa: E402  照合ルールは公式ディスコグラフィーと共通

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE = Path(__file__).resolve().parent / ".cache" / "itunes"
UA = "imas-presen-sheet/1.0 (fan-made static site; jacket lookup script)"
WAIT_SEC = 3.2

BRAND_WORDS = {
    "ml": ["ミリオンライブ", "MILLION"],
    "cg": ["シンデレラガールズ", "CINDERELLA"],
    "sc": ["シャイニーカラーズ", "SHINY COLORS", "SHINYCOLORS"],
    "sidem": ["SideM", "315"],
    "gm": ["学園アイドルマスター", "学マス", "GAKUEN", "初星"],
}
IMAS_WORDS = ["アイドルマスター", "IDOLM@STER", "IDOLMASTER", "アイマス"]
# 「Columbia」は Sony の Columbia Records など別会社の曲も拾ってしまうので入れない
# （シンデレラガールズ（日本コロムビア）の曲は、作品名の「CINDERELLA」などで拾える）
LABEL_WORDS = ["BANDAI NAMCO", "Lantis", "LANTIS", "バンダイナムコ"]


def get_json(url: str):
    CACHE.mkdir(parents=True, exist_ok=True)
    f = CACHE / (hashlib.sha1(url.encode()).hexdigest() + ".json")
    if f.exists():
        return json.loads(f.read_text(encoding="utf-8"))
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode("utf-8"))
            f.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
            time.sleep(WAIT_SEC)
            return data
        except Exception as e:  # 403/429 は回数制限。少し長めに待つ
            wait = 20 * (attempt + 1)
            print(f"  ! {e} -> retry in {wait}s", file=sys.stderr)
            time.sleep(wait)
    return {"results": []}


def search(term: str) -> list[dict]:
    q = urllib.parse.urlencode({"term": term, "country": "JP", "media": "music", "entity": "song", "limit": 50})
    return get_json(f"https://itunes.apple.com/search?{q}").get("results", [])


def copyright_of(collection_id: int) -> str:
    q = urllib.parse.urlencode({"id": collection_id, "country": "JP"})
    res = get_json(f"https://itunes.apple.com/lookup?{q}").get("results", [])
    return res[0].get("copyright", "") if res else ""


def has_any(text: str, words: list[str]) -> bool:
    t = (text or "").upper()
    return any(w.upper() in t for w in words)


def find(song: dict, brand: str) -> dict | None:
    key = song_key(song["title"])
    singers = [re.sub(r"\s", "", s) for s in song.get("singers") or []]
    seen, cands = set(), []
    for term in (f"{song['title']} アイドルマスター", song["title"]):
        for r in search(term):
            tid = r.get("trackId")
            if tid in seen or not r.get("artworkUrl100"):
                continue
            seen.add(tid)
            k, rank = classify(r.get("trackName", ""))
            if k != key:
                continue
            artist = re.sub(r"\s", "", r.get("artistName", ""))
            text = f"{r.get('collectionName', '')} {r.get('artistName', '')}"
            why = ""
            if singers and any(s and s in artist for s in singers):
                why = "歌唱者"
            elif has_any(text, IMAS_WORDS + BRAND_WORDS.get(brand, [])):
                why = "作品名"
            else:
                cp = copyright_of(r["collectionId"]) if r.get("collectionId") else ""
                if has_any(cp, LABEL_WORDS):
                    why = "レーベル"
            if why:
                cands.append((rank, r.get("releaseDate", "9999"), r, why))
        if cands:
            break
    if not cands:
        return None
    rank, date, r, why = min(cands, key=lambda c: (c[0], c[1]))
    return {
        "url": re.sub(r"/\d+x\d+bb\.(jpg|png)$", "/600x600bb.jpg", r["artworkUrl100"]),
        "track": r.get("trackName", ""),
        "artist": r.get("artistName", ""),
        "album": r.get("collectionName", ""),
        "date": date[:10],
        "why": why,
    }


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    brands = args or [p.stem for p in sorted((DATA / "songs").glob("*.json"))]
    jf = DATA / "jackets.json"
    jackets = json.loads(jf.read_text(encoding="utf-8"))
    report, added = [], 0
    for b in brands:
        songs = json.loads((DATA / "songs" / f"{b}.json").read_text(encoding="utf-8"))
        missing = [s for s in songs if not jackets.get(str(s["id"]))]
        print(f"[{b}] {len(missing)} songs without jacket")
        for s in missing:
            hit = find(s, b)
            if hit:
                report.append(f"OK\t{b}\t{s['title']}\t→ {hit['track']} / {hit['artist']} / {hit['album']} ({hit['date']}, {hit['why']})\t{hit['url']}")
                if apply:
                    jackets[str(s["id"])] = hit["url"]
                added += 1
            else:
                report.append(f"--\t{b}\t{s['title']}\t見つからず")
    out = Path(__file__).resolve().parent / ".cache" / "itunes_report.txt"
    out.write_text("\n".join(report) + "\n", encoding="utf-8")
    if apply:
        jf.write_text(json.dumps(jackets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"found {added} / {len(report)}  ({'applied' if apply else 'dry run'}; report: scripts/.cache/itunes_report.txt)")


if __name__ == "__main__":
    main()
