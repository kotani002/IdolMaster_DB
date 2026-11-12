// アイマス楽曲プレゼンシート
// データ: data/*.json（scripts/fetch_data.py で ふじわらはじめAPI から生成）

const STORE_KEY = "imas-presen-v1";
const HASHTAG = "#アイマス楽曲プレゼン";
const DEFAULT_NAME = "名無しP";
// CORS 非対応の画像は出力時だけプロキシ経由で読む（600px に縮小して軽くする）
// 大きな元画像の初回取得は失敗することがあるので、別ホスト名で再挑戦する
const PROXY_OPTS = "w=600&h=600&fit=inside&output=jpg&q=88";
const IMG_PROXIES = [
  (u) => `https://wsrv.nl/?url=${encodeURIComponent(u)}&${PROXY_OPTS}`,
  (u) => `https://images.weserv.nl/?url=${encodeURIComponent(u)}&${PROXY_OPTS}`,
];

const $ = (sel, root = document) => root.querySelector(sel);
const h = (tag, attrs = {}, ...children) => {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k === "style" && typeof v === "object") {
      for (const [p, val] of Object.entries(v)) {
        if (p.startsWith("--")) el.style.setProperty(p, val);
        else el.style[p] = val;
      }
    }
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (k in el && typeof v !== "string") el[k] = v;
    else el.setAttribute(k, v);
  }
  for (const c of children.flat()) if (c != null && c !== false) el.append(c);
  return el;
};
const uid = () => Math.random().toString(36).slice(2, 10);

// ---------------------------------------------------------------- data

const DB = { brands: [], themes: [], jackets: {}, meta: {}, songs: {}, idols: {} };

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function ensureBrand(id) {
  if (!DB.songs[id]) DB.songs[id] = await getJSON(`data/songs/${id}.json`).catch(() => []);
  if (!DB.idols[id]) DB.idols[id] = await getJSON(`data/idols/${id}.json`).catch(() => []);
}
const brand = (id) => DB.brands.find((b) => b.id === id) || DB.brands[0];

// ---------------------------------------------------------------- state

function newItem(theme = "") {
  return { id: uid(), theme, songId: null, title: "", url: "", jacket: "", jacketAuto: false, pitch: "", members: [] };
}
function defaultState() {
  return { name: "", from: "ml", to: "cg", items: [newItem(DB.themes[0] || "まず聴いてほしい曲")] };
}

let state;
function loadState() {
  try {
    const s = JSON.parse(localStorage.getItem(STORE_KEY) || "null");
    if (s && Array.isArray(s.items)) return s;
  } catch {}
  return null;
}
let saveTimer = 0;
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(() => {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
    catch { toast("ブラウザへの保存に失敗しました（端末画像が大きすぎる可能性があります）"); }
  }, 250);
}

// ---------------------------------------------------------------- utils

function toast(msg, ms = 2600) {
  const t = $("#toast");
  t.textContent = msg;
  t.classList.add("show");
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove("show"), ms);
}

// カナ・ひらがな・全角半角・大小文字の違いを吸収して検索する
function norm(s) {
  return (s || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/[ァ-ヶ]/g, (c) => String.fromCharCode(c.charCodeAt(0) - 0x60))
    .replace(/[\s・☆★♪!！?？、。,.\-ー〜~'’"”()（）「」『』]/g, "");
}

function hexToRgb(hex) {
  let x = (hex || "").replace("#", "");
  if (x.length === 3) x = x.split("").map((c) => c + c).join("");
  const n = parseInt(x, 16);
  if (Number.isNaN(n) || x.length !== 6) return null;
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function inkFor(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return "#fff";
  const [r, g, b] = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  const L = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return L > 0.45 ? "#2a2730" : "#ffffff";
}
// 白と混ぜた淡色（html2canvas 用に color-mix を使わず計算）
function tint(hex, ratio) {
  const rgb = hexToRgb(hex) || [200, 200, 200];
  const m = rgb.map((v) => Math.round(v * ratio + 255 * (1 - ratio)));
  return `rgb(${m.join(",")})`;
}

function applyBrandColors() {
  const f = brand(state.from), t = brand(state.to);
  const root = document.documentElement.style;
  root.setProperty("--from", f.color);
  root.setProperty("--from-ink", f.ink);
  root.setProperty("--to", t.color);
  root.setProperty("--to-ink", t.ink);
}

// 曲のブランド（選曲時に記録。未記録の古いデータは「から」側のブランド）
const songBrand = (it) => it.brand || state.from;

function memberColor(m) {
  return m.color || brand(m.brand || state.to).color;
}

function autosize(ta) {
  ta.style.height = "";
  if (!ta.value) return; // 空のときは min-height に任せる（placeholder の折り返しで伸びるのを防ぐ）
  ta.style.height = "auto";
  ta.style.height = ta.scrollHeight + 2 + "px";
}

// ---------------------------------------------------------------- header

function renderHead() {
  const nameIn = $("#in-name");
  nameIn.value = state.name;
  nameIn.oninput = () => { state.name = nameIn.value; save(); };

  for (const [sel, key] of [["#sel-from", "from"], ["#sel-to", "to"]]) {
    const s = $(sel);
    s.replaceChildren(...DB.brands.map((b) => h("option", { value: b.id }, b.name)));
    s.value = state[key];
    s.onchange = async () => {
      const other = key === "from" ? "to" : "from";
      if (s.value === state[other]) state[other] = state[key]; // 同じブランドを選んだら入れ替え
      state[key] = s.value;
      await onBrandChange();
    };
  }
  $("#btn-swap").onclick = async () => {
    [state.from, state.to] = [state.to, state.from];
    await onBrandChange();
  };
}

async function onBrandChange() {
  await Promise.all([ensureBrand(state.from), ensureBrand(state.to)]);
  $("#sel-from").value = state.from;
  $("#sel-to").value = state.to;
  applyBrandColors();
  renderItems();
  save();
}

// ---------------------------------------------------------------- cards

function renderItems() {
  const box = $("#items");
  box.replaceChildren(...state.items.map((it, i) => cardEl(it, i)));
  box.querySelectorAll(".pitch").forEach(autosize);
}

function cardEl(it, idx) {
  const n = state.items.length;
  const card = h("article", { class: "card", "data-id": it.id });

  // --- お題（○○な曲）
  const themeIn = h("input", {
    class: "theme-input", type: "text", value: it.theme, maxlength: "40",
    placeholder: "○○な曲（自由に入力）", "aria-label": "お題",
    oninput: () => { it.theme = themeIn.value; syncChips(); save(); },
  });
  const chips = h("div", { class: "theme-chips" },
    DB.themes.map((t) => h("button", {
      type: "button", class: "chip", "data-t": t,
      onclick: () => { it.theme = t; themeIn.value = t; syncChips(); save(); card.classList.remove("show-themes"); },
    }, t)));
  function syncChips() {
    chips.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c.dataset.t === it.theme));
  }
  syncChips();

  const move = (d) => {
    const j = idx + d;
    if (j < 0 || j >= n) return;
    [state.items[idx], state.items[j]] = [state.items[j], state.items[idx]];
    renderItems(); save();
  };
  const head = h("div", { class: "card-theme" },
    h("span", { class: "card-no" }, String(idx + 1)),
    themeIn,
    h("button", { type: "button", class: "tool", title: "お題から選ぶ", onclick: () => card.classList.toggle("show-themes") }, "お題"),
    h("button", { type: "button", class: "tool", title: "上へ", disabled: idx === 0, onclick: () => move(-1) }, "↑"),
    h("button", { type: "button", class: "tool", title: "下へ", disabled: idx === n - 1, onclick: () => move(1) }, "↓"),
    h("button", {
      type: "button", class: "tool danger", title: "この曲を削除",
      onclick: () => {
        const filled = it.title || it.pitch || it.members.length;
        if (filled && !confirm("この曲を削除しますか？")) return;
        state.items.splice(idx, 1);
        renderItems(); save();
      },
    }, "×"),
  );

  // --- ジャケット
  const jacket = h("button", { type: "button", class: "jacket", "aria-label": "ジャケット画像を設定", onclick: () => openJacket(it) },
    h("span", {}));
  // 保存済みの曲も jackets.json の最新の内容で補完する（データ追加前に選んだ曲・URLが更新された曲）
  if (it.songId && (!it.jacket || it.jacketAuto)) {
    const jk = DB.jackets[String(it.songId)];
    if (jk && jk !== it.jacket) { it.jacket = jk; it.jacketAuto = true; save(); }
  }
  paintJacket(jacket, it);

  // --- 曲名（検索 + 自由入力）
  const songIn = h("input", {
    class: "song-input", type: "text", value: it.title, placeholder: `曲名（${brand(state.from).short}の曲から検索）`,
    autocomplete: "off", "aria-label": "曲名", role: "combobox", "aria-expanded": "false",
  });
  const list = h("ul", { class: "suggest", hidden: true, role: "listbox" });

  let results = [], active = -1;
  const pick = (s) => {
    it.title = s.title; it.songId = s.id; it.url = s.url; it.brand = state.from;
    // 楽曲に対応するジャケットがあれば自動で差し替える（自分で設定したジャケットは残す）
    const jk = DB.jackets[String(s.id)];
    if (jk && (it.jacketAuto || !it.jacket)) { it.jacket = jk; it.jacketAuto = true; }
    else if (!jk && it.jacketAuto) { it.jacket = ""; it.jacketAuto = false; }
    paintJacket(jacket, it);
    songIn.value = s.title;
    close(); save();
  };
  const close = () => { list.hidden = true; songIn.setAttribute("aria-expanded", "false"); active = -1; };
  const draw = () => {
    list.replaceChildren(...(results.length
      ? results.map((s, i) => h("li", {
          role: "option", class: i === active ? "active" : "",
          onmousedown: (e) => { e.preventDefault(); pick(s); },
        }, s.title, s.kana && norm(s.kana) !== norm(s.title) ? h("small", {}, s.kana) : null))
      : [h("li", { class: "empty" }, "見つかりません（このまま自由入力もできます）")]));
    list.hidden = false;
    songIn.setAttribute("aria-expanded", "true");
  };
  const search = () => {
    const q = norm(songIn.value);
    if (!q) { results = []; close(); return; }
    const songs = DB.songs[state.from] || [];
    const starts = [], contains = [];
    for (const s of songs) {
      const a = norm(s.title), k = norm(s.kana);
      if (a.startsWith(q) || k.startsWith(q)) starts.push(s);
      else if (a.includes(q) || k.includes(q)) contains.push(s);
      if (starts.length > 40) break;
    }
    results = starts.concat(contains).slice(0, 30);
    active = results.length ? 0 : -1;
    draw();
  };
  songIn.addEventListener("input", () => {
    it.title = songIn.value; it.songId = null; it.url = ""; it.brand = state.from;
    if (it.jacketAuto) { it.jacket = ""; it.jacketAuto = false; }
    paintJacket(jacket, it, true);
    save(); search();
  });
  songIn.addEventListener("focus", () => { if (songIn.value && !it.songId) search(); });
  songIn.addEventListener("blur", () => { close(); if (!it.jacket) paintJacket(jacket, it); });
  songIn.addEventListener("keydown", (e) => {
    if (list.hidden || !results.length) return;
    if (e.key === "ArrowDown") { active = (active + 1) % results.length; draw(); e.preventDefault(); }
    else if (e.key === "ArrowUp") { active = (active - 1 + results.length) % results.length; draw(); e.preventDefault(); }
    else if (e.key === "Enter" && active >= 0) { pick(results[active]); e.preventDefault(); }
    else if (e.key === "Escape") close();
  });

  // --- プレゼン内容
  const pitch = h("textarea", {
    class: "pitch", placeholder: "プレゼン内容：この曲のここが好き！こんな人に刺さる！", maxlength: "400", "aria-label": "プレゼン内容",
  });
  pitch.value = it.pitch;
  pitch.addEventListener("input", () => { it.pitch = pitch.value; autosize(pitch); save(); });

  // --- 歌唱予想メンバー
  const tags = h("div", { class: "tags" });
  const drawTags = () => {
    tags.replaceChildren(
      ...it.members.map((m, i) => {
        const c = memberColor(m);
        return h("span", { class: "tag", style: { "--tag-bg": c, "--tag-ink": inkFor(c) } },
          m.name,
          h("button", {
            type: "button", "aria-label": `${m.name}を外す`,
            onclick: () => { it.members.splice(i, 1); drawTags(); save(); },
          }, "×"));
      }),
      h("button", { type: "button", class: "tag-add", onclick: () => openMembers(it, drawTags) }, "＋ メンバーを選ぶ"),
    );
  };
  drawTags();

  card.append(
    head, chips,
    h("div", { class: "card-body" },
      jacket,
      h("div", { class: "card-main" },
        h("div", { class: "song-field" }, songIn, list),
        pitch,
        h("div", {},
          h("div", { class: "members-label" }, "歌唱予想メンバー"),
          tags),
      ),
    ),
  );
  return card;
}

const JK_WAIT = "楽曲を選ぶと自動で更新されます";
const JK_FAIL = "ジャケットの取得に失敗しました。自分でジャケットの設定ができます";

// ジャケット枠の表示：画像 / 選曲待ち / 取得失敗（＝自分で設定してね）
// typing=true の間は入力途中なので失敗表示にしない
function paintJacket(el, it, typing = false) {
  const span = el.querySelector("span");
  const token = (el._tok = (el._tok || 0) + 1);
  const fail = () => {
    setBg(el, "");
    el.classList.add("is-failed");
    span.textContent = JK_FAIL;
  };
  el.classList.remove("is-failed");
  if (it.jacket) {
    setBg(el, it.jacket);
    const img = new Image();
    img.onerror = () => { if (el._tok === token) fail(); };
    img.src = it.jacket;
    return;
  }
  setBg(el, "");
  if (!typing && (it.songId || it.title.trim())) fail();
  else span.textContent = JK_WAIT;
}

function setBg(el, url) {
  el.style.backgroundImage = url ? `url("${url.replace(/"/g, "%22")}")` : "";
  el.classList.toggle("has-img", !!url);
}

// ---------------------------------------------------------------- member dialog

// 初期表示は「その曲のブランド」のアイドル。ブランドのタグで他ブランドにも切り替えられる
const memDlg = { item: null, onDone: null, brand: "", group: "" };

async function openMembers(item, onDone) {
  memDlg.item = item; memDlg.onDone = onDone;
  memDlg.brand = songBrand(item); memDlg.group = "";
  await Promise.all(DB.brands.map((b) => ensureBrand(b.id)));
  $("#mem-brand").textContent = item.title ? `「${item.title}」` : "";
  $("#mem-search").value = "";
  $("#mem-custom-in").value = "";
  drawBrandChips();
  drawGroupChips();
  drawMemList();
  $("#dlg-members").showModal();
  if (matchMedia("(pointer:fine)").matches) $("#mem-search").focus();
}

function drawBrandChips() {
  const box = $("#mem-brands");
  box.replaceChildren(...DB.brands.map((b) => {
    const on = b.id === memDlg.brand;
    return h("button", {
      type: "button", class: "chip brand-chip" + (on ? " on" : ""), "aria-pressed": String(on),
      style: on ? { background: b.color, borderColor: b.color, color: b.ink } : { borderColor: b.color },
      onclick: () => { memDlg.brand = b.id; memDlg.group = ""; drawBrandChips(); drawGroupChips(); drawMemList(); },
    }, b.id === songBrand(memDlg.item) ? `${b.short}（この曲）` : b.short);
  }));
}

function drawGroupChips() {
  const idols = DB.idols[memDlg.brand] || [];
  const groups = [...new Set(idols.map((i) => i.group).filter(Boolean))];
  const gbox = $("#mem-groups");
  gbox.replaceChildren(...(groups.length > 1
    ? ["", ...groups].map((g) => h("button", {
        type: "button", class: "chip" + (g === memDlg.group ? " on" : ""), "data-g": g,
        onclick: () => { memDlg.group = g; gbox.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c.dataset.g === g)); drawMemList(); },
      }, g || "すべて"))
    : []));
}

function drawMemList() {
  const it = memDlg.item;
  const b = brand(memDlg.brand);
  const q = norm($("#mem-search").value);
  const idols = (DB.idols[memDlg.brand] || []).filter((i) =>
    (!memDlg.group || i.group === memDlg.group) &&
    (!q || norm(i.name).includes(q) || norm(i.kana).includes(q) || norm(i.cv).includes(q)));
  const chosen = new Set(it.members.map((m) => m.name));
  $("#mem-list").replaceChildren(...idols.map((i) => h("button", {
    type: "button", class: "mem-item" + (chosen.has(i.name) ? " on" : ""), "aria-pressed": String(chosen.has(i.name)),
    onclick: () => {
      const k = it.members.findIndex((m) => m.name === i.name);
      if (k >= 0) it.members.splice(k, 1);
      else it.members.push({ name: i.name, color: i.color || "", brand: b.id });
      drawMemList(); memDlg.onDone?.(); save();
    },
  }, h("span", { class: "dot", style: { "--c": i.color || b.color } }),
     h("span", {}, i.name, i.cv ? h("small", {}, `CV.${i.cv}`) : null))));
  $("#mem-count").textContent = `${it.members.length}人選択中`;
}

function addCustomMember() {
  const inp = $("#mem-custom-in");
  const name = inp.value.trim();
  if (!name || !memDlg.item) return;
  if (!memDlg.item.members.some((m) => m.name === name)) memDlg.item.members.push({ name, color: "", brand: memDlg.brand });
  inp.value = "";
  drawMemList(); memDlg.onDone?.(); save();
}

// ---------------------------------------------------------------- jacket dialog

const jkDlg = { item: null, value: "" };

function openJacket(item) {
  jkDlg.item = item; jkDlg.value = item.jacket || "";
  $("#jk-url").value = jkDlg.value.startsWith("data:") ? "" : jkDlg.value;
  setBg($("#jk-preview"), jkDlg.value);
  $("#dlg-jacket").showModal();
}

async function fileToDataURL(file, max = 640) {
  const bmp = await createImageBitmap(file);
  const s = Math.min(1, max / Math.max(bmp.width, bmp.height));
  const c = document.createElement("canvas");
  c.width = Math.round(bmp.width * s); c.height = Math.round(bmp.height * s);
  c.getContext("2d").drawImage(bmp, 0, 0, c.width, c.height);
  return c.toDataURL("image/jpeg", 0.86);
}

// ---------------------------------------------------------------- export

function blobToDataURL(b) {
  return new Promise((res, rej) => { const r = new FileReader(); r.onload = () => res(r.result); r.onerror = rej; r.readAsDataURL(b); });
}
async function fetchImage(u, ms = 8000) {
  const ctl = new AbortController();
  const timer = setTimeout(() => ctl.abort(), ms); // 応答がない画像で出力が止まらないように
  const r = await fetch(u, { mode: "cors", credentials: "omit", signal: ctl.signal }).finally(() => clearTimeout(timer));
  if (!r.ok) throw new Error(String(r.status));
  const b = await r.blob();
  if (!b.type.startsWith("image/")) throw new Error("not image");
  return blobToDataURL(b);
}
// 画像出力用にジャケットを data URL 化（CORS 不可なら画像プロキシ経由で再挑戦）
async function resolveJacket(u) {
  if (!u) return "";
  if (u.startsWith("data:")) return u;
  try { return await fetchImage(u); } catch {}
  for (const proxy of IMG_PROXIES) {
    try { return await fetchImage(proxy(u), 20000); } catch {}
  }
  return null;
}

function buildSheet(jackets) {
  const f = brand(state.from), t = brand(state.to);
  const items = state.items.filter((it) => it.title || it.pitch || it.members.length || it.jacket);
  const bg = `linear-gradient(160deg, ${tint(f.color, 0.26)} 0%, #fbf8f3 34%, #fbf8f3 66%, ${tint(t.color, 0.22)} 100%)`;
  return h("div", { class: "x-sheet", style: { backgroundImage: bg } },
    h("div", { class: "x-head" },
      h("div", { class: "x-name" }, state.name.trim() || DEFAULT_NAME),
      h("div", { class: "x-sub" },
        h("span", { class: "x-pill", style: { background: f.color, color: f.ink } }, f.name),
        h("span", {}, "から"),
        h("span", { class: "x-pill", style: { background: t.color, color: t.ink } }, t.name),
        h("span", {}, "へのオススメ曲")),
    ),
    h("div", { class: "x-items" }, items.map((it, i) => {
      const jk = jackets.get(it.id);
      return h("div", { class: "x-card" },
        h("div", { class: "x-theme", style: { background: tint(f.color, 0.2), borderBottom: `3px solid ${tint(f.color, 0.45)}` } },
          h("span", { class: "x-no", style: { background: f.color, color: f.ink } }, String(i + 1)),
          h("span", {}, it.theme.trim() || "オススメ曲")),
        h("div", { class: "x-body" },
          h("div", { class: "x-jacket", style: jk ? { backgroundImage: `url("${jk}")` } : {} }, jk ? "" : "NO IMAGE"),
          h("div", { class: "x-main" },
            h("div", { class: "x-title" }, it.title.trim() || "（曲名未入力）"),
            h("div", { class: "x-pitch" }, it.pitch.trim()),
            it.members.length ? h("div", { class: "x-mem-label" }, "歌唱予想メンバー") : null,
            it.members.length ? h("div", { class: "x-tags" }, it.members.map((m) => {
              const c = memberColor(m);
              return h("span", { class: "x-tag", style: { background: c, color: inkFor(c) } }, m.name);
            })) : null,
          ),
        ),
      );
    })),
    h("div", { class: "x-foot" },
      h("span", {}, h("b", {}, HASHTAG), "　", location.host + location.pathname.replace(/index\.html$/, "")),
      h("span", {}, "楽曲データ：ふじわらはじめ (CC BY-NC 4.0)")),
  );
}

let lastExport = null; // { blob, url }

async function exportImage() {
  if (!state.items.some((it) => it.title || it.pitch)) { toast("曲名かプレゼン内容を入力してください"); return; }
  if (typeof html2canvas !== "function") { toast("画像ライブラリを読み込めませんでした。通信状態を確認してください"); return; }
  $("#loading").hidden = false;
  try {
    const jackets = new Map();
    let failed = 0;
    await Promise.all(state.items.map(async (it) => {
      const d = await resolveJacket(it.jacket);
      if (d === null) failed++;
      jackets.set(it.id, d || "");
    }));
    await document.fonts.ready;
    const stage = $("#export-stage");
    const sheet = buildSheet(jackets);
    stage.replaceChildren(sheet);
    // レイアウト確定待ち（requestAnimationFrame は裏タブで止まるのでタイマーで待つ）
    await new Promise((r) => setTimeout(r, 60));
    const scale = sheet.offsetHeight * 2 > 14000 ? 1 : 2;
    const canvas = await html2canvas(sheet, { scale, backgroundColor: "#fbf8f3", logging: false, useCORS: true });
    stage.replaceChildren();
    const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
    if (!blob) throw new Error("toBlob failed");
    if (lastExport?.url) URL.revokeObjectURL(lastExport.url);
    lastExport = { blob, url: URL.createObjectURL(blob) };
    $("#ex-img").src = lastExport.url;
    $("#ex-note").textContent = failed
      ? `ジャケット ${failed} 件は配信元の制限で読み込めず「NO IMAGE」になりました。端末に保存した画像を選ぶと確実です。`
      : "";
    $("#ex-share").hidden = !canShareFile();
    $("#dlg-export").showModal();
  } catch (e) {
    console.error(e);
    toast("画像の作成に失敗しました");
  } finally {
    $("#loading").hidden = true;
  }
}

const fileName = () => `imas-presen-${state.from}-to-${state.to}.png`;
const shareText = () => `${HASHTAG}\n${brand(state.from).name} から ${brand(state.to).name} へのオススメ曲\n${location.origin}${location.pathname}`;

function canShareFile() {
  try {
    return !!navigator.canShare && navigator.canShare({ files: [new File([""], "a.png", { type: "image/png" })] });
  } catch { return false; }
}
function download() {
  const a = h("a", { href: lastExport.url, download: fileName() });
  document.body.append(a); a.click(); a.remove();
}
async function copyImage() {
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": lastExport.blob })]);
    toast("画像をコピーしました");
    return true;
  } catch {
    toast("このブラウザではコピーできません。保存してから添付してください");
    return false;
  }
}

// ---------------------------------------------------------------- wire up

function wire() {
  $("#btn-add").onclick = () => {
    const used = new Set(state.items.map((i) => i.theme));
    const next = DB.themes.find((t) => !used.has(t)) || "";
    state.items.push(newItem(next));
    renderItems(); save();
    const cards = document.querySelectorAll(".card");
    cards[cards.length - 1]?.scrollIntoView({ behavior: "smooth", block: "center" });
  };
  $("#btn-reset").onclick = () => {
    if (!confirm("入力内容をすべて消してリセットしますか？")) return;
    state = defaultState();
    renderHead(); onBrandChange();
  };
  $("#btn-export").onclick = exportImage;
  let rz = 0;
  window.addEventListener("resize", () => {
    clearTimeout(rz);
    rz = setTimeout(() => document.querySelectorAll(".pitch").forEach(autosize), 150);
  });

  $("#mem-search").addEventListener("input", drawMemList);
  $("#mem-custom-add").onclick = addCustomMember;
  $("#mem-custom-in").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addCustomMember(); } });
  $("#mem-search").addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); });

  $("#jk-url").addEventListener("input", () => {
    jkDlg.value = $("#jk-url").value.trim();
    setBg($("#jk-preview"), jkDlg.value);
  });
  $("#jk-file").addEventListener("change", async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    try {
      jkDlg.value = await fileToDataURL(f);
      $("#jk-url").value = "";
      setBg($("#jk-preview"), jkDlg.value);
    } catch { toast("画像を読み込めませんでした"); }
  });
  $("#jk-clear").onclick = () => { jkDlg.value = ""; $("#jk-url").value = ""; setBg($("#jk-preview"), ""); };
  // 「決定」で反映（dialog の close イベントには頼らない）
  const applyJacket = () => {
    if (!jkDlg.item) return;
    const v = jkDlg.value;
    if (v && !v.startsWith("data:") && !/^https?:\/\//i.test(v)) { toast("http(s) で始まる画像URLを入力してください"); return; }
    jkDlg.item.jacket = v;
    jkDlg.item.jacketAuto = false; // 自分で設定したものは選曲し直しても消さない
    const el = document.querySelector(`.card[data-id="${jkDlg.item.id}"] .jacket`);
    if (el) paintJacket(el, jkDlg.item);
    save();
    $("#dlg-jacket").close();
  };
  $("#jk-ok").addEventListener("click", (e) => { e.preventDefault(); applyJacket(); });
  $("#jk-url").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); applyJacket(); } });
  $("#jk-close").addEventListener("click", (e) => { e.preventDefault(); $("#dlg-jacket").close(); });

  $("#ex-close").onclick = () => $("#dlg-export").close();
  $("#ex-save").onclick = download;
  $("#ex-copy").onclick = copyImage;
  $("#ex-share").onclick = async () => {
    try {
      await navigator.share({ files: [new File([lastExport.blob], fileName(), { type: "image/png" })], text: shareText() });
    } catch (e) { if (e?.name !== "AbortError") toast("共有できませんでした"); }
  };
  $("#ex-x").onclick = async () => {
    const copied = matchMedia("(pointer:fine)").matches ? await copyImage() : false;
    if (!copied) download();
    window.open(`https://x.com/intent/post?text=${encodeURIComponent(shareText())}`, "_blank", "noopener,noreferrer");
    toast(copied ? "画像をコピーしました。ポスト画面に貼り付けてください" : "画像を保存しました。ポストに添付してください", 4000);
  };
}

async function init() {
  [DB.brands, DB.themes, DB.jackets, DB.meta] = await Promise.all([
    getJSON("data/brands.json"),
    getJSON("data/themes.json").catch(() => []),
    getJSON("data/jackets.json").catch(() => ({})),
    getJSON("data/meta.json").catch(() => ({})),
  ]);
  state = loadState() || defaultState();
  if (!DB.brands.some((b) => b.id === state.from)) state.from = DB.brands[0].id;
  if (!DB.brands.some((b) => b.id === state.to) || state.to === state.from) state.to = DB.brands.find((b) => b.id !== state.from).id;
  if (DB.meta.updated_at) $("#data-date").textContent = ` / データ更新 ${DB.meta.updated_at}`;
  wire();
  renderHead();
  await onBrandChange();
}

init().catch((e) => {
  console.error(e);
  document.querySelector("#items").textContent = "データの読み込みに失敗しました。ページを再読み込みしてください。";
});
