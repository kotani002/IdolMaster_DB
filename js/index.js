// トップページ: 作品切り替え + タグ絞り込み + 着用者絞り込み + 全体検索
(async function () {
  let costumes, seriesList, wearerMeta, tagMeta;
  try {
    [costumes, seriesList, wearerMeta, tagMeta] = await Promise.all([
      loadCostumes(), loadSeries(), loadWearerMeta(), loadTagMeta(),
    ]);
  } catch (e) {
    showError(e.message + "(ローカルで開く場合は簡易サーバー経由で表示してください)");
    return;
  }

  const seriesMap = new Map(seriesList.map((s) => [s.id, s]));
  const seriesBox = document.getElementById("series");
  const chipBox = document.getElementById("chips");
  const wearerBox = document.getElementById("wearers");
  const grid = document.getElementById("grid");
  const countEl = document.getElementById("count");
  const searchEl = document.getElementById("search");
  const clearBtn = document.getElementById("clear");

  const selected = new Set();   // タグ(AND)
  const selectedW = new Set();  // 着用者(OR)
  const selectedUnits = new Set(); // ユニット(OR)
  const unitNames = new Set(Object.keys(tagMeta).filter((name) => tagMeta[name].type === "unit"));
  let series = "all"; // "all" = 全作品を横断
  let lastCount = null;

  // URL ?series=gakumas&tags=a,b&wearers=x,y&units=u,v&q=xxx から初期状態を復元
  const params = new URLSearchParams(location.search);
  if (seriesMap.has(params.get("series"))) series = params.get("series");
  for (const t of (params.get("tags") || "").split(",").filter(Boolean)) {
    if (unitNames.has(t)) selectedUnits.add(t);
    else selected.add(t);
  }
  for (const w of (params.get("wearers") || "").split(",").filter(Boolean)) selectedW.add(w);
  for (const u of (params.get("units") || "").split(",").filter(Boolean)) selectedUnits.add(u);
  searchEl.value = params.get("q") || "";

  const inScope = (c) => series === "all" || c.series === series;
  const scoped = () => costumes.filter(inScope);

  function tagCountsOf(list) {
    const m = new Map();
    for (const c of list) {
      for (const t of c.tags || []) {
        if (!unitNames.has(t)) m.set(t, (m.get(t) || 0) + 1);
      }
    }
    return m;
  }
  function unitCountsOf(list) {
    const m = new Map();
    for (const c of list) {
      for (const unit of c.tags || []) {
        if (unitNames.has(unit)) m.set(unit, (m.get(unit) || 0) + 1);
      }
    }
    return m;
  }
  function wearerCountsOf(list) {
    const m = new Map();
    for (const c of list) {
      for (const w of c.wearers || []) {
        if (w === "シャイニーカラーズ全体") continue;
        m.set(w, (m.get(w) || 0) + 1);
      }
    }
    return m;
  }

  // 現在の作品に存在しない選択を外す
  function pruneSelections() {
    const tv = tagCountsOf(scoped());
    for (const t of [...selected]) if (!tv.has(t)) selected.delete(t);
    const wv = wearerCountsOf(scoped());
    for (const w of [...selectedW]) if (!wv.has(w)) selectedW.delete(w);
    const uv = unitCountsOf(scoped());
    for (const unit of [...selectedUnits]) if (!uv.has(unit)) selectedUnits.delete(unit);
  }

  function syncUrl() {
    const p = new URLSearchParams();
    if (series !== "all") p.set("series", series);
    if (selected.size) p.set("tags", [...selected].join(","));
    if (selectedW.size) p.set("wearers", [...selectedW].join(","));
    if (selectedUnits.size) p.set("units", [...selectedUnits].join(","));
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
          pruneSelections();
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
        const b = el("button", { class: "chip tag-filter", type: "button", "aria-pressed": String(selected.has(t)) }, [
          tagIcon(t, tagMeta),
          t,
          el("span", { class: "n", text: String(counts.get(t)) }),
        ]);
        setTagStyle(b, tagMeta[t]);
        b.addEventListener("click", () => {
          selected.has(t) ? selected.delete(t) : selected.add(t);
          update();
        });
        return b;
      })
    );
  }

  function unitChip(unit, n) {
    const b = el("button", {
      class: "chip unit-filter", type: "button", "aria-pressed": String(selectedUnits.has(unit)),
    }, [
      tagIcon(unit, tagMeta),
      unit,
      el("span", { class: "n", text: String(n) }),
    ]);
    setTagStyle(b, tagMeta[unit]);
    b.addEventListener("click", () => {
      selectedUnits.has(unit) ? selectedUnits.delete(unit) : selectedUnits.add(unit);
      update();
    });
    return b;
  }

  function renderUnits() {
    const groups = [];
    for (const s of seriesList) {
      if (series !== "all" && s.id !== series) continue;
      const counts = unitCountsOf(costumes.filter((c) => c.series === s.id));
      if (!counts.size) continue;
      const order = [...counts.keys()].sort((a, b) => a.localeCompare(b, "ja"));
      groups.push({ s, counts, order });
    }
    const unitsBox = document.getElementById("units");
    if (!groups.length) {
      unitsBox.replaceChildren(el("p", { class: "muted", text: "ユニットデータがありません" }));
      return;
    }
    unitsBox.replaceChildren(
      ...groups.map((g) =>
        el("div", { class: "chip-group" }, [
          series === "all" ? el("p", { class: "chip-group-label" }, [seriesBadge(g.s, 16), g.s.short]) : "",
          el("div", { class: "chips" }, g.order.map((unit) => unitChip(unit, g.counts.get(unit)))),
        ])
      )
    );
  }

  // ---- 着用者(現在の作品に存在するユニット・アイドルだけ。全作品のときは作品ごとにグループ表示) ----
  function wearerChip(w, n) {
    const b = el("button", { class: "chip wearer", type: "button", "aria-pressed": String(selectedW.has(w)) }, [
      wearerIcon(w, wearerMeta),
      w,
      el("span", { class: "n", text: String(n) }),
    ]);
    const meta = wearerMeta && wearerMeta[w];
    if (meta && typeof meta.color === "string" && /^#[\da-f]{6}$/i.test(meta.color)) {
      b.style.setProperty("--wearer-color", meta.color);
    }
    if (meta && typeof meta.textColor === "string" && /^#[\da-f]{6}$/i.test(meta.textColor)) {
      b.style.setProperty("--wearer-text-color", meta.textColor);
    }
    b.addEventListener("click", () => {
      selectedW.has(w) ? selectedW.delete(w) : selectedW.add(w);
      update();
    });
    return b;
  }

  function renderWearers() {
    const groups = [];
    for (const s of seriesList) {
      if (series !== "all" && s.id !== series) continue;
      const counts = wearerCountsOf(costumes.filter((c) => c.series === s.id));
      if (!counts.size) continue;
      // データ上の登場順を維持(ユニット・アイドルの並びを崩さない)
      const order = [];
      for (const c of costumes) {
        if (c.series !== s.id) continue;
        for (const w of c.wearers || []) {
          if (w !== "シャイニーカラーズ全体" && !order.includes(w)) order.push(w);
        }
      }
      groups.push({ s, order, counts });
    }
    if (!groups.length) {
      wearerBox.replaceChildren(el("p", { class: "muted", text: "着用者データがありません" }));
      return;
    }
    wearerBox.replaceChildren(
      ...groups.map((g) =>
        el("div", { class: "chip-group" }, [
          series === "all" ? el("p", { class: "chip-group-label" }, [seriesBadge(g.s, 16), g.s.short]) : "",
          el("div", { class: "chips" }, g.order.map((w) => wearerChip(w, g.counts.get(w)))),
        ])
      )
    );
  }

  function matches(c) {
    if (!inScope(c)) return false;
    // 選択タグをすべて含む衣装だけ表示(AND検索)
    for (const t of selected) if (!(c.tags || []).includes(t)) return false;
    // 選択ユニットのいずれかに該当する衣装を表示(OR)
    if (selectedUnits.size && !(c.tags || []).some((unit) => selectedUnits.has(unit))) return false;
    // 選択した着用者のいずれかが着用している衣装(OR)
    if (selectedW.size && !(c.wearers || []).some((w) => selectedW.has(w))) return false;
    const q = searchEl.value.trim().toLowerCase();
    if (!q) return true;
    const s = seriesMap.get(c.series);
    const hay = [
      c.name, s ? s.name : "", s ? s.short : "",
      ...(c.wearers || []), ...(c.lives || []), ...(c.songs || []), ...(c.tags || []),
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
        const unitTags = (c.tags || []).filter((t) => unitNames.has(t));
        return el("a", { class: "card", style: "--i:" + Math.min(i, 14), href: "costume.html?id=" + encodeURIComponent(c.id) }, [
          el("img", { src: c.image || "images/placeholder.svg", alt: c.name, loading: "lazy" }),
          el("div", { class: "body" }, [
            el("p", { class: "name", text: c.name }),
            el("p", { class: "meta" }, [
              s && series === "all" ? seriesBadge(s, 18) : "",
              s && series === "all" && unitTags.length ? el("span", { class: "brand-unit-divider", "aria-hidden": "true" }) : "",
              ...unitTags.map((unit) => tagIcon(unit, tagMeta)),
              c.firstAppearance ? el("span", { class: "first-appearance", text: "初登場: " + c.firstAppearance }) : "",
            ]),
            el("div", { class: "tags" }, (c.tags || []).filter((t) => !unitNames.has(t)).map((t) => {
              const tag = el("span", { class: "tag" }, [tagIcon(t, tagMeta), t]);
              setTagStyle(tag, tagMeta[t]);
              return tag;
            })),
          ]),
        ]);
      })
    );
  }

  // 詳細検索(検索バー・タグ)に条件が入っているとき、閉じていても件数で分かるようにする
  const advancedEl = document.getElementById("advanced");
  const advCountEl = document.getElementById("adv-count");
  const wearerCountEl = document.getElementById("wearer-count");
  const unitCountEl = document.getElementById("unit-count");
  function renderAdvancedCount() {
    const n = selected.size + (searchEl.value.trim() ? 1 : 0);
    advCountEl.textContent = n ? String(n) : "";
    wearerCountEl.textContent = selectedW.size ? String(selectedW.size) : "";
    unitCountEl.textContent = selectedUnits.size ? String(selectedUnits.size) : "";
  }

  function update() {
    renderAdvancedCount();
    renderSeries();
    renderChips();
    renderUnits();
    renderWearers();
    renderGrid();
    syncUrl();
  }

  searchEl.addEventListener("input", update);
  clearBtn.addEventListener("click", () => {
    selected.clear();
    selectedW.clear();
    selectedUnits.clear();
    searchEl.value = "";
    update();
  });

  pruneSelections();
  // URLで共有された条件があれば、該当する絞り込みを開いた状態で表示する
  if (selected.size || searchEl.value.trim()) advancedEl.open = true;
  if (selectedW.size) document.getElementById("wearers-filter").open = true;
  if (selectedUnits.size) document.getElementById("units-filter").open = true;
  update();
})();
