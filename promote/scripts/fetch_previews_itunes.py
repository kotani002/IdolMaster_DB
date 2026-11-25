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
from fetch_jackets_itunes import BRAND_WORDS, IMAS_WORDS, SKIP_SONGS, get_json, has_any, search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
OUT = DATA / "previews.json"
REPORT = Path(__file__).resolve().parent / ".cache" / "previews_report.txt"

# 「曲名 (Ver.Cute)」「(Ver.MASTER EVERMORE)」「Migratory Echoes (ユニット名Ver.)」などサイト側で分けた版の付記
# （以前は「…Ver.)」の形しか拾えず、(Ver.Cute) の曲がどの版も同じ音源（リミックスなど）になっていた）
SITE_VERSION = re.compile(r"\s*[（(][^（()）]*ver\.[^（()）]*[)）]\s*$", re.I)
# リミックス・ソロリミックスは「曲そのもの」と違うので使わない（曲名にそう書いてある曲は除く）
REMIX = re.compile(r"remix|リミックス|\bmix\b|ソロ・?(バージョン|ver)|solo ver", re.I)
# 曲名の後ろの「(二階堂千鶴 Ver.)」「[MILLIONSTARS Ver.]」のような版の付記（中身を取り出す）
VER_TAG = re.compile(r"[（(\[［]([^（()）\[\]［］]*?)\s*ver\.?[)）\]］]", re.I)
# 曲名の後ろの付記（括弧書き）。候補が複数あるときは、付記の無い元の音源を先に使う
EXTRA_TAG = re.compile(r"[（(\[［【][^（()）\[\]［］【】]*[)）\]］】]")
# Apple の曲名の「(シンデレラガールズ バージョン)」のような付記（照合の前に外す。外さないと VOY@GER などが別の曲扱いになった）
KANA_VERSION = re.compile(r"\s*[（(][^（()）]*バージョン[)）]")

# ブランドをまたぐ共通の曲（スタマス・カバー曲など）がまとまっているアルバム（ユーザー情報）。
# 曲名が検索で見つからなかった曲は、これらのアルバムの収録曲から探す（アーティスト名にアイドル名が並んでいる）
STARLIT_ALBUMS = [
    1588675530,  # THE IDOLM@STER STARLIT SEASON 00 GR@TITUDE - Single
    1588673720,  # 00 GR@TITUDE【日本コロムビア盤】
    1717753692,  # 00 GR@TITUDE【ランティス盤】
    1718493703,  # THE IDOLM@STER STARLIT SEASON 01
    1602208428,  # 02
    1718496905,  # 03
    1618722648,  # 04
]
# ブランドごとの、曲名検索では見つけにくい曲がまとまったアルバム（ユーザー情報）。
#   シャニマスの季節曲など（Let's get a chance・SWEET♡STEP…）は曲名に「-25 colors-」のような付記が付いている
BRAND_ALBUMS = {
    "sc": [
        1734553272,  # THE IDOLM@STER SHINY COLORS WING COLLECTION -A side-（季節曲など。ユーザー情報：A・B 両方）
        1734553065,  # THE IDOLM@STER SHINY COLORS WING COLLECTION -B side-（-25 colors-）
        1836353222,  # THE IDOLM@STER SHINY COLORS -28 colors- COLLECTION
    ],
}
# 照合の前に外す、アルバム独自の曲名の付記（「-25 colors-」など）
ALBUM_SUFFIX = re.compile(r"\s*-\s*\d+\s*colors\s*-\s*$", re.I)
_album_cache: dict[int, list[dict]] = {}


def album_tracks(ids: list[int]) -> list[dict]:
    out = []
    for cid in ids:
        if cid not in _album_cache:
            res = get_json(f"https://itunes.apple.com/lookup?id={cid}&country=JP&entity=song&limit=200").get("results", [])
            _album_cache[cid] = [t for t in res if t.get("wrapperType") == "track" and t.get("previewUrl")]
        out += _album_cache[cid]
    return out


def starlit_tracks() -> list[dict]:
    return album_tracks(STARLIT_ALBUMS)


# 手で決めた試聴（照合より優先する）。キーは previews.json と同じ（越境曲は「ブランド:曲ID」）
#   値は Apple Music の trackId（曲の URL の「?i=」の後ろの数字）
PREVIEW_OVERRIDES = {
    "cg:4411": 1579016507,  # VOY@GER（シンデレラガールズ バージョン）。ユーザー指定
    "9760": 1779614260,     # Clean.Clean up（コメティック / ECHOES 08）。ユーザー指定
    "11327": 1818073120,    # GET OVER（ストレイライト / 円環 -Halo around- 02）。ユーザー指定
    "11392": 1830422653,    # Swing it!（ノクチル / 円環 -Halo around- 04）。ユーザー指定
}


UNIT_KANA = json.loads((DATA / "units.json").read_text(encoding="utf-8")) if (DATA / "units.json").exists() else {}


def find(song: dict, brand: str, multi: bool = False) -> tuple[dict, str] | None:
    """
    まず版・ブランドをきちんと確かめて探し、見つからなければ順にゆるめる（ユーザー判断）
      1. 版を分けた曲（Ver.Cute など）でその版の音源が無い → 元の曲（版の指定なし）の音源を使う
      2. 越境曲でそのブランドの盤が無い → どのブランド名も付いていない共通の盤（THE IDOLM@STER …）を使う
    """
    hit = find_strict(song, brand, multi_brand=multi)
    if not hit and SITE_VERSION.search(song["title"]):
        hit = find_strict(song, brand, ignore_ver=True, multi_brand=multi)
        if hit: hit = (hit[0], hit[1] + "・元の版")
    if not hit:
        # よくある曲名（Swing it!・GET OVER・Sparkle など）は、検索結果（1回50件）がほかのアーティストの曲で埋まって
        # 見つからないことがあるので、「曲名＋ブランド名」「曲名＋ユニット名（カタカナ）」で探し直す
        hit = find_strict(song, brand, terms=extra_terms(song, brand), multi_brand=multi)
        if hit: hit = (hit[0], hit[1] + "・追加検索")
    if not hit:
        hit = find_starlit(song)
    if not hit and BRAND_ALBUMS.get(brand):
        hit = find_brand_album(song, brand)
    if not hit and multi:
        hit = find_strict(song, brand, common=True)
        if hit: hit = (hit[0], hit[1] + "・共通盤")
    return hit


def find_starlit(song: dict) -> tuple[dict, str] | None:
    """STARLIT SEASON のアルバムの収録曲から探す。曲名が同じで、アーティスト名に歌唱者の名前が入っているものだけ使う"""
    key = song_key(SITE_VERSION.sub("", song["title"]))
    singers = [norm(re.sub(r"[（(]初代[)）]", "", s)) for s in song.get("singers") or []]
    singers = [s for s in singers if len(s) >= 2]
    cands = []
    for t in starlit_tracks():
        k, rank = classify(KANA_VERSION.sub("", t.get("trackName", "")))
        if k != key or rank != 0 or (REMIX.search(t["trackName"]) and not REMIX.search(song["title"])):
            continue
        if singers and any(s in norm(t.get("artistName", "")) for s in singers):
            cands.append((t.get("releaseDate", "9999"), t))
    if not cands:
        return None
    return min(cands, key=lambda c: c[0])[1], "STARLIT SEASON"


def find_brand_album(song: dict, brand: str) -> tuple[dict, str] | None:
    """BRAND_ALBUMS のアルバムの収録曲から探す。曲名（「-25 colors-」などの付記を外したもの）が同じものを使う
    （ブランドのアルバムなので、アーティスト名がブランド名（シャイニーカラーズ）でもよい）"""
    key = song_key(SITE_VERSION.sub("", song["title"]))
    cands = []
    for t in album_tracks(BRAND_ALBUMS[brand]):
        name = ALBUM_SUFFIX.sub("", KANA_VERSION.sub("", t.get("trackName", "")))
        k, rank = classify(name)
        if k != key or rank != 0 or (REMIX.search(t["trackName"]) and not REMIX.search(song["title"])):
            continue
        cands.append((t.get("releaseDate", "9999"), t))
    if not cands:
        return None
    return min(cands, key=lambda c: c[0])[1], "ブランドのアルバム"


def extra_terms(song: dict, brand: str) -> list[str]:
    title = SITE_VERSION.sub("", song["title"])
    to_kata = lambda s: "".join(chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s)
    terms = [f"{title} {w}" for w in BRAND_WORDS.get(brand, [])[:2]]
    for u in (song.get("units") or [])[:2]:
        if UNIT_KANA.get(u):
            terms.append(f"{title} {to_kata(UNIT_KANA[u])}")
    return terms


def find_strict(song: dict, brand: str, ignore_ver: bool = False, common: bool = False,
                terms: list[str] | None = None, multi_brand: bool = False) -> tuple[dict, str] | None:
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
    need_ver = norm(re.sub(r"ver\.?", "", vm.group(0), flags=re.I)) if vm and not ignore_ver else ""
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
    for term in terms or (f"{title} アイドルマスター", title):
        for r in search(term):
            tid = r.get("trackId")
            if tid in seen or not r.get("previewUrl"):
                continue
            seen.add(tid)
            track = r.get("trackName", "")
            k, rank = classify(KANA_VERSION.sub("", track))
            if k != key or rank != 0:
                continue
            disc = f"{track} {r.get('collectionName', '')}"
            # 版の名前は曲名かアルバム名に入っていればよい（Cute jewelries! 001・MASTER EVERMORE などアルバム名で分かる版がある）
            if need_ver and need_ver not in norm(disc):
                continue
            if REMIX.search(track) and not REMIX.search(song["title"]):
                continue
            # 何人かで歌う曲の「(二階堂千鶴 Ver.)」のような1人の版（ソロ）は使わない
            tag = VER_TAG.search(track)
            if tag and len(singers) > 1 and norm(tag.group(1)) in singers and not VER_TAG.search(song["title"]):
                continue
            # 越境曲の「シャイニーカラーズVer.」のような、ほかのブランドの盤は使わない
            if has_any(disc, other_words) and not has_any(disc, own_words):
                continue
            artist = norm(r.get("artistName", ""))
            text = f"{r.get('collectionName', '')} {r.get('artistName', '')}"
            prio = None
            if common:
                # 共通盤：「THE IDOLM@STER」などは入っていて、どのブランドの名前も入っていないもの
                all_words = [w for ws in BRAND_WORDS.values() for w in ws]
                if has_any(f"{disc} {r.get('artistName', '')}", IMAS_WORDS) and not has_any(f"{disc} {r.get('artistName', '')}", all_words):
                    prio, why = 2, "共通"
            elif any(n in artist for n in names):
                prio, why = 0, "歌唱者"
            elif has_any(text, own_words + (IMAS_WORDS if brand == "as" else [])) and not has_any(text, other_words):
                # 765AS は作品名が「THE IDOLM@STER」だけのことがあるので、ほかのブランド名が無ければ使う
                prio, why = 1, "作品名"
            if prio is not None:
                # 曲名に無い付記（M@STER VERSION・GAME VERSION・Ver. など）が付いた音源は、付記の無いものより後にする
                # （「M@STER VERSION」は 765AS・シンデレラの CD のもともとの音源に付いている名前なので付記扱いしない）
                # 越境曲は「(シャイニーカラーズVer.)」のような自分のブランドの盤を最優先にする（その付記は減点しない）。
                # （以前は付記の無い音源を優先したため、シャニマスの GR@TITUDE が玲音たちの版になってしまった）
                own = has_any(f"{disc} {r.get('artistName', '')}", own_words)
                extra = any(norm(t) not in norm(song["title"]) and not re.search(r"m@ster vers?[it]on", t, re.I)
                            and not has_any(t, own_words) for t in EXTRA_TAG.findall(track))
                cands.append((prio, 0 if own or not multi_brand else 1, 1 if extra else 0, r.get("releaseDate", "9999"), r, why))
        # 「曲名 アイドルマスター」で見つかれば、曲名だけの検索はしない（同名の別の曲が多いため）
        if cands:
            break
    if not cands:
        return None
    _, _, _, _, r, why = min(cands, key=lambda c: (c[0], c[1], c[2], c[3]))
    return r, why


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    redo = "--redo" in sys.argv
    brands = args or [p.stem for p in sorted((DATA / "songs").glob("*.json"))]
    previews = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    previews.pop("_comment", None)
    report, found, total = [], 0, 0
    # 複数のブランドにある曲（越境曲：VOY@GER・GR@TITUDE など）はブランドごとに別の盤なので、
    # 「ブランド:曲ID」で書く（共有ページはこちらを先に見る。jackets.json と同じ考え方）
    seen_in = {}
    for p in (DATA / "songs").glob("*.json"):
        for s in json.loads(p.read_text(encoding="utf-8")):
            seen_in.setdefault(str(s["id"]), set()).add(p.stem)
    for b in brands:
        songs = json.loads((DATA / "songs" / f"{b}.json").read_text(encoding="utf-8"))
        print(f"[{b}] {len(songs)} songs", flush=True)
        for i, s in enumerate(songs, 1):
            plain = str(s["id"])
            multi = len(seen_in.get(plain, ())) > 1
            sid = f"{b}:{plain}" if multi else plain
            if s["title"] in SKIP_SONGS.get(b, set()):
                continue
            total += 1
            if multi:
                previews.pop(plain, None)  # 以前の形（ブランドを分けない書き方）は消す
            if sid in PREVIEW_OVERRIDES:
                previews[sid] = PREVIEW_OVERRIDES[sid]
                found += 1
                report.append(f"OK\t{b}\t{s['title']}\t→ 手で指定（PREVIEW_OVERRIDES）\t{PREVIEW_OVERRIDES[sid]}")
                continue
            if sid in previews and not redo:
                found += 1
                continue
            hit = find(s, b, multi)
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
    body = {"_comment": "楽曲ID(ふじわらはじめの song_id。複数ブランドにある曲は「ブランド:曲ID」) -> Apple Music の trackId。scripts/fetch_previews_itunes.py で作成"}
    body.update(sorted(previews.items(), key=lambda kv: kv[0]))
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=0) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
