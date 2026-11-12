#!/usr/bin/env python3
"""
ジャケット未設定の曲を CSV に書き出す / 記入済みの CSV を data/jackets.json に取り込む。

  python scripts/jackets_csv.py export            # -> jackets_todo.csv（全ブランドの未設定曲）
  python scripts/jackets_csv.py import [CSV]      # jacket_url 列が入っている行を jackets.json に反映

CSV の列: brand, song_id, title, fujiwarahaji_url, jacket_url
- jacket_url を埋めて import すると、その曲のジャケットとして登録されます。
- jacket_url が空の行は何もしません（既存の登録も消しません）。
- Excel で開けるよう UTF-8 (BOM付き) で書き出します。
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
JF = DATA / "jackets.json"
DEFAULT_CSV = ROOT / "jackets_todo.csv"
FIELDS = ["brand", "song_id", "title", "fujiwarahaji_url", "jacket_url"]


def load_jackets() -> dict:
    return json.loads(JF.read_text(encoding="utf-8")) if JF.exists() else {}


def export(path: Path) -> None:
    jackets = load_jackets()
    brands = [b["id"] for b in json.loads((DATA / "brands.json").read_text(encoding="utf-8"))]
    rows = []
    for b in brands:
        for s in json.loads((DATA / "songs" / f"{b}.json").read_text(encoding="utf-8")):
            if str(s["id"]) not in jackets:
                rows.append({"brand": b, "song_id": s["id"], "title": s["title"],
                             "fujiwarahaji_url": s["url"], "jacket_url": ""})
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path}")


def import_(path: Path) -> None:
    jackets = load_jackets()
    added, skipped = 0, []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            sid = (row.get("song_id") or "").strip()
            url = (row.get("jacket_url") or "").strip()
            if not sid or not url:
                continue
            if not url.lower().startswith(("http://", "https://")):
                skipped.append(f"{sid} {row.get('title', '')}: {url}")
                continue
            jackets[sid] = url
            added += 1
    JF.write_text(json.dumps(jackets, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"imported {added} jackets -> {JF}")
    for s in skipped:
        print(f"  skipped (not a URL): {s}")


def main() -> None:
    # Windows のコンソールで ♡ などが表示できずに落ちないようにする
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass
    if len(sys.argv) < 2 or sys.argv[1] not in ("export", "import"):
        print(__doc__)
        sys.exit(1)
    path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_CSV
    export(path) if sys.argv[1] == "export" else import_(path)


if __name__ == "__main__":
    main()
