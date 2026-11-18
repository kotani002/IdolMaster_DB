// アイマス楽曲プレゼンシート
// データ: data/*.json（scripts/fetch_data.py で ふじわらはじめAPI から生成）

const STORE_KEY = "imas-presen-v2"; // v2: 初期状態を「曲なし」に変更したので、以前の下書きは引き継がない
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

const DB = { brands: [], themes: [], jackets: {}, meta: {}, events: [], units: {}, songs: {}, idols: {} };

// 楽曲のジャケット。越境曲はブランドごとに別の盤があるので「ブランド:曲ID」を先に見る
function jacketOf(songId, brandId) {
  return DB.jackets[`${brandId}:${songId}`] || DB.jackets[String(songId)];
}

async function getJSON(path) {
  const r = await fetch(path, { cache: "no-cache" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

async function ensureBrand(id) {
  if (!DB.songs[id]) DB.songs[id] = isPickable(brand(id)) ? await getJSON(`data/songs/${id}.json`).catch(() => []) : [];
  if (!DB.idols[id]) DB.idols[id] = await getJSON(`data/idols/${id}.json`).catch(() => []);
}

// データを取りに行く間は、起動時と同じ「読み込み中…」を出す（<html class="booting">）。
// すぐ終わる（取得済み・キャッシュ）ときにちらつかないよう、少し待ってから出す。起動中に呼ばれたら外さない
async function withLoading(task) {
  const root = document.documentElement;
  const wasBooting = root.classList.contains("booting");
  const timer = setTimeout(() => root.classList.add("booting"), 120);
  try {
    return await task();
  } finally {
    clearTimeout(timer);
    if (!wasBooting) root.classList.remove("booting");
  }
}
const brand = (id) => DB.brands.find((b) => b.id === id) || DB.brands[0];
// おすすめするブランドとして選べるブランド。selectable:false は歌唱メンバーの候補にだけ出す（楽曲データがないブランド）
const isPickable = (b) => b.selectable !== false;
const pickableBrands = () => DB.brands.filter(isPickable);

// ---------------------------------------------------------------- state

function newItem(theme = "") {
  return { id: uid(), theme, songId: null, title: "", url: "", jacket: "", jacketAuto: false, pitch: "", members: [] };
}
function defaultState() {
  return { name: "", from: "ml", items: [] }; // 最初は曲なし（「＋新しい曲を追加する」が一番上に来る）
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
function saveNow() {
  clearTimeout(saveTimer);
  if (!state) return;
  try { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
  catch { toast("ブラウザへの保存に失敗しました（端末画像が大きすぎる可能性があります）"); }
}
function save() {
  clearTimeout(saveTimer);
  saveTimer = setTimeout(saveNow, 250);
}
// 音楽アプリなどに切り替えた瞬間（タブが裏に回る・ページが破棄される直前）に、待たずに保存する。
// スマホのブラウザは裏に回ったタブを予告なく破棄することがあるため。
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") saveNow(); });
window.addEventListener("pagehide", saveNow);
// ブラウザの容量不足による自動削除を避けるよう依頼する（対応ブラウザのみ）
try { navigator.storage?.persist?.(); } catch {}

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
function luminance(hex) {
  const rgb = hexToRgb(hex);
  if (!rgb) return 0;
  const [r, g, b] = rgb.map((v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}
function inkFor(hex) {
  if (!hexToRgb(hex)) return "#fff";
  return luminance(hex) > 0.45 ? "#2a2730" : "#ffffff";
}
// 白に近いイメージカラー（及川雫 #ffffff・桑山千雪など）は白地に溶けるので、タグに縁取りを付ける
const isLight = (hex) => luminance(hex) > 0.75;
// 白と混ぜた淡色（html2canvas 用に color-mix を使わず計算）
function tint(hex, ratio) {
  const rgb = hexToRgb(hex) || [200, 200, 200];
  const m = rgb.map((v) => Math.round(v * ratio + 255 * (1 - ratio)));
  return `rgb(${m.join(",")})`;
}

function applyBrandColors() {
  // （以前は「から／へ」の2ブランドだった名残で --to も使っているので、同じ色を入れる）
  const f = brand(state.from);
  const root = document.documentElement.style;
  root.setProperty("--from", f.color);
  root.setProperty("--from-ink", f.ink);
  root.setProperty("--to", f.color);
  root.setProperty("--to-ink", f.ink);
}

// 曲のブランド（選曲時に記録。未記録の古いデータはおすすめするブランド）
const songBrand = (it) => it.brand || state.from;

function memberColor(m) {
  return m.color || brand(m.brand || state.from).color;
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
  const syncFilled = () => nameIn.closest(".field-name").classList.toggle("filled", !!nameIn.value.trim());
  nameIn.value = state.name;
  syncFilled();
  nameIn.oninput = () => { state.name = nameIn.value; syncFilled(); save(); };

  const s = $("#sel-from");
  s.replaceChildren(...pickableBrands().map((b) => h("option", { value: b.id }, b.name)));
  s.value = state.from;
  s.onchange = () => changeBrands(s.value);
}

// おすすめするブランドが変わると、別ブランドの曲が入ったカードは矛盾するので確認してリセットする
async function changeBrands(nextFrom) {
  const stale = state.items.filter((it) => it.title.trim() && songBrand(it) !== nextFrom);
  if (stale.length) {
    const names = [...new Set(stale.map((it) => brand(songBrand(it)).name))].join("・");
    const ok = confirm(
      `${names}の曲が${stale.length}曲入っています。\n` +
      `おすすめするブランドを${brand(nextFrom).name}に変えると、これらのカードの曲名・ジャケット・プレゼン内容・歌って欲しいアイドルがリセットされます（お題は残ります）。\n変更しますか？`);
    if (!ok) {
      $("#sel-from").value = state.from;
      return;
    }
    for (const it of stale) {
      Object.assign(it, { title: "", songId: null, url: "", jacket: "", jacketAuto: false, brand: nextFrom, pitch: "", members: [] });
    }
  }
  state.from = nextFrom;
  await onBrandChange();
}

async function onBrandChange() {
  await withLoading(() => ensureBrand(state.from));
  $("#sel-from").value = state.from;
  applyBrandColors();
  renderItems();
  save();
}

// ---------------------------------------------------------------- cards

function renderItems() {
  const box = $("#items");
  box.replaceChildren(...state.items.map((it, i) => cardEl(it, i)));
  box.querySelectorAll(".pitch, .theme-input").forEach(autosize);
}

function cardEl(it, idx) {
  const n = state.items.length;
  const card = h("article", { class: "card", "data-id": it.id });

  // --- お題（○○な曲）
  // 1行入力だとスマホで長いお題が途中で切れるので、折り返せる textarea（改行は入れさせない）にする
  const themeIn = h("textarea", {
    class: "theme-input", rows: "1", maxlength: "40",
    placeholder: "○○な曲（自由に入力できます）", "aria-label": "お題（自由に入力できます）",
    oninput: () => {
      if (/[\r\n]/.test(themeIn.value)) themeIn.value = themeIn.value.replace(/[\r\n]+/g, " ");
      it.theme = themeIn.value; autosize(themeIn); syncChips(); save();
    },
    onkeydown: (e) => { if (e.key === "Enter") { e.preventDefault(); themeIn.blur(); } },
  });
  themeIn.value = it.theme;
  // 鉛筆アイコン：お題は選ぶだけでなく自由に書き込めることを知らせる
  const themeBox = h("label", { class: "theme-box", title: "お題は自由に入力できます" },
    themeIn, h("span", { class: "theme-edit", "aria-hidden": "true" }, "✎"));
  const chips = h("div", { class: "theme-chips" },
    DB.themes.map((t) => h("button", {
      type: "button", class: "chip", "data-t": t,
      onclick: () => { it.theme = t; themeIn.value = t; autosize(themeIn); syncChips(); save(); card.classList.remove("show-themes"); },
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
    themeBox,
    h("button", { type: "button", class: "tool theme-pick", title: "お題の候補から選ぶ", onclick: () => card.classList.toggle("show-themes") }, "お題を選ぶ ▾"),
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
  // スマホ（指で操作する画面）はスクロール中に誤ってジャケットに触れやすいので、2回タップで開く。
  // 1回目は「もう一度タップでジャケット変更」を出して待つ（少し経つと戻る）。マウス・キーボードは1回で開く
  const jacket = h("button", {
    type: "button", class: "jacket", "aria-label": "ジャケット画像を設定",
    onclick: (e) => {
      const touch = matchMedia("(pointer: coarse)").matches && e.detail !== 0; // detail 0 はキーボード操作
      if (!touch || jacket.classList.contains("armed")) {
        jacket.classList.remove("armed"); clearTimeout(jacket._armT);
        openJacket(it);
        return;
      }
      jacket.classList.add("armed");
      clearTimeout(jacket._armT);
      jacket._armT = setTimeout(() => jacket.classList.remove("armed"), 1500);
    },
  }, h("span", {}));
  // 保存済みの曲も jackets.json の最新の内容で補完する（データ追加前に選んだ曲・URLが更新された曲）
  if (it.songId && (!it.jacket || it.jacketAuto)) {
    const jk = jacketOf(it.songId, it.brand || state.from);
    if (jk && jk !== it.jacket) { it.jacket = jk; it.jacketAuto = true; save(); }
  }
  paintJacket(jacket, it);

  // --- 曲名（検索 + 自由入力）
  const songIn = h("input", {
    class: "song-input", type: "text", value: it.title, placeholder: `${brand(state.from).short}の曲名・ユニット名・アイドル名で検索`,
    autocomplete: "off", autocapitalize: "off", autocorrect: "off", spellcheck: "false",
    "aria-label": "曲名", role: "combobox", "aria-expanded": "false",
  });
  const list = h("ul", { class: "suggest", hidden: true, role: "listbox" });
  const icon = h("span", { class: "song-icon", "aria-hidden": "true" });
  icon.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round"><circle cx="10.5" cy="10.5" r="6.5"/><path d="M15.5 15.5 21 21"/></svg>';
  const songField = h("div", { class: "song-field" }, h("span", { class: "song-box" }, songIn, icon), list);
  // 曲名が入ったら枠を控えめにする（未入力の間はブランドカラーの破線で目立たせる）
  const syncSongField = () => songField.classList.toggle("filled", !!it.title.trim());
  syncSongField();

  let results = [], active = -1;
  let hitNote = new Map(); // ユニット名・歌唱者名で見つかった曲 → 候補に出す「ユニット：名前」「歌：名前」
  // スマホの日本語入力は変換中の文字が確定されずに残るため、候補をタップした時に
  // 「候補の曲名 + 入力途中の文字」になってしまう。先に入力欄を外して変換を確定させてから曲名で上書きし、
  // 直後に遅れて届く入力イベントも無視する。
  let pickedAt = 0;
  const pick = (s) => {
    if (document.activeElement === songIn) songIn.blur();
    pickedAt = performance.now();
    it.title = s.title; it.songId = s.id; it.url = s.url; it.brand = state.from;
    // 楽曲に対応するジャケットがあれば自動で差し替える（自分で設定したジャケットは残す）
    const jk = jacketOf(s.id, state.from);
    if (jk && (it.jacketAuto || !it.jacket)) { it.jacket = jk; it.jacketAuto = true; it.jkPos = "auto"; }
    else if (!jk && it.jacketAuto) { it.jacket = ""; it.jacketAuto = false; it.jkPos = "auto"; }
    paintJacket(jacket, it);
    songIn.value = s.title;
    close(); syncSongField(); save();
  };
  const close = () => { list.hidden = true; songIn.setAttribute("aria-expanded", "false"); active = -1; };
  const draw = () => {
    list.replaceChildren(...(results.length
      ? results.map((s, i) => h("li", {
          role: "option", class: i === active ? "active" : "",
          // 押した瞬間に選ぶとスマホで候補をスクロールできない（触れた曲が選ばれる）ので、タップ（click）で選ぶ。
          // pointerdown は入力欄からフォーカスが外れて候補が閉じないように止めるだけ
          onpointerdown: (e) => e.preventDefault(),
          onclick: () => pick(s),
        }, s.title, hitNote.has(s) ? h("small", {}, hitNote.get(s))
          : s.kana && norm(s.kana) !== norm(s.title) ? h("small", {}, s.kana) : null))
      : [h("li", { class: "empty" }, "見つかりません（このまま自由入力もできます）")]));
    list.hidden = false;
    songIn.setAttribute("aria-expanded", "true");
  };
  const search = () => {
    const q = norm(songIn.value);
    if (!q) { results = []; close(); return; }
    const songs = DB.songs[state.from] || [];
    const starts = [], contains = [], byUnit = [], byUnitPart = [], bySinger = [];
    hitNote = new Map();
    // ユニット名（よみでも可）：完全一致はそのユニットの曲を全部、2文字以上の部分一致でも出す（例：「すとれい」→ストレイライト）
    const unitMatch = (u) => {
      const a = norm(u), k = norm(DB.units[u]);
      if (a === q || k === q) return 2;
      return q.length >= 2 && (a.includes(q) || (k && k.includes(q))) ? 1 : 0;
    };
    for (const s of songs) {
      const a = norm(s.title), k = norm(s.kana);
      if (a.startsWith(q) || k.startsWith(q)) { starts.push(s); continue; }
      if (a.includes(q) || k.includes(q)) { contains.push(s); continue; }
      let best = 0, unit = "";
      for (const u of s.units || []) { const m = unitMatch(u); if (m > best) { best = m; unit = u; } }
      if (best) { (best === 2 ? byUnit : byUnitPart).push(s); hitNote.set(s, `ユニット：${unit}`); continue; }
      // 歌唱者名と完全一致（「春日 未来」のような空白の有無は区別しない）なら、その人の参加曲を全部出す
      const n = (s.singers || []).find((n) => norm(n) === q);
      if (n) { bySinger.push(s); hitNote.set(s, `歌：${n}`); }
    }
    results = starts.concat(contains).slice(0, 30).concat(byUnit, byUnitPart, bySinger);
    active = results.length ? 0 : -1;
    draw();
  };
  songIn.addEventListener("input", () => {
    if (performance.now() - pickedAt < 400) { songIn.value = it.title; return; } // 選曲直後の確定による入力は無視
    it.title = songIn.value; it.songId = null; it.url = ""; it.brand = state.from;
    if (it.jacketAuto) { it.jacket = ""; it.jacketAuto = false; it.jkPos = "auto"; }
    paintJacket(jacket, it, true);
    syncSongField();
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

  // --- 歌って欲しいアイドル
  const tags = h("div", { class: "tags" });
  const drawTags = () => {
    tags.replaceChildren(
      ...it.members.map((m, i) => {
        const c = memberColor(m);
        return h("span", { class: "tag" + (isLight(c) ? " light" : ""), style: { "--tag-bg": c, "--tag-ink": inkFor(c) } },
          m.name,
          h("button", {
            type: "button", "aria-label": `${m.name}を外す`,
            onclick: () => { it.members.splice(i, 1); drawTags(); save(); },
          }, "×"));
      }),
      h("button", { type: "button", class: "tag-add", onclick: () => openMembers(it, drawTags) }, "＋ アイドルを選ぶ"),
    );
  };
  drawTags();

  card.append(
    head, chips,
    h("div", { class: "card-body" },
      jacket,
      h("div", { class: "card-main" },
        songField,
        pitch,
        h("div", { class: "members" },
          h("div", { class: "members-label" }, "歌って欲しいアイドル"),
          tags),
      ),
    ),
  );
  return card;
}

const JK_WAIT = "楽曲を選ぶと自動で更新されます";
const JK_FAIL = "ジャケットの取得に失敗しました。自分でジャケットの設定ができます";
// ジャケット未設定の曲に出す画像（scripts/make_now_printing.py で作成）
const NOW_PRINTING = "assets/now_printing.png?v=3"; // 画像を作り直したら ?v= を変える

// ジャケットの表示位置。表と裏が横に並んだジャケットを正方形の中央で切ると背表紙が映るので、
// 横長（幅が高さの WIDE_RATIO 倍以上）の画像は表紙側を見せる。今のデータで横長なのはランティスの
// MTG01（表紙が左半分）と MTG11（左右とも同じ絵柄）なので、自動では左側にする。外れたらジャケット設定で選び直せる
const JK_POSITIONS = [["auto", "自動"], ["left", "左"], ["center", "中央"], ["right", "右"]];
const WIDE_RATIO = 1.6;
const ratioCache = new Map();
function imageRatio(url) {
  if (!url) return Promise.resolve(1);
  url = imgUrl(url);
  if (!ratioCache.has(url)) {
    ratioCache.set(url, new Promise((res) => {
      const img = new Image();
      img.referrerPolicy = "no-referrer";
      img.onload = () => res(img.naturalWidth / (img.naturalHeight || 1));
      img.onerror = () => res(1);
      img.src = url;
    }));
  }
  return ratioCache.get(url);
}

// 参照元（Referer）付きで読み込むと「This image was hotlinked」画像を返す配信元。
// index.html で参照元を送らない設定にしているが、Chrome は CSS の背景画像の読み込みには参照元を付けてしまう。
// そのためジャケットは CSS 背景ではなく <img referrerpolicy="no-referrer"> で表示する（setBg）。
// 一度でも差し替え画像を受け取ったブラウザは同じURLだとキャッシュの差し替え画像を出し続ける
// （配信元がキャッシュ期限を付けていないため長く残る）ので、配信元が無視するクエリを付けて別URLにする
const HOTLINK_HOSTS = new Set(["shinycolors.lantis.jp"]);
const HOTLINK_NR = "2"; // 以前の版（CSS 背景で表示）で「?nr=1」に差し替え画像がキャッシュされているので変更
const hotlinkFallback = new Map(); // 元URL → 差し替え画像を受け取ったときの代わりのURL（画像変換サービス経由）
function imgUrl(u) {
  if (!u || u.startsWith("data:")) return u;
  if (hotlinkFallback.has(u)) return hotlinkFallback.get(u);
  try {
    const x = new URL(u);
    if (HOTLINK_HOSTS.has(x.host) && !x.searchParams.has("nr")) { x.searchParams.set("nr", HOTLINK_NR); return x.href; }
  } catch {}
  return u;
}
// それでも差し替え画像（200×200）が返ってきたら（拡張機能などで参照元が送られている等）、
// 画像変換サービスに配信元から取ってきてもらう。サービス側は参照元を送らないので本物が返る
function isHotlinkPlaceholder(u, img) {
  try { return HOTLINK_HOSTS.has(new URL(u).host) && img.naturalWidth === 200 && img.naturalHeight === 200; }
  catch { return false; }
}
// 縦長のジャケット（Blu-ray サイズ・ボックス物など）は正方形に切らず、全体が入るように引きで表示する
const TALL_RATIO = 0.95;
const FIT_WHOLE = "contain"; // jacketPos が返す特別な値：切らずに全体を表示
async function jacketPos(url, pos) {
  if (pos && pos !== "auto") return `${pos} center`;
  const r = await imageRatio(url);
  if (r < TALL_RATIO) return FIT_WHOLE;
  return r >= WIDE_RATIO ? "left center" : "center";
}

// ジャケット枠の表示：画像 / 選曲待ち / 取得失敗（＝自分で設定してね）
// typing=true の間は入力途中なので失敗表示にしない
function paintJacket(el, it, typing = false) {
  const span = el.querySelector("span");
  const token = (el._tok = (el._tok || 0) + 1);
  const fail = () => {
    // 未設定・読み込み失敗は「NOW PRINTING...」画像を出し、上に「自分で設定できます」の案内を重ねる
    setBg(el, NOW_PRINTING);
    setBgPos(el, "");
    el.classList.add("is-failed");
    span.textContent = JK_FAIL;
  };
  el.classList.remove("is-failed");
  if (it.jacket) {
    setBg(el, it.jacket);
    setBgPos(el, "");
    jacketPos(it.jacket, it.jkPos).then((p) => { if (el._tok === token) setBgPos(el, p); });
    const img = new Image();
    img.referrerPolicy = "no-referrer";
    img.onerror = () => { if (el._tok === token) fail(); };
    img.onload = () => {
      if (!isHotlinkPlaceholder(it.jacket, img) || hotlinkFallback.has(it.jacket)) return;
      hotlinkFallback.set(it.jacket, IMG_PROXIES[0](it.jacket));
      if (el._tok === token) setBg(el, it.jacket);
    };
    img.src = imgUrl(it.jacket);
    return;
  }
  setBg(el, "");
  if (!typing && (it.songId || it.title.trim())) fail();
  else span.textContent = JK_WAIT;
}

// 枠にジャケット画像を表示する（CSS 背景だと参照元が送られてしまうので <img> を重ねる。見た目は cover と同じ）
function setBg(el, url) {
  let img = el.querySelector(":scope > img.jk-img");
  if (!url) {
    img?.remove();
    el.classList.remove("has-img");
    return;
  }
  if (!img) {
    img = document.createElement("img");
    img.className = "jk-img";
    img.alt = "";
    img.referrerPolicy = "no-referrer";
    img.decoding = "async";
    el.prepend(img);
  }
  const src = imgUrl(url);
  if (img.getAttribute("src") !== src) img.src = src;
  el.classList.add("has-img");
}
// 表示位置（object-position）。横長ジャケットの左寄せ・ユーザーの選び直しに使う。縦長は全体表示（contain）
function setBgPos(el, pos) {
  const img = el.querySelector(":scope > img.jk-img");
  if (!img) return;
  const whole = pos === FIT_WHOLE;
  img.style.objectFit = whole ? "contain" : "";
  img.style.objectPosition = whole ? "center" : pos || "";
}

// ---------------------------------------------------------------- member dialog

// 初期表示は「その曲のブランド」のアイドル。ブランドのタグで他ブランドにも切り替えられる
const memDlg = { item: null, onDone: null, brand: "", group: "" };

async function openMembers(item, onDone) {
  memDlg.item = item; memDlg.onDone = onDone;
  memDlg.brand = songBrand(item); memDlg.group = "";
  await withLoading(() => Promise.all(DB.brands.map((b) => ensureBrand(b.id))));
  $("#mem-brand").textContent = item.title ? `「${item.title}」` : "";
  $("#mem-search").value = "";
  $("#mem-custom-in").value = "";
  drawBrandChips();
  drawGroupChips();
  drawMemList();
  $("#dlg-members").showModal();
  if (matchMedia("(pointer:fine)").matches) $("#mem-search").focus();
}

// タグの選択肢：各ブランド + イベント（デレミリ対バンなど、出演者で絞り込む）
// memDlg.brand は ブランドID か "event:<イベントID>"
const EVENT_PREFIX = "event:";
const isEventTab = (v) => v.startsWith(EVENT_PREFIX);
const ALL_COLOR = "#57525f"; // 「全員」タグ（ブランドをまたぐもの）の色
const eventOf = (v) => DB.events.find((e) => EVENT_PREFIX + e.id === v);
// イベント内のブランドの並び順＝ events.json に最初に出てくる順（デレミリ：デレ→ミリオン、エムシャニ：SideM→シャニマス）
const eventBrandRank = (ev) => {
  const order = [...new Set(ev.days.flatMap((d) => d.members.map((m) => m.brand)))];
  return (b) => { const k = order.indexOf(b); return k < 0 ? order.length : k; };
};

function drawBrandChips() {
  const box = $("#mem-brands");
  const pick = (v) => { memDlg.brand = v; memDlg.group = ""; drawBrandChips(); drawGroupChips(); drawMemList(); };
  box.replaceChildren(
    ...DB.brands.map((b) => {
      const on = b.id === memDlg.brand;
      return h("button", {
        type: "button", class: "chip brand-chip" + (on ? " on" : ""), "aria-pressed": String(on),
        style: on ? { background: b.color, borderColor: b.color, color: b.ink } : { borderColor: b.color },
        onclick: () => pick(b.id),
      }, b.short);
    }),
    ...DB.events.map((e) => {
      const v = EVENT_PREFIX + e.id, on = v === memDlg.brand;
      return h("button", {
        type: "button", class: "chip event-chip" + (on ? " on" : ""), "aria-pressed": String(on),
        title: e.title, onclick: () => pick(v),
      }, e.name);
    }),
  );
  scrollChipIntoView(box);
}

// スマホではタグが横スクロールの1行になるので、選択中のタグが見える位置までずらす
function scrollChipIntoView(box) {
  const on = box.querySelector(".chip.on");
  if (!on || box.scrollWidth <= box.clientWidth) return;
  const left = on.offsetLeft - box.offsetLeft;
  if (left < box.scrollLeft || left + on.offsetWidth > box.scrollLeft + box.clientWidth) box.scrollLeft = Math.max(0, left - 24);
}

// いま表示する候補（ブランドならそのアイドル、イベントなら出演日ごとの出演者）
function memberPool() {
  const ev = eventOf(memDlg.brand);
  if (!ev) {
    const b = memDlg.brand;
    return (DB.idols[b] || []).map((i) => ({ ...i, brand: b, groups: i.group ? [i.group] : [] }));
  }
  const pool = new Map();
  for (const d of ev.days) {
    for (const m of d.members) {
      const key = m.brand + ":" + m.name;
      if (!pool.has(key)) {
        const i = (DB.idols[m.brand] || []).find((x) => x.name === m.name) || { name: m.name, kana: "", cv: "", color: "" };
        pool.set(key, { ...i, brand: m.brand, groups: [] });
      }
      pool.get(key).groups.push(d.id);
    }
  }
  // 並び順：イベントのブランド順（対バンの出演日をまたいでも、ブランドごとにまとまる）
  const rank = eventBrandRank(ev);
  return [...pool.values()].sort((a, b) => rank(a.brand) - rank(b.brand)); // sort は安定ソート
}

function groupOptions() {
  const ev = eventOf(memDlg.brand);
  if (ev) return ev.days.map((d) => ({ key: d.id, label: d.label }));
  const groups = [...new Set((DB.idols[memDlg.brand] || []).map((i) => i.group).filter(Boolean))];
  return groups.length > 1 ? groups.map((g) => ({ key: g, label: g })) : [];
}

function drawGroupChips() {
  const opts = groupOptions();
  const gbox = $("#mem-groups");
  gbox.replaceChildren(...(opts.length
    ? [{ key: "", label: "すべて" }, ...opts].map((o) => h("button", {
        type: "button", class: "chip" + (o.key === memDlg.group ? " on" : ""), "data-g": o.key,
        onclick: () => { memDlg.group = o.key; gbox.querySelectorAll(".chip").forEach((c) => c.classList.toggle("on", c.dataset.g === o.key)); drawMemList(); },
      }, o.label))
    : []));
  gbox.scrollLeft = 0;
  scrollChipIntoView(gbox);
}

// 「○○全員」タグ：個別のアイドルを選ばず、まとめて1つのタグとして追加する
function allRows() {
  const ev = eventOf(memDlg.brand);
  if (!ev) {
    if (memDlg.group) return [];
    const b = brand(memDlg.brand);
    return [{ label: `${b.short}全員`, brand: b.id, color: b.color }];
  }
  const rows = [];
  const rank = eventBrandRank(ev);
  for (const d of ev.days) {
    if (memDlg.group && memDlg.group !== d.id) continue;
    const day = d.label.split(/\s/)[0]; // "Day1 2/27(土)" → "Day1"
    rows.push({ label: `${day}全員`, brand: "", color: ALL_COLOR });
    const ids = [...new Set(d.members.map((m) => m.brand))].sort((a, b) => rank(a) - rank(b));
    for (const id of ids) rows.push({ label: `${day}${brand(id).short}全員`, brand: id, color: brand(id).color });
  }
  return rows;
}

function toggleMember(m) {
  const it = memDlg.item;
  const k = it.members.findIndex((x) => x.name === m.name);
  if (k >= 0) it.members.splice(k, 1); else it.members.push(m);
  drawMemList(); memDlg.onDone?.(); save();
}

function drawMemList() {
  const it = memDlg.item;
  const showBrand = isEventTab(memDlg.brand); // イベントでは両ブランドが混ざるのでブランド名も出す
  const q = norm($("#mem-search").value);
  const idols = memberPool().filter((i) =>
    (!memDlg.group || i.groups.includes(memDlg.group)) &&
    (!q || norm(i.name).includes(q) || norm(i.kana).includes(q) || norm(i.cv).includes(q)));
  const chosen = new Set(it.members.map((m) => m.name));
  // 「全員」は1行にまとめた小さめのボタンにする（全幅の行が並ぶと、スマホでアイドル一覧が画面外に押し出されるため）
  const allBtns = allRows().filter((r) => !q || norm(r.label).includes(q)).map((r) => h("button", {
    type: "button", class: "mem-all" + (chosen.has(r.label) ? " on" : ""), "aria-pressed": String(chosen.has(r.label)),
    onclick: () => toggleMember({ name: r.label, color: r.color, brand: r.brand, all: true }),
  }, h("span", { class: "dot", style: { "--c": r.color } }), r.label));
  const alls = allBtns.length
    ? [h("div", { class: "mem-alls" }, h("span", { class: "mem-alls-label" }, "まとめて1タグで追加"), ...allBtns)]
    : [];
  $("#mem-list").replaceChildren(...alls, ...idols.map((i) => {
    const b = brand(i.brand);
    // CV はふだん出さない。CV で検索して見つかった人（名前・よみでは当たらない人）にだけ、理由が分かるよう出す
    const byCv = q && i.cv && norm(i.cv).includes(q) && !norm(i.name).includes(q) && !norm(i.kana).includes(q);
    const sub = [showBrand ? b.short : "", byCv ? `CV.${i.cv}` : ""].filter(Boolean).join(" / ");
    return h("button", {
      type: "button", class: "mem-item" + (chosen.has(i.name) ? " on" : ""), "aria-pressed": String(chosen.has(i.name)),
      onclick: () => {
        const k = it.members.findIndex((m) => m.name === i.name);
        if (k >= 0) it.members.splice(k, 1);
        else it.members.push({ name: i.name, color: i.color || "", brand: b.id });
        drawMemList(); memDlg.onDone?.(); save();
      },
    }, h("span", { class: "dot", style: { "--c": i.color || b.color } }),
       h("span", {}, i.name, sub ? h("small", {}, sub) : null));
  }));
  $("#mem-count").textContent = `${it.members.length}人選択中`;
}

function addCustomMember() {
  const inp = $("#mem-custom-in");
  const name = inp.value.trim();
  if (!name || !memDlg.item) return;
  const b = isEventTab(memDlg.brand) ? songBrand(memDlg.item) : memDlg.brand;
  if (!memDlg.item.members.some((m) => m.name === name)) memDlg.item.members.push({ name, color: "", brand: b });
  inp.value = "";
  drawMemList(); memDlg.onDone?.(); save();
}

// ---------------------------------------------------------------- jacket dialog

const jkDlg = { item: null, value: "", pos: "auto" };

function openJacket(item) {
  jkDlg.item = item; jkDlg.value = item.jacket || ""; jkDlg.pos = item.jkPos || "auto";
  $("#jk-url").value = jkDlg.value.startsWith("data:") ? "" : jkDlg.value;
  paintJkPreview();
  $("#dlg-jacket").showModal();
}

// プレビューと「表示する位置」ボタン（画像があるときだけ出す）
function paintJkPreview() {
  const pv = $("#jk-preview");
  setBg(pv, jkDlg.value);
  setBgPos(pv, "");
  const v = jkDlg.value, pos = jkDlg.pos;
  if (v) jacketPos(v, pos).then((p) => { if (jkDlg.value === v && jkDlg.pos === pos) setBgPos(pv, p); });
  const box = $("#jk-pos");
  box.hidden = !v;
  box.querySelector(".jk-pos-btns").replaceChildren(...JK_POSITIONS.map(([id, label]) => h("button", {
    type: "button", class: "chip" + (id === pos ? " on" : ""), "aria-pressed": String(id === pos),
    onclick: () => { jkDlg.pos = id; paintJkPreview(); },
  }, label)));
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
  u = imgUrl(u);
  try { return await fetchImage(u); } catch {}
  for (const proxy of IMG_PROXIES) {
    try { return await fetchImage(proxy(u), 20000); } catch {}
  }
  return null;
}

// 画像に入れるカード（何か入力のあるもの）
const exportItems = () => state.items.filter((it) => it.title || it.pitch || it.members.length || it.jacket);

// 1枚の画像。items は exportItems() の一部、start はその最初のカードの通し番号（0始まり）、
// page / pages は「何枚目／全何枚」（1枚だけのときは出さない）
function buildSheet(items, jackets, start = 0, page = 1, pages = 1) {
  const f = brand(state.from);
  const bg = `linear-gradient(160deg, ${tint(f.color, 0.26)} 0%, #fbf8f3 34%, #fbf8f3 66%, ${tint(f.color, 0.18)} 100%)`;
  return h("div", { class: "x-sheet", style: { backgroundImage: bg } },
    h("div", { class: "x-head" },
      h("div", { class: "x-name" }, state.name.trim() || DEFAULT_NAME),
      h("div", { class: "x-sub" },
        h("span", { class: "x-pill", style: { background: f.color, color: f.ink } }, f.name),
        h("span", {}, "のおすすめ曲")),
      pages > 1 ? h("div", { class: "x-page", style: { background: f.color, color: f.ink } }, `${page} / ${pages}`) : null,
    ),
    h("div", { class: "x-items" }, items.map((it, j) => {
      const i = start + j;
      const jk = jackets.get(it.id);
      return h("div", { class: "x-card" },
        h("div", { class: "x-theme", style: { background: tint(f.color, 0.2), borderBottom: `3px solid ${tint(f.color, 0.45)}` } },
          h("span", { class: "x-no", style: { background: f.color, color: f.ink } }, String(i + 1)),
          h("span", {}, it.theme.trim() || "オススメ曲")),
        h("div", { class: "x-body" },
          h("div", { class: "x-jacket", style: jk.src ? { backgroundImage: `url("${jk.src}")`,
            ...(jk.pos === FIT_WHOLE ? { backgroundSize: "contain", backgroundPosition: "center" } : { backgroundPosition: jk.pos }) } : {} }, jk.src ? "" : "NO IMAGE"),
          h("div", { class: "x-main" },
            h("div", { class: "x-title" }, it.title.trim() || "（曲名未入力）"),
            h("div", { class: "x-pitch" }, it.pitch.trim()),
            it.members.length ? h("div", { class: "x-mem-label" }, "歌って欲しいアイドル") : null,
            it.members.length ? h("div", { class: "x-tags" }, it.members.map((m) => {
              const c = memberColor(m);
              // 白に近い色は縁取り（html2canvas が確実に描ける border で付ける）
              const edge = isLight(c) ? { border: "2px solid rgba(0,0,0,.18)", padding: "3px 14px 5px" } : {};
              return h("span", { class: "x-tag", style: { background: c, color: inkFor(c), ...edge } }, m.name);
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

// 1枚の画像に入れる曲数。これより多いときは複数枚に分ける
const SONGS_PER_IMAGE = 4;

let lastExport = []; // [{ blob, url, name }]

async function exportImage() {
  if (!state.items.some((it) => it.title || it.pitch)) { toast("曲名かプレゼン内容を入力してください"); return; }
  if (typeof html2canvas !== "function") { toast("画像ライブラリを読み込めませんでした。通信状態を確認してください"); return; }
  $("#loading").hidden = false;
  try {
    const jackets = new Map();
    let failed = 0;
    let nowPrinting; // ジャケットが無い・読めない曲は「NOW PRINTING...」画像にする（1回だけ読み込む）
    const placeholder = () => (nowPrinting ??= resolveJacket(new URL(NOW_PRINTING, location.href).href).then((d) => d || ""));
    await Promise.all(state.items.map(async (it) => {
      const [d, pos] = await Promise.all([resolveJacket(it.jacket), it.jacket ? jacketPos(it.jacket, it.jkPos) : "center"]);
      if (d === null) failed++;
      jackets.set(it.id, d ? { src: d, pos } : { src: await placeholder(), pos: "center" });
    }));
    await document.fonts.ready;
    const stage = $("#export-stage");
    const items = exportItems();

    // 上から順に SONGS_PER_IMAGE 曲ずつ1枚にする
    const chunks = [];
    for (let k = 0; k < items.length; k += SONGS_PER_IMAGE) chunks.push(items.slice(k, k + SONGS_PER_IMAGE));

    const blobs = [];
    let start = 0;
    for (const [k, chunk] of chunks.entries()) {
      const sheet = buildSheet(chunk, jackets, start, k + 1, chunks.length);
      start += chunk.length;
      stage.replaceChildren(sheet);
      // レイアウト確定待ち（requestAnimationFrame は裏タブで止まるのでタイマーで待つ）
      await new Promise((r) => setTimeout(r, 60));
      // iPhone(Safari) は1枚のキャンバスが約1,677万画素を超えると描画できないので、
      // 長いカードで上限を超えるときは解像度を自動で下げる（通常は2倍、最低0.5倍）
      const MAX_PIXELS = 16_000_000, MAX_SIDE = 16_000;
      const w = sheet.offsetWidth, ht = sheet.offsetHeight;
      const scale = Math.max(0.5, Math.min(2, Math.sqrt(MAX_PIXELS / (w * ht)), MAX_SIDE / ht));
      const canvas = await html2canvas(sheet, { scale, backgroundColor: "#fbf8f3", logging: false, useCORS: true });
      const blob = await new Promise((r) => canvas.toBlob(r, "image/png"));
      if (!blob) throw new Error("toBlob failed");
      blobs.push(blob);
    }
    stage.replaceChildren();

    for (const e of lastExport) URL.revokeObjectURL(e.url);
    lastExport = blobs.map((blob, k) => ({ blob, url: URL.createObjectURL(blob), name: fileName(k + 1, blobs.length) }));
    renderExportImages();
    const notes = [];
    if (lastExport.length > 1) notes.push(`${items.length}曲を${lastExport.length}枚に分けました（1枚あたり${SONGS_PER_IMAGE}曲）。` +
      (lastExport.length > 4 ? "X は1回の投稿に4枚まで添付できるので、5枚目以降はリプライなどで続けて投稿してください。" : ""));
    if (failed) notes.push(`ジャケット ${failed} 件は配信元の制限で読み込めず「NOW PRINTING」画像になりました。端末に保存した画像を選ぶと確実です。`);
    $("#ex-note").textContent = notes.join(" ");
    $("#ex-share").hidden = !canShareFile();
    $("#ex-save").textContent = lastExport.length > 1 ? `${lastExport.length}枚まとめて保存` : "画像を保存";
    $("#ex-copy").hidden = lastExport.length > 1; // クリップボードは1枚しか入らないので、複数枚のときは各画像の下のボタンでコピー
    $("#dlg-export").showModal();
  } catch (e) {
    console.error(e);
    toast("画像の作成に失敗しました");
  } finally {
    $("#loading").hidden = true;
  }
}

const fileName = (k = 1, n = 1) => `imas-presen-${state.from}${n > 1 ? `-${k}` : ""}.png`;
// 投稿文はハッシュタグだけ（内容は画像で伝える。サイトのURLは画像の下部に入っている）
const shareText = () => HASHTAG;

// 出力画面に画像を並べる。複数枚のときは各画像に「何枚目」と、その画像だけの保存・コピーボタンを付ける
function renderExportImages() {
  const many = lastExport.length > 1;
  $("#ex-imgs").replaceChildren(...lastExport.map((e, k) => h("figure", { class: "ex-fig" },
    many ? h("figcaption", {}, `${k + 1} / ${lastExport.length} 枚目`) : null,
    h("img", { src: e.url, alt: `出力したプレゼンシート${many ? `（${k + 1}枚目）` : ""}` }),
    many ? h("div", { class: "ex-fig-actions" },
      h("button", { type: "button", class: "btn small", onclick: () => download(k) }, "この画像を保存"),
      h("button", { type: "button", class: "btn small", onclick: () => copyImage(k) }, "この画像をコピー")) : null,
  )));
}

function canShareFile() {
  try {
    return !!navigator.canShare && navigator.canShare({ files: [new File([""], "a.png", { type: "image/png" })] });
  } catch { return false; }
}
// k を省くと全部保存（複数枚のときは少し間を空けて順に保存する。ブラウザによっては複数ダウンロードの許可を聞かれる）
async function download(k) {
  const list = k == null ? lastExport : [lastExport[k]];
  for (const [i, e] of list.entries()) {
    if (i) await new Promise((r) => setTimeout(r, 400));
    const a = h("a", { href: e.url, download: e.name });
    document.body.append(a); a.click(); a.remove();
  }
}
async function copyImage(k = 0) {
  try {
    await navigator.clipboard.write([new ClipboardItem({ "image/png": lastExport[k].blob })]);
    toast(lastExport.length > 1 ? `${k + 1}枚目の画像をコピーしました` : "画像をコピーしました");
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
    rz = setTimeout(() => document.querySelectorAll(".pitch, .theme-input").forEach(autosize), 150);
  });

  $("#mem-search").addEventListener("input", drawMemList);
  $("#mem-custom-add").onclick = addCustomMember;
  $("#mem-custom-in").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); addCustomMember(); } });
  $("#mem-search").addEventListener("keydown", (e) => { if (e.key === "Enter") e.preventDefault(); });

  $("#jk-url").addEventListener("input", () => {
    jkDlg.value = $("#jk-url").value.trim();
    jkDlg.pos = "auto";
    paintJkPreview();
  });
  $("#jk-file").addEventListener("change", async (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (!f) return;
    try {
      jkDlg.value = await fileToDataURL(f);
      jkDlg.pos = "auto";
      $("#jk-url").value = "";
      paintJkPreview();
    } catch { toast("画像を読み込めませんでした"); }
  });
  $("#jk-clear").onclick = () => { jkDlg.value = ""; jkDlg.pos = "auto"; $("#jk-url").value = ""; paintJkPreview(); };
  // 「決定」で反映（dialog の close イベントには頼らない）
  const applyJacket = () => {
    if (!jkDlg.item) return;
    const v = jkDlg.value;
    if (v && !v.startsWith("data:") && !/^https?:\/\//i.test(v)) { toast("http(s) で始まる画像URLを入力してください"); return; }
    // 表示位置だけ変えた場合は、自動で入ったジャケットのまま（選曲し直したら差し替わる）にする
    if (v !== jkDlg.item.jacket) {
      jkDlg.item.jacket = v;
      jkDlg.item.jacketAuto = false; // 自分で設定したものは選曲し直しても消さない
    }
    jkDlg.item.jkPos = jkDlg.pos;
    const el = document.querySelector(`.card[data-id="${jkDlg.item.id}"] .jacket`);
    if (el) paintJacket(el, jkDlg.item);
    save();
    $("#dlg-jacket").close();
  };
  $("#jk-ok").addEventListener("click", (e) => { e.preventDefault(); applyJacket(); });
  $("#jk-url").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); applyJacket(); } });
  $("#jk-close").addEventListener("click", (e) => { e.preventDefault(); $("#dlg-jacket").close(); });

  $("#ex-close").onclick = () => $("#dlg-export").close();
  $("#ex-save").onclick = () => download();
  $("#ex-copy").onclick = () => copyImage(0);
  $("#ex-share").onclick = async () => {
    try {
      await navigator.share({ files: lastExport.map((e) => new File([e.blob], e.name, { type: "image/png" })), text: shareText() });
    } catch (e) { if (e?.name !== "AbortError") toast("共有できませんでした"); }
  };
  $("#ex-x").onclick = async () => {
    // 1枚なら（PC は）コピーして貼り付け。複数枚はクリップボードに入らないので保存して添付してもらう
    const one = lastExport.length === 1;
    const copied = one && matchMedia("(pointer:fine)").matches ? await copyImage(0) : false;
    if (!copied) await download();
    window.open(`https://x.com/intent/post?text=${encodeURIComponent(shareText())}`, "_blank", "noopener,noreferrer");
    toast(copied ? "画像をコピーしました。ポスト画面に貼り付けてください"
      : one ? "画像を保存しました。ポストに添付してください"
      : `画像を${lastExport.length}枚保存しました。ポストに添付してください（1回の投稿は4枚まで）`, 5000);
  };
}

async function init() {
  [DB.brands, DB.themes, DB.jackets, DB.meta, DB.events, DB.units] = await Promise.all([
    getJSON("data/brands.json"),
    getJSON("data/themes.json").catch(() => []),
    getJSON("data/jackets.json").catch(() => ({})),
    getJSON("data/meta.json").catch(() => ({})),
    getJSON("data/events.json").catch(() => []),
    getJSON("data/units.json").catch(() => ({})),
  ]);
  state = loadState() || defaultState();
  const pk = pickableBrands();
  if (!pk.some((b) => b.id === state.from)) state.from = pk[0].id;
  if (DB.meta.updated_at) $("#data-date").textContent = ` / データ更新 ${DB.meta.updated_at}`;
  wire();
  renderHead();
  await onBrandChange();
}

// 起動中の「読み込み中…」を外して画面を出す（ブランド色を塗り終えてから。失敗時もエラー文を見せるため外す）
const finishBoot = () => document.documentElement.classList.remove("booting");

init().then(finishBoot).catch((e) => {
  console.error(e);
  document.querySelector("#items").textContent = "データの読み込みに失敗しました。ページを再読み込みしてください。";
  finishBoot();
});
