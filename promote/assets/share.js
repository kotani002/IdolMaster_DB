// 共有URL：シートを ID の並びにして URL の「#」以降に入れる（サーバーには保存しない。# 以降はサーバーに送られない）
//   https://…/view#b<base64url>
//     先頭の1文字は形式（"b"）。プレゼン内容（文章）は入れない（長くなるため。文章は出力画像で伝える）
//
// 中身はビット単位で詰める。曲・アイドル・お題は ID（番号）で入れ、共有ページがデータから名前・色を引く：
//   ブランド4bit / 名前（有無1bit＋文字列）/ 曲数6bit / 曲ごとに：
//     お題2bit（0なし 1番号6bit 2自由入力）/ 曲2bit（0なし 1曲ID15bit 2文字の曲ID 3自由入力の曲名）/
//     曲のブランドが違うか1bit（＋4bit）/ ジャケット設定の有無1bit（＋公式ジャケット番号5bit・表示位置2bit）/
//     アイドル人数6bit / 1人ごとに 種類2bit：
//       0 アイドル（ブランド4bit＋ID。数字なら1bit＋14bit、文字のIDなら1bit＋文字列）
//       1 「○○全員」（ブランド4bit）
//       2 ユニット名（ブランド4bit＋文字列。色はアイドル一覧のユニット色）
//       3 自由入力・Day1全員など（文字列＋ブランド4bit（15＝なし）＋色の有無1bit（＋24bit））
//   文字列：長さ7bit＋ASCIIか1bit＋1文字7bit（ASCII）または16bit（それ以外）
//
// ※ 番号は変えないこと：BRAND_CODES の並び、data/themes.json の並び（末尾に足すのはよい。並べ替え・削除はしない）、
//    アイドル・曲の ID（ふじわらはじめの ID。手で足したアイドルの文字の ID も変えない）

export const SHARE_PAGE = "view";
const KIND = "b";
// ブランドの番号（追加は末尾に。並べ替え・削除はしない）
export const BRAND_CODES = ["as", "cg", "ml", "sidem", "sc", "gm", "876", "961"];
const NO_BRAND = 15;

// 上限（読むときもこの数で切る。細工した URL で大量のデータを作らせないため）
// 曲は8曲・歌って欲しいアイドル（タグ）は1曲10人まで（エディタの MAX_SONGS・MAX_TAGS と同じ）
// code：URL の長さの上限。全部を自由入力・最大の長さで埋めたシート（約12,100文字）が入る長さにしている
export const LIMITS = { code: 13000, items: 8, members: 10, name: 30, theme: 40, title: 100, member: 40, id: 24 };

// ---------------------------------------------------------------- ビット列
class BitWriter {
  constructor() { this.bytes = []; this.cur = 0; this.n = 0; }
  write(v, bits) {
    for (let i = bits - 1; i >= 0; i--) {
      this.cur = (this.cur << 1) | ((v >>> i) & 1);
      if (++this.n === 8) { this.bytes.push(this.cur); this.cur = 0; this.n = 0; }
    }
  }
  str(s, max) {
    s = String(s || "").slice(0, Math.min(max, 127));
    const ascii = /^[\x00-\x7f]*$/.test(s);
    this.write(s.length, 7);
    this.write(ascii ? 0 : 1, 1);
    for (let i = 0; i < s.length; i++) this.write(s.charCodeAt(i), ascii ? 7 : 16);
  }
  finish() { if (this.n) this.bytes.push(this.cur << (8 - this.n)); return Uint8Array.from(this.bytes); }
}
class BitReader {
  constructor(bytes) { this.bytes = bytes; this.pos = 0; this.total = bytes.length * 8; }
  read(bits) {
    if (this.pos + bits > this.total) throw new Error("truncated");
    let v = 0;
    for (let i = 0; i < bits; i++, this.pos++) v = v * 2 + ((this.bytes[this.pos >> 3] >> (7 - (this.pos & 7))) & 1);
    return v;
  }
  str(max) {
    const len = this.read(7), wide = this.read(1);
    if (len > max) throw new Error("too long");
    let s = "";
    for (let i = 0; i < len; i++) s += String.fromCharCode(this.read(wide ? 16 : 7));
    return s;
  }
}

const brandCode = (id) => { const k = BRAND_CODES.indexOf(id); return k >= 0 ? k : NO_BRAND; };
const brandOf = (k) => BRAND_CODES[k] || "";

// ---------------------------------------------------------------- エディタの state → ビット列
// look(it, m)：歌って欲しいアイドル1人を、共有用の形 { kind, brand, id?, name?, color? } にする（エディタがデータを見て決める）
// themes：お題の一覧（data/themes.json）。altIndex(it)：公式ジャケットの番号（既定の盤なら -1）
export function packState(state, { themes = [], look, altIndex = () => -1 }) {
  const w = new BitWriter();
  w.write(brandCode(state.from), 4);
  const name = state.name.trim();
  w.write(name ? 1 : 0, 1);
  if (name) w.str(name, LIMITS.name);
  const items = state.items.filter((it) => it.title.trim() || it.pitch.trim() || it.members.length).slice(0, LIMITS.items);
  w.write(items.length, 6);
  for (const it of items) {
    // お題
    const theme = it.theme.trim(), ti = themes.indexOf(theme);
    if (!theme) w.write(0, 2);
    else if (ti >= 0 && ti < 64) { w.write(1, 2); w.write(ti, 6); }
    else { w.write(2, 2); w.str(theme, LIMITS.theme); }
    // 曲
    const sid = it.songId;
    if (Number.isInteger(sid) && sid >= 0 && sid < 32768) { w.write(1, 2); w.write(sid, 15); }
    else if (sid != null && String(sid)) { w.write(2, 2); w.str(String(sid), LIMITS.id); }
    else if (it.title.trim()) { w.write(3, 2); w.str(it.title.trim(), LIMITS.title); }
    else w.write(0, 2);
    // 曲のブランド
    const sb = it.brand || state.from;
    w.write(sb !== state.from ? 1 : 0, 1);
    if (sb !== state.from) w.write(brandCode(sb), 4);
    // ジャケットの設定（公式ジャケットの盤・表示位置）
    const alt = it.jacketAlt ? altIndex(it) : -1;
    const pos = ["auto", "left", "center", "right"].indexOf(it.jkPos || "auto");
    const extra = (alt >= 0 && alt < 31) || pos > 0;
    w.write(extra ? 1 : 0, 1);
    if (extra) { w.write(alt >= 0 && alt < 31 ? alt : 31, 5); w.write(Math.max(0, pos), 2); }
    // 歌って欲しいアイドル
    const mems = it.members.slice(0, LIMITS.members).map((m) => look(it, m));
    w.write(mems.length, 6);
    for (const m of mems) {
      if (m.kind === "idol") {
        w.write(0, 2); w.write(brandCode(m.brand), 4);
        if (Number.isInteger(m.id) && m.id >= 0 && m.id < 16384) { w.write(1, 1); w.write(m.id, 14); }
        else { w.write(0, 1); w.str(String(m.id), LIMITS.id); }
      } else if (m.kind === "all") {
        w.write(1, 2); w.write(brandCode(m.brand), 4);
      } else if (m.kind === "unit") {
        w.write(2, 2); w.write(brandCode(m.brand), 4); w.str(m.name, LIMITS.member);
      } else {
        w.write(3, 2); w.str(m.name, LIMITS.member); w.write(brandCode(m.brand), 4);
        const c = /^#[0-9a-f]{6}$/i.test(m.color || "") ? parseInt(m.color.slice(1), 16) : -1;
        w.write(c >= 0 ? 1 : 0, 1);
        if (c >= 0) w.write(c, 24);
      }
    }
  }
  return w.finish();
}

// ---------------------------------------------------------------- ビット列 → 共有ページ用
// 返す形：{ from, name, items: [{ theme: {index}|{text}|null, songId, title, brand, alt, pos,
//          members: [{ kind:"idol", brand, id } | { kind:"all", brand } | { kind:"unit", brand, name } | { kind:"custom", name, brand, color }] }] }
export function unpackSheet(bytes) {
  const r = new BitReader(bytes);
  const from = brandOf(r.read(4));
  if (!from) throw new Error("bad brand");
  const name = r.read(1) ? r.str(LIMITS.name) : "";
  const n = r.read(6);
  if (n > LIMITS.items) throw new Error("too many items");
  const items = [];
  for (let k = 0; k < n; k++) {
    const it = { theme: null, songId: null, title: "", brand: from, alt: -1, pos: "auto", members: [] };
    const tk = r.read(2);
    if (tk === 1) it.theme = { index: r.read(6) };
    else if (tk === 2) it.theme = { text: r.str(LIMITS.theme) };
    else if (tk === 3) throw new Error("bad theme");
    const sk = r.read(2);
    if (sk === 1) it.songId = r.read(15);
    else if (sk === 2) it.songId = r.str(LIMITS.id);
    else if (sk === 3) it.title = r.str(LIMITS.title);
    if (r.read(1)) it.brand = brandOf(r.read(4)) || from;
    if (r.read(1)) {
      const a = r.read(5);
      it.alt = a === 31 ? -1 : a;
      it.pos = ["auto", "left", "center", "right"][r.read(2)];
    }
    const mn = r.read(6);
    if (mn > LIMITS.members) throw new Error("too many members");
    for (let j = 0; j < mn; j++) {
      const kind = r.read(2);
      if (kind === 0) {
        const brand = brandOf(r.read(4));
        const id = r.read(1) ? r.read(14) : r.str(LIMITS.id);
        it.members.push({ kind: "idol", brand, id });
      } else if (kind === 1) {
        it.members.push({ kind: "all", brand: brandOf(r.read(4)) });
      } else if (kind === 2) {
        const brand = brandOf(r.read(4));
        it.members.push({ kind: "unit", brand, name: r.str(LIMITS.member) });
      } else {
        const name = r.str(LIMITS.member), brand = brandOf(r.read(4));
        const color = r.read(1) ? "#" + r.read(24).toString(16).padStart(6, "0") : "";
        it.members.push({ kind: "custom", name, brand, color });
      }
    }
    items.push(it);
  }
  return { from, name, items };
}

// ---------------------------------------------------------------- base64url
function toB64(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i += 0x8000) s += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function fromB64(s) {
  s = s.replace(/-/g, "+").replace(/_/g, "/");
  const bin = atob(s + "===".slice((s.length + 3) % 4));
  return Uint8Array.from(bin, (c) => c.charCodeAt(0));
}

export const encodeSheet = (bytes) => KIND + toB64(bytes);

export function decodeSheet(code) {
  if (typeof code !== "string" || code.length > LIMITS.code) throw new Error("too long");
  if (code[0] !== KIND) throw new Error("unknown format");
  return unpackSheet(fromB64(code.slice(1)));
}

// 共有ページのURL。公開サイト（Cloudflare Pages）は「/view」で view.html を返す（.html 付きは転送になるので付けない）。
// 手元の確認用サーバー（python -m http.server）は .html を付けないと開けないので付ける
export function shareUrl(bytes, base = location.href) {
  const local = /^(localhost|127\.0\.0\.1|\[::1\])$/.test(new URL(base).hostname);
  const u = new URL(local ? SHARE_PAGE + ".html" : SHARE_PAGE, base);
  u.search = "";
  u.hash = encodeSheet(bytes);
  return u.href;
}

// location.hash から取り出す（無ければ null）
export function codeFromHash(hash = location.hash) {
  const m = /^#([A-Za-z0-9_-]+)$/.exec(hash || "");
  return m ? m[1] : null;
}
