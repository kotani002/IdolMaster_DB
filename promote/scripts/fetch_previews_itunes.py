#!/usr/bin/env python3
"""
曲ごとの Apple Music（iTunes）の trackId を探して data/previews.json に書く（共有ページのお試し視聴用）。

  python scripts/fetch_previews_itunes.py              # 全ブランド
  python scripts/fetch_previews_itunes.py sc sidem     # ブランドを指定
  python scripts/fetch_previews_itunes.py sc --redo    # 登録済みの曲も探し直す

- 結果は scripts/.cache/previews_report.txt に出る（取り違えが無いか確認用）。
- 照合のしかたはジャケット（fetch_jackets_itunes.py）と同じ。ただし視聴は「曲そのもの」が違うと困るので、
    ・カラオケ・インスト・ソロリミックスは使わない
    ・歌唱者の名前が入った結果を優先し、次に作品名・レーベルで確かめたものの中から一番早く発売されたもの
- 試聴URL（previewUrl）は変わることがあるので保存しない。共有ページを開いたときに trackId で問い合わせる。
- 問い合わせ結果は scripts/.cache/itunes/ に保存されるので（ジャケットのスクリプトと共通）、2回目以降は速い。
  API は1分あたり約20回までなので、初回は1ブランド数十分かかる。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from fetch_jackets import classify, song_key  # noqa: E402
from fetch_jackets_itunes import (BRAND_WORDS, IMAS_WORDS, LABEL_WORDS, SKIP_SONGS,  # noqa: E402
                                  copyright_of, has_any, search)

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "previews.json"
REPORT = Path(__file__).resolve().parent / ".cache" / "previews_report.txt"

# 「曲名 (Ver.Cute)」「Migratory Echoes (ユニット名Ver.)」などサイト側で分けた版の付記
SITE_VERSION = re.compile(r"\s*[（(][^（()）]*ver\.?[)）]\s*$", re.I)


def find(song: dict, brand: str) -> tuple[dict, str] | None:
    title = SITE_VERSION.sub("", song["title"])
    key = song_key(title)
    singers = [re.sub(r"\s|[（(]初代[)）]", "", s) for s in song.get("singers") or []]
    seen, cands, cp_checks = set(), [], 0
    for term in (f"{title} アイドルマスター", title):
        for r in search(term):
            tid = r.get("trackId")
            if tid in seen or not r.get("previewUrl"):
                continue
            seen.add(tid)
            k, rank = classify(r.get("trackName", ""))
            if k != key or rank != 0:
                continue
            artist = re.sub(r"\s", "", r.get("artistName", ""))
            text = f"{r.get('collectionName', '')} {r.get('artistName', '')}"
            prio = None
            if singers and any(s and s in artist for s in singers):
                prio, why = 0, "歌唱者"
            elif has_any(text, IMAS_WORDS + BRAND_WORDS.get(brand, [])):
                prio, why = 1, "作品名"
            elif cp_checks < 4:  # レーベルの確認は1曲4件まで（同名の別の曲で問い合わせが増えすぎないように）
                cp_checks += 1
                cp = copyright_of(r["collectionId"]) if r.get("collectionId") else ""
                if has_any(cp, LABEL_WORDS):
                    prio, why = 1, "レーベル"
            if prio is not None:
                cands.append((prio, r.get("releaseDate", "9999"), r, why))
        # 「曲名 アイドルマスター」で見つかれば、曲名だけの検索はしない（同名の別の曲が多く、レーベルの確認で時間がかかるため）
        if cands:
            break
    if not cands:
        return None
    _, _, r, why = min(cands, key=lambda c: (c[0], c[1]))
    return r, why


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    redo = "--redo" in sys.argv
    brands = args or [p.stem for p in sorted((DATA / "songs").glob("*.json"))]
    previews = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    previews.pop("_comment", None)
    report, found, total = [], 0, 0
    for b in brands:
        songs = json.loads((DATA / "songs" / f"{b}.json").read_text(encoding="utf-8"))
        print(f"[{b}] {len(songs)} songs", flush=True)
        for i, s in enumerate(songs, 1):
            sid = str(s["id"])
            if s["title"] in SKIP_SONGS.get(b, set()):
                continue
            total += 1
            if sid in previews and not redo:
                found += 1
                continue
            hit = find(s, b)
            if hit:
                r, why = hit
                previews[sid] = r["trackId"]
                found += 1
                report.append(f"OK\t{b}\t{s['title']}\t→ {r.get('trackName')} / {r.get('artistName')} / "
                              f"{r.get('collectionName')} ({r.get('releaseDate', '')[:10]}, {why})\t{r['trackId']}")
            else:
                report.append(f"--\t{b}\t{s['title']}\t見つからず")
            if i % 50 == 0:
                print(f"  {i}/{len(songs)}", flush=True)
                save(previews)
    save(previews)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"previews: {found} / {total}  (report: scripts/.cache/previews_report.txt)")


def save(previews: dict) -> None:
    body = {"_comment": "楽曲ID(ふじわらはじめの song_id) -> Apple Music の trackId。scripts/fetch_previews_itunes.py で作成"}
    body.update(sorted(previews.items(), key=lambda kv: kv[0]))
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
