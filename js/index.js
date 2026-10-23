// トップページ: 一覧表示とタグ絞り込み
(async function () {
  let costumes;
  try {
    costumes = await loadCostumes();
  } catch (e) {
    showError(e.message + "(ローカルで開く場合は簡易サーバー経由で表示してください)");
    return;
  }

  const selected = new Set();
  const chipBox = document.getElementById("chips");
  const grid = document.getElementById("grid");
  const countEl = document.getElementById("count");
  const searchEl = document.getElementById("search");
  const clearBtn = document.getElementById("clear");
  let rendered = false; // 初回表示のあとは登場アニメーションを付けない

  // タグ一覧(出現数つき)
  const tagCounts = new Map();
  for (const c of costumes) for (const t of c.tags || []) tagCounts.set(t, (tagCounts.get(t) || 0) + 1);
  const allTags = [...tagCounts.keys()].sort((a, b) => a.localeCompare(b, "ja"));

  // URLの ?tags=a,b から初期状態を復元
  const params = new URLSearchParams(location.search);
  for (const t of (params.get("tags") || "").split(",").filter(Boolean)) {
    if (tagCounts.has(t)) selected.add(t);
  }
  searchEl.value = params.get("q") || "";

  function syncUrl() {
    const p = new URLSearchParams();
    if (selected.size) p.set("tags", [...selected].join(","));
    if (searchEl.value.trim()) p.set("q", searchEl.value.trim());
    const qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }

  function renderChips() {
    chipBox.replaceChildren(
      ...allTags.map((t) => {
        const b = el("button", { class: "chip", type: "button", "aria-pressed": String(selected.has(t)) }, [
          t,
          el("span", { class: "n", text: String(tagCounts.get(t)) }),
        ]);
        b.addEventListener("click", () => {
          selected.has(t) ? selected.delete(t) : selected.add(t);
          update();
        });
        return b;
      })
    );
  }

  function matches(c) {
    // 選択タグをすべて含む衣装だけ表示(AND検索)
    for (const t of selected) if (!(c.tags || []).includes(t)) return false;
    const q = searchEl.value.trim().toLowerCase();
    if (!q) return true;
    const hay = [c.name, ...(c.idols || []), ...(c.lives || []), ...(c.tags || [])].join(" ").toLowerCase();
    return hay.includes(q);
  }

  function renderGrid() {
    const list = costumes.filter(matches);
    countEl.textContent = list.length + " 件 / 全 " + costumes.length + " 件";
    grid.classList.toggle("static", rendered);
    rendered = true;
    if (!list.length) {
      grid.replaceChildren(el("p", { class: "empty", text: "条件に合う衣装がありません" }));
      return;
    }
    grid.replaceChildren(
      ...list.map((c, i) =>
        el("a", { class: "card", style: "--i:" + Math.min(i, 14), href: "costume.html?id=" + encodeURIComponent(c.id) }, [
          el("img", { src: c.image || "images/placeholder.svg", alt: c.name, loading: "lazy" }),
          el("div", { class: "body" }, [
            el("p", { class: "name", text: c.name }),
            el("p", { class: "meta", text: c.firstAppearance ? "初登場: " + c.firstAppearance : "" }),
            el("div", { class: "tags" }, (c.tags || []).map((t) => el("span", { class: "tag", text: t }))),
          ]),
        ])
      )
    );
  }

  function update() {
    renderChips();
    renderGrid();
    syncUrl();
  }

  searchEl.addEventListener("input", update);
  clearBtn.addEventListener("click", () => {
    selected.clear();
    searchEl.value = "";
    update();
  });

  update();
})();
