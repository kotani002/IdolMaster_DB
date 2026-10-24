// トップページ: 作品切り替え + タグ絞り込み + 全体検索
(async function () {
  let costumes, seriesList;
  try {
    [costumes, seriesList] = await Promise.all([loadCostumes(), loadSeries()]);
  } catch (e) {
    showError(e.message + "(ローカルで開く場合は簡易サーバー経由で表示してください)");
    return;
  }

  const seriesMap = new Map(seriesList.map((s) => [s.id, s]));
  const seriesBox = document.getElementById("series");
  const chipBox = document.getElementById("chips");
  const grid = document.getElementById("grid");
  const countEl = document.getElementById("count");
  const searchEl = document.getElementById("search");
  const clearBtn = document.getElementById("clear");

  const selected = new Set();
  let series = "all"; // "all" = 全作品を横断
  let lastCount = null;

  // URL ?series=gakumas&tags=a,b&q=xxx から初期状態を復元
  const params = new URLSearchParams(location.search);
  if (seriesMap.has(params.get("series"))) series = params.get("series");
  for (const t of (params.get("tags") || "").split(",").filter(Boolean)) selected.add(t);
  searchEl.value = params.get("q") || "";

  const inScope = (c) => series === "all" || c.series === series;
  const scoped = () => costumes.filter(inScope);

  function tagCountsOf(list) {
    const m = new Map();
    for (const c of list) for (const t of c.tags || []) m.set(t, (m.get(t) || 0) + 1);
    return m;
  }

  function syncUrl() {
    const p = new URLSearchParams();
    if (series !== "all") p.set("series", series);
    if (selected.size) p.set("tags", [...selected].join(","));
    if (searchEl.value.trim()) p.set("q", searchEl.value.trim());
    const qs = p.toString();
    history.replaceState(null, "", qs ? "?" + qs : location.pathname);
  }

  // ---- 作品切り替えアイコン ----
  function renderSeries() {
    const items = [{ id: "all", name: "すべての作品", short: "すべて", mark: "ALL", color: "#7a6a86", count: costumes.length }];
    for (const s of seriesList) items.push({ ...s, count: costumes.filter((c) => c.series === s.id).length });

    seriesBox.replaceChildren(
      ...items.map((s) => {
        const b = el("button", {
          class: "s-btn", type: "button", title: s.name, "aria-pressed": String(series === s.id),
        }, [
          seriesBadge(s, 40),
          el("span", { class: "s-label" }, [
            el("span", { class: "s-name", text: s.short }),
            el("span", { class: "s-count", text: s.count + "件" }),
          ]),
        ]);
        b.addEventListener("click", () => {
          if (series === s.id) return;
          series = s.id;
          // 切り替え先に存在しないタグは外す
          const valid = tagCountsOf(scoped());
          for (const t of [...selected]) if (!valid.has(t)) selected.delete(t);
          update();
        });
        return b;
      })
    );
  }

  // ---- タグ(現在の作品の範囲だけ) ----
  function renderChips() {
    const counts = tagCountsOf(scoped());
    const tags = [...counts.keys()].sort((a, b) => a.localeCompare(b, "ja"));
    chipBox.replaceChildren(
      ...tags.map((t) => {
        const b = el("button", { class: "chip", type: "button", "aria-pressed": String(selected.has(t)) }, [
          t,
          el("span", { class: "n", text: String(counts.get(t)) }),
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
    if (!inScope(c)) return false;
    // 選択タグをすべて含む衣装だけ表示(AND検索)
    for (const t of selected) if (!(c.tags || []).includes(t)) return false;
    const q = searchEl.value.trim().toLowerCase();
    if (!q) return true;
    const s = seriesMap.get(c.series);
    const hay = [
      c.name, s ? s.name : "", s ? s.short : "",
      ...(c.idols || []), ...(c.lives || []), ...(c.songs || []), ...(c.tags || []),
    ].join(" ").toLowerCase();
    return q.split(/\s+/).every((w) => hay.includes(w)); // スペース区切りはAND
  }

  function renderGrid() {
    const list = costumes.filter(matches);
    const total = scoped().length;
    countEl.textContent = list.length + " 件 / " + total + " 件";
    if (lastCount !== null && lastCount !== list.length) {
      countEl.classList.remove("bump");
      void countEl.offsetWidth; // アニメーションを再始動
      countEl.classList.add("bump");
    }
    lastCount = list.length;

    if (!list.length) {
      const msg = total === 0 ? "この作品のデータは準備中です" : "条件に合う衣装がありません";
      grid.replaceChildren(el("p", { class: "empty", text: msg }));
      return;
    }
    grid.replaceChildren(
      ...list.map((c, i) => {
        const s = seriesMap.get(c.series);
        return el("a", { class: "card", style: "--i:" + Math.min(i, 14), href: "costume.html?id=" + encodeURIComponent(c.id) }, [
          el("img", { src: c.image || "images/placeholder.svg", alt: c.name, loading: "lazy" }),
          el("div", { class: "body" }, [
            el("p", { class: "name", text: c.name }),
            el("p", { class: "meta" }, [
              s && series === "all" ? seriesBadge(s, 18) : "",
              (s && series === "all" ? " " + s.short + " " : "") + (c.firstAppearance ? "初登場: " + c.firstAppearance : ""),
            ]),
            el("div", { class: "tags" }, (c.tags || []).map((t) => el("span", { class: "tag", text: t }))),
          ]),
        ]);
      })
    );
  }

  function update() {
    renderSeries();
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

  // 初期状態に存在しないタグがURLに含まれていたら外す
  const valid = tagCountsOf(scoped());
  for (const t of [...selected]) if (!valid.has(t)) selected.delete(t);

  update();
})();
