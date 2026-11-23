// 共有ページ（view.html）：URL の # に入ったシートを表示し、曲を Apple Music の試聴（約30秒）で聴けるようにする
// 試聴の曲は data/previews.json（楽曲ID → Apple Music の trackId。scripts/fetch_previews_itunes.py で作成）。
// 試聴URLは変わることがあるので保存せず、開いたときに iTunes の lookup API でまとめて1回だけ問い合わせる。

import { decodeSheet, codeFromHash } from "./share.js?v=20261123a";

const DEFAULT_NAME = "名無しP";
const NOW_PRINTING = "assets/now_printing.png?v=3";
const ITUNES_LOOKUP = "https://itunes.apple.com/lookup";
const PROXY = (u) => `https://wsrv.nl/?url=${encodeURIComponent(u)}&w=600&h=600&fit=inside&output=jpg&q=88`;

const $ = (sel, root = document) => root.querySelector(sel);
const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") {
      for (const [p, val] of Object.entries(v)) p.startsWith("--") ? el.style.setProperty(p, val) : (el.style[p] = val);
    } else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null && c !== false) el.append(c);
  return el;
};

async function getJSON(path, fallback) {
  try {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${path}: ${r.status}`);
    return await r.json();
  } catch (e) {
    if (fallback !== undefined) return fallback;
    throw e;
  }
}

function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), ms);
}

// ---------------------------------------------------------------- 色（app.js と同じ計算）
function hexToRgb(hex) {
  let x = (hex || "").replace("#", "");
  if (x.length === 3) x = x.split("").map((c) => c + c).join("");
  const n = parseInt(x, 16);
  if (Number.isNaN(n) || x.length !== 6) return null;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function luminance(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return 0;
  const [r, g, b] = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
const inkFor = (hex) => (!hexToRgb(hex) ? "#fff" : luminance(hex) > 0.45 ? "#2a2730" : "#ffffff");
const isLight = (hex) => luminance(hex) > 0.75;

// ---------------------------------------------------------------- data
const DB = { brands: [], jackets: {}, jacketAlts: {}, previews: {}, songs: {} };
const brand = (id) => DB.brands.find((b) => b.id === id) || { id, name: id, short: id, color: "#8a8593", ink: "#fff" };
const jacketOf = (songId, b) => DB.jackets[`${b}:${songId}`] || DB.jackets[String(songId)] || "";
const altsOf = (songId, b) => (songId == null ? [] : DB.jacketAlts[`${b}:${songId}`] || DB.jacketAlts[String(songId)] || []);
const songOf = (it) => (it.songId == null ? null : (DB.songs[it.brand] || []).find((s) => String(s.id) === String(it.songId)) || null);

// 「歌：…」（app.js の singerNote と同じ考え方。全体曲はブランド名＋全体、ユニットがあればユニット名）
const NOT_UNIT = new Set(["越境曲", "全体曲", "スターリットシーズン", "スタマス", "ディアリースターズ"]);
function singerNote(s, brandId) {
  if (!s) return "";
  if ((s.units || []).includes("全体曲")) return `歌：${brand(brandId).name}全体`;
  const units = (s.units || []).filter((u) => !NOT_UNIT.has(u));
  const names = [...new Set((s.singers || []).map((n) => n.replace(/\s*[（(]初代[)）]\s*/g, "")))];
  const list = units.length ? units : names;
  return list.length ? `歌：${list.join("、")}` : "";
}

// ---------------------------------------------------------------- ジャケット（app.js の imgUrl・jacketPos を簡略化したもの）
const HOTLINK_HOSTS = new Set(["shinycolors.lantis.jp"]);
function imgUrl(u) {
  try {
    const x = new URL(u);
    if (HOTLINK_HOSTS.has(x.host) && !x.searchParams.has("nr")) { x.searchParams.set("nr", "2"); return x.href; }
  } catch {}
  return u;
}
function jacketEl(url, pos) {
  const box = h("div", { class: "jacket v-jacket" });
  const img = h("img", { class: "jk-img", alt: "", decoding: "async" });
  img.referrerPolicy = "no-referrer";
  img.onload = () => {
    const r = img.naturalWidth / (img.naturalHeight || 1);
    // 参照元付きで読まれて差し替え画像（200×200）が返ったら、画像変換サービス経由で読み直す
    if (HOTLINK_HOSTS.has(new URL(img.src, location.href).host) && img.naturalWidth === 200 && img.naturalHeight === 200) {
      img.src = PROXY(url); return;
    }
    if (pos !== "auto") img.style.objectPosition = `${pos} center`;
    else if (r < 0.95) img.style.objectFit = "contain";
    else if (r >= 1.6) img.style.objectPosition = /^https?:\/\/columbia\.jp\//.test(url) ? "right center" : "left center";
  };
  img.onerror = () => { img.onerror = null; img.src = NOW_PRINTING; };
  img.src = url ? imgUrl(url) : NOW_PRINTING;
  box.append(img);
  return box;
}

// ---------------------------------------------------------------- 試聴
const audio = new Audio();
audio.preload = "none";
// 試聴の音源（audio-ssl.itunes.apple.com）は CORS 許可あり。Web Audio で音量を変えるため crossOrigin を付ける
audio.crossOrigin = "anonymous";
const player = { cards: [], cur: -1, chain: false };

// ---- 音量のフェード（いきなり大きな音で鳴って驚かせないように）
// iPhone の Safari は audio.volume を変えられないので、Web Audio の GainNode で音量を動かす。
// Web Audio が使えないブラウザは audio.volume を少しずつ変える
const FADE_IN_SEC = 2.0;   // 再生開始：0 からこの秒数で上げる
const FADE_OUT_SEC = 0.35; // 停止・曲の切り替え：この秒数で下げてから止める
const MAX_GAIN = 0.85;     // 試聴は音圧が高い曲が多いので、少し控えめにする
const fader = { ctx: null, gain: null, timer: 0 };function setupFader() {
  if (fader.ctx || fader.ctx === false) return;
  try {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    const ctx = new Ctx();
    const gain = ctx.createGain();
    gain.gain.value = 0;
    ctx.createMediaElementSource(audio).connect(gain).connect(ctx.destination);
    Object.assign(fader, { ctx, gain });
  } catch (e) {
    console.warn("Web Audio unavailable, fallback to audio.volume", e);
    fader.ctx = false;
  }
}
// 今の音量から to まで sec 秒で変える。終わったら resolve
function fadeTo(to, sec) {
  clearInterval(fader.timer);
  if (fader.gain) {
    const g = fader.gain.gain, now = fader.ctx.currentTime;
    g.cancelScheduledValues(now);
    g.setValueAtTime(g.value, now);
    g.linearRampToValueAtTime(to, now + sec);
    return new Promise((r) => setTimeout(r, sec * 1000));
  }
  return new Promise((r) => {
    const from = audio.volume, t0 = performance.now();
    fader.timer = setInterval(() => {
      const k = Math.min(1, (performance.now() - t0) / (sec * 1000));
      audio.volume = from + (to - from) * k;
      if (k >= 1) { clearInterval(fader.timer); r(); }
    }, 30);
  });
}
function muteNow() {
  clearInterval(fader.timer);
  if (fader.gain) {
    const g = fader.gain.gain;
    g.cancelScheduledValues(fader.ctx.currentTime);
    g.setValueAtTime(0, fader.ctx.currentTime);
  } else audio.volume = 0;
}
// フェードアウトしてから止める
let stopping = null;
async function stopWithFade() {
  if (audio.paused) return;
  const token = (stopping = {});
  await fadeTo(0, FADE_OUT_SEC);
  if (stopping === token) audio.pause();
}

// trackId → { preview, url, artist }
async function lookupTracks(ids) {
  const out = new Map();
  if (!ids.length) return out;
  for (let k = 0; k < ids.length; k += 150) {
    const q = new URLSearchParams({ id: ids.slice(k, k + 150).join(","), country: "JP", entity: "song" });
    try {
      const r = await fetch(`${ITUNES_LOOKUP}?${q}`);
      const d = await r.json();
      for (const t of d.results || []) {
        if (t.wrapperType === "track" && t.trackId) {
          out.set(t.trackId, { preview: t.previewUrl || "", url: t.trackViewUrl || "", artist: t.artistName || "" });
        }
      }
    } catch (e) { console.error(e); }
  }
  return out;
}

function setPlaying(i) {
  player.cards.forEach((c, k) => {
    c.el.classList.toggle("playing", k === i && !audio.paused);
    c.btn.setAttribute("aria-label", k === i && !audio.paused ? `「${c.title}」の試聴を止める` : `「${c.title}」を試聴する`);
    if (k !== i) c.bar.style.width = "0%";
  });
  $("#v-playall").textContent = player.chain && !audio.paused ? "■ 試聴を止める" : "▶ 続けて試聴する";
}

async function play(i, chain = false) {
  const c = player.cards[i];
  if (!c?.preview) return;
  // 押した操作の中で用意する（ブラウザは操作の中でしか音を出させないため）
  setupFader();
  if (fader.ctx && fader.ctx.state === "suspended") fader.ctx.resume().catch(() => {});
  // 再生中の曲の ▶ をもう一度押したら止める。
  // 「続けて試聴する」（chain）のときは止めず、下でフェードアウトしてから先頭から流し直す
  // （1曲目の再生中に押すと、1曲目を止めるだけで何も流れなかったため）
  if (!chain && player.cur === i && !audio.paused) { player.chain = false; await stopWithFade(); setPlaying(i); return; }
  stopping = null;
  // 別の曲が鳴っていたら、短くフェードアウトしてから切り替える
  if (!audio.paused) await fadeTo(0, FADE_OUT_SEC);
  player.cur = i; player.chain = chain;
  muteNow();
  if (audio.src !== c.preview) audio.src = c.preview;
  audio.currentTime = 0;
  try {
    await audio.play();
    fadeTo(MAX_GAIN, FADE_IN_SEC);
    setPlaying(i);
  } catch (e) {
    console.error(e);
    toast("試聴を再生できませんでした");
    setPlaying(-1);
  }
  if (chain) c.el.scrollIntoView({ behavior: "smooth", block: "center" });
}
const nextPlayable = (from) => player.cards.findIndex((c, k) => k > from && c.preview);

audio.addEventListener("timeupdate", () => {
  const c = player.cards[player.cur];
  if (c && audio.duration) c.bar.style.width = `${(audio.currentTime / audio.duration) * 100}%`;
});
audio.addEventListener("pause", () => setPlaying(player.cur));
audio.addEventListener("ended", () => {
  const n = player.chain ? nextPlayable(player.cur) : -1;
  if (n >= 0) play(n, true);
  else { player.chain = false; setPlaying(-1); }
});

// ---------------------------------------------------------------- 表示
function cardEl(it, idx, f, track) {
  const s = songOf(it);
  const title = it.title || s?.title || "（曲名未入力）";
  const alts = altsOf(it.songId, it.brand);
  const jk = (it.alt >= 0 && alts[it.alt]?.jacket) || (it.songId != null ? jacketOf(it.songId, it.brand) : "");
  const note = singerNote(s, it.brand);

  const btn = h("button", { type: "button", class: "v-play", "aria-label": `「${title}」を試聴する` },
    h("span", { class: "v-play-icon", "aria-hidden": "true" }));
  const bar = h("span", { class: "v-progress-bar" });
  const term = `${title}${track?.artist ? " " + track.artist.split(/[,、&]/)[0].replace(/\s*[（(]CV.*$/, "") : ""}`;
  const links = h("div", { class: "v-links" },
    track?.preview ? null : h("span", { class: "v-nopreview" }, "試聴はありません"),
    h("a", { class: "v-link apple", target: "_blank", rel: "noopener",
      href: track?.url || `https://music.apple.com/jp/search?term=${encodeURIComponent(title)}` },
      track?.url ? "Apple Musicで聴く" : "Apple Musicで探す"),
    h("a", { class: "v-link spotify", target: "_blank", rel: "noopener",
      href: `https://open.spotify.com/search/${encodeURIComponent(term)}` }, "Spotifyで探す"),
  );

  const el = h("article", { class: "card v-card" + (track?.preview ? " has-preview" : "") },
    h("div", { class: "card-theme" },
      h("span", { class: "card-no" }, String(idx + 1)),
      h("span", { class: "v-theme" }, it.theme || "オススメ曲")),
    h("div", { class: "card-body" },
      h("div", { class: "v-jacket-wrap" },
        jacketEl(jk, it.pos),
        track?.preview ? btn : null),
      h("div", { class: "card-main" },
        h("div", { class: "v-title-row" },
          h("h2", { class: "v-title" }, title),
          note ? h("div", { class: "v-singers" }, note) : null),
        track?.preview ? h("div", { class: "v-progress", "aria-hidden": "true" }, bar) : null,
        links,
        it.pitch ? h("p", { class: "v-pitch" }, it.pitch) : null,
        it.members.length ? h("div", { class: "members" },
          h("div", { class: "members-label" }, "歌って欲しいアイドル"),
          h("div", { class: "tags" }, it.members.map((m) => {
            const c = m.color || brand(m.brand || f.id).color;
            return h("span", { class: "tag v-tag" + (isLight(c) ? " light" : ""), style: { "--tag-bg": c, "--tag-ink": inkFor(c) } }, m.name);
          }))) : null,
      ),
    ),
  );
  const i = player.cards.length;
  player.cards.push({ el, btn, bar, title, preview: track?.preview || "" });
  btn.addEventListener("click", () => play(i));
  return el;
}

function showError(msg) {
  $("#v-name").textContent = "シートを開けませんでした";
  $("#v-brand").hidden = true;
  $(".v-head .brand-line").hidden = true;
  $("#v-items").replaceChildren(h("div", { class: "card v-empty" },
    h("p", {}, msg),
    h("p", {}, h("a", { class: "btn primary", href: "./" }, "楽曲プレゼンシートを作る"))));
}

async function init() {
  const code = codeFromHash();
  const metaP = Promise.all([
    getJSON("data/brands.json"),
    getJSON("data/jackets.json", {}),
    getJSON("data/jacket_alts.json", {}),
    getJSON("data/previews.json", {}),
  ]);
  if (!code) { await metaP.catch(() => {}); showError("URLにシートの内容が入っていません。共有されたURLを最後までコピーできているか確認してください。"); return; }
  let sheet;
  try { sheet = await decodeSheet(code); }
  catch (e) {
    console.error(e);
    showError(typeof DecompressionStream !== "function"
      ? "お使いのブラウザでは、このシートを開けません。ブラウザを最新にしてお試しください。"
      : "URLが途中で切れているか、壊れているようです。共有されたURLを最後までコピーできているか確認してください。");
    return;
  }
  [DB.brands, DB.jackets, DB.jacketAlts, DB.previews] = await metaP;
  const brandIds = [...new Set(sheet.items.map((it) => it.brand))];
  await Promise.all(brandIds.map(async (b) => { DB.songs[b] = await getJSON(`data/songs/${encodeURIComponent(b)}.json`, []); }));

  const f = brand(sheet.from);
  const root = document.documentElement.style;
  root.setProperty("--from", f.color); root.setProperty("--from-ink", f.ink);
  root.setProperty("--to", f.color); root.setProperty("--to-ink", f.ink);
  const name = sheet.name || DEFAULT_NAME;
  document.title = `${name}の${f.name}のおすすめ曲｜アイマス楽曲プレゼンシート`;
  $("#v-name").textContent = name;
  const pill = $("#v-brand");
  pill.textContent = f.name;
  pill.style.background = f.color; pill.style.color = f.ink;

  // 試聴：曲ID → trackId → 試聴URL
  const trackIdOf = (it) => (it.songId == null ? null : DB.previews[String(it.songId)] || null);
  const tracks = await lookupTracks([...new Set(sheet.items.map(trackIdOf).filter(Boolean))]);
  $("#v-items").replaceChildren(...sheet.items.map((it, i) => cardEl(it, i, f, tracks.get(trackIdOf(it)))));

  const playable = player.cards.filter((c) => c.preview).length;
  $("#v-playall").hidden = playable < 2;
  $("#v-note").textContent = playable
    ? `${sheet.items.length}曲中${playable}曲を試聴できます（Apple Music・約30秒）`
    : sheet.items.length ? "試聴できる曲はありません" : "曲が入っていません";
  $("#v-playall").onclick = async () => {
    if (player.chain && !audio.paused) { player.chain = false; await stopWithFade(); setPlaying(-1); return; }
    const first = nextPlayable(-1);
    if (first >= 0) play(first, true);
  };
}

init()
  .catch((e) => { console.error(e); showError("データの読み込みに失敗しました。ページを再読み込みしてください。"); })
  .finally(() => document.documentElement.classList.remove("booting"));
window.addEventListener("hashchange", () => location.reload());
