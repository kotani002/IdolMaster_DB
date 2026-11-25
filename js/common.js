// 共通処理: データ読み込みと小さなDOMヘルパー
const COSTUMES_URL = "data/costumes.json";

async function loadCostumes() {
  const res = await fetch(COSTUMES_URL);
  if (!res.ok) throw new Error("衣装データを読み込めませんでした: " + res.status);
  return res.json();
}

// 作品(シリーズ)定義。衣装データの series に id を書く
async function loadSeries() {
  const res = await fetch("data/series.json");
  if (!res.ok) throw new Error("作品データを読み込めませんでした: " + res.status);
  return res.json();
}

async function loadTagMeta() {
  try {
    const res = await fetch("data/tags.json");
    return res.ok ? await res.json() : {};
  } catch (e) {
    return {};
  }
}

function tagIcon(name, meta) {
  const icon = meta && meta[name] && meta[name].icon;
  return icon && /^[\w./' -]+$/.test(icon)
    ? el("img", { class: "tag-icon", src: icon, alt: "", "aria-hidden": "true", loading: "lazy" })
    : "";
}

function setTagStyle(node, meta) {
  if (!meta) return;
  if (typeof meta.color === "string" && /^#[\da-f]{6}$/i.test(meta.color)) {
    node.style.setProperty("--tag-color", meta.color);
  }
  if (typeof meta.textColor === "string" && /^#[\da-f]{6}$/i.test(meta.textColor)) {
    node.style.setProperty("--tag-text-color", meta.textColor);
  }
}

// 作品アイコン。画像指定がなければ文字バッジを表示
function seriesBadge(s, size) {
  const b = s.icon
    ? el("img", { class: "s-badge", src: s.icon, alt: "", "aria-hidden": "true" })
    : el("span", { class: "s-badge", "aria-hidden": "true", text: s.mark });
  if (!s.icon) b.style.background = s.color;
  if (size) b.style.setProperty("--size", size + "px");
  return b;
}

// 着用者ごとの任意設定(アイコン・タグ色)。data/wearers.json が無くても動く
//   { "花海咲季": { "icon": "images/wearers/saki.png", "color": "#e8505b", "textColor": "#ffffff" } }
async function loadWearerMeta() {
  try {
    const res = await fetch("data/wearers.json");
    return res.ok ? await res.json() : {};
  } catch (e) {
    return {};
  }
}

// 着用者アイコン: 画像があればそれを、なければ頭文字の丸バッジ(色は名前から自動)
function wearerIcon(name, meta) {
  const m = (meta && meta[name]) || {};
  if (m.icon && /^[\w./' -]+$/.test(m.icon)) {
    return el("img", { class: "w-icon", src: m.icon, alt: "", loading: "lazy" });
  }
  let h = 0;
  for (const ch of name) h = (h * 31 + ch.codePointAt(0)) % 360;
  const b = el("span", { class: "w-icon", "aria-hidden": "true", text: [...name][0] || "?" });
  b.style.background = m.color || "hsl(" + h + " 55% 48%)";
  return b;
}

function el(tag, props = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") node.className = v;
    else if (k === "text") node.textContent = v;
    else node.setAttribute(k, v);
  }
  for (const c of [].concat(children)) {
    node.append(c instanceof Node ? c : document.createTextNode(c));
  }
  return node;
}

function showError(message) {
  const target = document.getElementById("app") || document.body;
  target.replaceChildren(el("p", { class: "empty", text: message }));
}
