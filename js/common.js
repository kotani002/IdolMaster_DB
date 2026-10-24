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

// 作品アイコン(オリジナルの丸バッジ。公式ロゴではありません)
function seriesBadge(s, size) {
  const b = el("span", { class: "s-badge", "aria-hidden": "true", text: s.mark });
  b.style.background = s.color;
  if (size) b.style.setProperty("--size", size + "px");
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
