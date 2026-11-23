#!/usr/bin/env python3
"""
曲ごとの Apple Music（iTunes）の trackId を探して data/previews.json に書く（共有ページのお試し視聴用）。

  python scripts/fetch_previews_itunes.py              # 全ブランド
  python scripts/fetch_previews_itunes.py sc sidem     # ブランドを指定
  python scripts/fetch_previews_itunes.py sc --redo    # 登録済みの曲も探し直す

- 結果は scripts/.cache/previews_report.txt に出る（取り違えが無いか確認用）。
- 照合のしかたはジャケット（fetch_jackets_itunes.py）と同じ。ただし視聴は「曲そのもの」が違うと困るので、
    ・カラオケ・インスト・ソロリミックスは使わない
    ・アーティスト名に歌唱者・ユニット名が入った結果を優先し、次にこのブランドの作品名だけが入ったもの（find の説明）の中から一番早く発売されたもの
    ・ジャケットと違い、「アイドルマスター」だけ・レーベルが同じだけの結果は使わない（別ブランド・別作品の同名曲を拾うため）
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
from fetch_jackets import classify, norm, song_key  # noqa: E402
from fetch_jackets_itunes import BRAND_WORDS, IMAS_WORDS, SKIP_SONGS, has_any, search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "previews.json"
REPORT = Path(__file__).resolve().parent / ".cache" / "previews_report.txt"

# 「曲名 (Ver.Cute)」「Migratory Echoes (ユニット名Ver.)」などサイト側で分けた版の付記
SITE_VERSION = re.compile(r"\s*[（(][^（()）]*ver\.?[)）]\s*$", re.I)


UNIT_KANA = json.loads((DATA / "units.json").read_text(encoding="utf-8")) if (DATA / "units.json").exists() else {}


def find(song: dict, brand: str) -> tuple[dict, str] | None:
    """
    取り違えを防ぐため、次のどちらかを満たす結果だけを使う（ジャケットより厳しくしている）
      1. アーティスト名に歌唱者かユニット名（よみでも可）が入っている
      2. アルバム名・アーティスト名にこのブランドの作品名が入っていて、ほかのブランドの作品名は入っていない
    「アイドルマスター」だけ・レーベルが同じだけ、では使わない
    （以前は使っていたが、SideM の KARMA・シンデレラのメッセージ・ラブライブ!のサウンドトラック・
      同じレーベルの別のアーティストの曲を拾った）
    """
    title = SITE_VERSION.sub("", song["title"])
    key = song_key(title)
    # サイト側で版を分けた曲（「Migratory Echoes (ノクチルVer.)」「(Ver.Cute)」）は、曲名にその版の名前が入った結果だけ使う
    # （分けないと、どの版も同じ1つの版（アンティーカ Ver. など）になってしまった）
    vm = SITE_VERSION.search(song["title"])
    need_ver = norm(re.sub(r"ver\.?", "", vm.group(0), flags=re.I)) if vm else ""
    singers = [norm(re.sub(r"[（(]初代[)）]", "", s)) for s in song.get("singers") or []]
    units = []
    for u in song.get("units") or []:
        units.append(norm(u))
        if UNIT_KANA.get(u):
            units.append(norm(UNIT_KANA[u]))
    names = [x for x in singers + units if len(x) >= 2]
    own_words = BRAND_WORDS.get(brand, [])
    other_words = [w for b, ws in BRAND_WORDS.items() if b != brand for w in ws if not has_any(w, own_words)]
    seen, cands = set(), []
    for term in (f"{title} アイドルマスター", title):
        for r in search(term):
            tid = r.get("trackId")
            if tid in seen or not r.get("previewUrl"):
                continue
            seen.add(tid)
            k, rank = classify(r.get("trackName", ""))
            if k != key or rank != 0:
                continue
            if need_ver and need_ver not in norm(r.get("trackName", "")):
                continue
            artist = norm(r.get("artistName", ""))
            text = f"{r.get('collectionName', '')} {r.get('artistName', '')}"
            prio = None
            if any(n in artist for n in names):
                prio, why = 0, "歌唱者"
            elif has_any(text, own_words + (IMAS_WORDS if brand == "as" else [])) and not has_any(text, other_words):
                # 765AS は作品名が「THE IDOLM@STER」だけのことがあるので、ほかのブランド名が無ければ使う
                prio, why = 1, "作品名"
            if prio is not None:
                cands.append((prio, r.get("releaseDate", "9999"), r, why))
        # 「曲名 アイドルマスター」で見つかれば、曲名だけの検索はしない（同名の別の曲が多いため）
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
                previews.pop(sid, None)  # 探し直して見つからなくなった曲（以前の取り違え）は消す
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
