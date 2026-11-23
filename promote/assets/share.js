// 共有URL：シートの中身を URL の「#」以降に入れる（サーバーには保存しない。# 以降はサーバーに送られない）
//   https://…/view.html#d=<形式1文字><base64url>
//     形式 "z"：JSON を deflate-raw で圧縮（CompressionStream が使えるブラウザ）
//     形式 "j"：JSON そのまま（圧縮できないブラウザ用）
// JSON は短いキーで書く：{ v:1, n:名前, f:ブランド, i:[{ t:お題, s:曲ID, k:曲名, b:曲のブランド, p:プレゼン, m:[[名前,ブランド,色]], a:公式ジャケットの番号, o:表示位置 }] }
// 既定値（空文字・おすすめブランドと同じ・自動）は書かない

export const SHARE_PAGE = "view.html";
const VERSION = 1;

// ---- エディタの state → 共有用の短い形
// altIndex(it) は「公式ジャケットから選ぶ」で選んだ盤の番号（既定の盤なら -1）
export function packState(state, altIndex = () => -1) {
  const items = state.items
    .filter((it) => it.title.trim() || it.pitch.trim() || it.members.length)
    .map((it) => {
      const o = {};
      if (it.theme.trim()) o.t = it.theme.trim();
      if (it.songId != null) o.s = it.songId;
      if (it.title.trim()) o.k = it.title.trim();
      if (it.brand && it.brand !== state.from) o.b = it.brand;
      if (it.pitch.trim()) o.p = it.pitch.trim();
      if (it.members.length) o.m = it.members.map((m) => [m.name, m.brand || "", m.color || ""]);
      const a = it.jacketAlt ? altIndex(it) : -1;
      if (a >= 0) o.a = a;
      if (it.jkPos && it.jkPos !== "auto") o.o = it.jkPos;
      return o;
    });
  const d = { v: VERSION, f: state.from, i: items };
  if (state.name.trim()) d.n = state.name.trim();
  return d;
}

// ---- 共有用の短い形 → 表示用
export function unpackSheet(d) {
  if (!d || typeof d !== "object" || !Array.isArray(d.i)) throw new Error("bad sheet");
  const str = (v, max) => (typeof v === "string" ? v.slice(0, max) : "");
  const from = str(d.f, 16);
  return {
    name: str(d.n, 30),
    from,
    items: d.i.slice(0, 50).map((o) => ({
      theme: str(o.t, 40),
      songId: typeof o.s === "number" || typeof o.s === "string" ? o.s : null,
      title: str(o.k, 100),
      brand: str(o.b, 16) || from,
      pitch: str(o.p, 400),
      members: (Array.isArray(o.m) ? o.m : []).slice(0, 60).map((m) => ({
        name: str(m?.[0], 40), brand: str(m?.[1], 16), color: /^#[0-9a-f]{3,8}$/i.test(m?.[2] || "") ? m[2] : "",
      })).filter((m) => m.name),
      alt: Number.isInteger(o.a) ? o.a : -1,
      pos: ["left", "center", "right"].includes(o.o) ? o.o : "auto",
    })),
  };
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

export async function encodeSheet(packed) {
  const raw = new TextEncoder().encode(JSON.stringify(packed));
  if (typeof CompressionStream === "function") {
    try { return "z" + toB64(await pipe(raw, new CompressionStream("deflate-raw"))); } catch {}
  }
  return "j" + toB64(raw);
}

export async function decodeSheet(code) {
  const kind = code[0], body = fromB64(code.slice(1));
  let raw;
  if (kind === "z") {
    if (typeof DecompressionStream !== "function") throw new Error("old browser");
    raw = await pipe(body, new DecompressionStream("deflate-raw"));
  } else if (kind === "j") raw = body;
  else throw new Error("unknown format");
  return unpackSheet(JSON.parse(new TextDecoder().decode(raw)));
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
