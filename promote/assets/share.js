// 共有URL：シートの中身を URL の「#」以降に入れる（サーバーには保存しない。# 以降はサーバーに送られない）
//   https://…/view.html#d=a<base64url>
//     "a"：JSON を UTF-16 にして deflate-raw で圧縮したもの
//          （日本語の文章は UTF-8 だと1文字3バイト、UTF-16 だと2バイトなので、圧縮後もこちらが短い）
//
// JSON は短いキーで書き、閲覧ページでデータから分かるものは入れない：
//   { f:ブランド, n:名前, i:[{ t:お題, s:曲ID, k:曲名（曲IDが無い自由入力の曲だけ）, b:曲のブランド（f と違うときだけ）,
//        p:プレゼン, m:[ "アイドル名" | [名前, ブランド, 色] ], a:公式ジャケットの番号, o:表示位置 }] }
//   歌って欲しいアイドルは、曲のブランドのアイドルで色も一覧どおりなら名前だけ。
//   ブランドが違う・色が一覧と違う（「○○全員」「Day1全員」・ユニット名・自由入力）ときだけ配列にする（色は一覧どおりなら省く）。
//   アイドル・お題は番号にしない（データを更新して並びが変わると、共有済みのURLが別の人・お題を指してしまうため）

export const SHARE_PAGE = "view.html";
const KIND = "a";

// ---- エディタの state → 共有用の短い形
// altIndex(it)：「公式ジャケットから選ぶ」で選んだ盤の番号（既定の盤なら -1）
// defaultColor(member, brandId)：そのアイドルを名前とブランドだけで表示したときの色（一覧の色、無ければブランド色）
export function packState(state, { altIndex = () => -1, defaultColor = () => "" } = {}) {
  const items = state.items
    .filter((it) => it.title.trim() || it.pitch.trim() || it.members.length)
    .map((it) => {
      const o = {};
      const songBrand = it.brand || state.from;
      if (it.theme.trim()) o.t = it.theme.trim();
      if (it.songId != null) o.s = it.songId;
      else if (it.title.trim()) o.k = it.title.trim();
      if (songBrand !== state.from) o.b = songBrand;
      if (it.pitch.trim()) o.p = it.pitch.trim();
      if (it.members.length) {
        o.m = it.members.map((m) => {
          const b = m.brand || "";
          const color = m.color && m.color.toLowerCase() !== (defaultColor(m, b) || "").toLowerCase() ? m.color : "";
          if (b === songBrand && !color) return m.name;
          return color ? [m.name, b, color] : [m.name, b];
        });
      }
      const a = it.jacketAlt ? altIndex(it) : -1;
      if (a >= 0) o.a = a;
      if (it.jkPos && it.jkPos !== "auto") o.o = it.jkPos;
      return o;
    });
  const d = { f: state.from, i: items };
  if (state.name.trim()) d.n = state.name.trim();
  return d;
}

// ---- 共有用の短い形 → 表示用（曲名・アイドルの色は閲覧ページがデータから補う）
export function unpackSheet(d) {
  if (!d || typeof d !== "object" || !Array.isArray(d.i)) throw new Error("bad sheet");
  const str = (v, max) => (typeof v === "string" ? v.slice(0, max) : "");
  const color = (v) => (/^#[0-9a-f]{3,8}$/i.test(v || "") ? v : "");
  const from = str(d.f, 16);
  return {
    name: str(d.n, 30),
    from,
    items: d.i.slice(0, 50).map((o) => {
      const brand = str(o.b, 16) || from;
      return {
        theme: str(o.t, 40),
        songId: typeof o.s === "number" || typeof o.s === "string" ? o.s : null,
        title: str(o.k, 100),
        brand,
        pitch: str(o.p, 400),
        members: (Array.isArray(o.m) ? o.m : []).slice(0, 60).map((m) => (typeof m === "string"
          ? { name: str(m, 40), brand, color: "" }
          : { name: str(m?.[0], 40), brand: str(m?.[1], 16), color: color(m?.[2]) })).filter((m) => m.name),
        alt: Number.isInteger(o.a) ? o.a : -1,
        pos: ["left", "center", "right"].includes(o.o) ? o.o : "auto",
      };
    }),
  };
}

// ---- 文字列 ⇔ UTF-16（ビッグエンディアン）のバイト列
function toUtf16(str) {
  const a = new Uint8Array(str.length * 2);
  for (let i = 0; i < str.length; i++) { const c = str.charCodeAt(i); a[2 * i] = c >> 8; a[2 * i + 1] = c & 255; }
  return a;
}
function fromUtf16(bytes) {
  let s = "";
  for (let i = 0; i + 1 < bytes.length; i += 2 * 0x4000) {
    const codes = [];
    for (let j = i; j + 1 < bytes.length && j < i + 2 * 0x4000; j += 2) codes.push((bytes[j] << 8) | bytes[j + 1]);
    s += String.fromCharCode(...codes);
  }
  return s;
}

// ---- base64url
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
async function pipe(bytes, stream) {
  const out = new Response(new Blob([bytes]).stream().pipeThrough(stream));
  return new Uint8Array(await out.arrayBuffer());
}

export const canShare = () => typeof CompressionStream === "function";
export const canOpen = () => typeof DecompressionStream === "function";

export async function encodeSheet(packed) {
  return KIND + toB64(await pipe(toUtf16(JSON.stringify(packed)), new CompressionStream("deflate-raw")));
}

export async function decodeSheet(code) {
  if (code[0] !== KIND) throw new Error("unknown format");
  const raw = await pipe(fromB64(code.slice(1)), new DecompressionStream("deflate-raw"));
  return unpackSheet(JSON.parse(fromUtf16(raw)));
}

// 共有ページのURL（エディタと同じ場所にある view.html）
export async function shareUrl(packed, base = location.href) {
  const u = new URL(SHARE_PAGE, base);
  u.search = "";
  u.hash = "d=" + (await encodeSheet(packed));
  return u.href;
}

// location.hash から取り出す（無ければ null）
export function codeFromHash(hash = location.hash) {
  const m = /^#?d=([A-Za-z0-9_-]+)/.exec(hash || "");
  return m ? m[1] : null;
}
