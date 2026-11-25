// 衣装紹介ページ: ?id=xxx のデータを表示
(async function () {
  const app = document.getElementById("app");
  const id = new URLSearchParams(location.search).get("id");

  let costumes, seriesList, wearerMeta, tagMeta;
  try {
    [costumes, seriesList, wearerMeta, tagMeta] = await Promise.all([
      loadCostumes(), loadSeries(), loadWearerMeta(), loadTagMeta(),
    ]);
  } catch (e) {
    showError(e.message);
    return;
  }

  const c = costumes.find((x) => x.id === id);
  if (!c) {
    showError("指定された衣装が見つかりませんでした。");
    return;
  }

  document.title = c.name + " | アイドルマスター衣装図鑑";

  const listOrDash = (arr) =>
    arr && arr.length
      ? el("ul", { class: "plain" }, arr.map((v) => el("li", { text: v })))
      : el("span", { class: "muted", text: "—" });

  const tagLinks = (c.tags || []).map((t) => {
    const link = el("a", { class: "tag", href: "index.html?tags=" + encodeURIComponent(t) }, [tagIcon(t, tagMeta), t]);
    setTagStyle(link, tagMeta[t]);
    return link;
  });

  // 着用者: 押すと、その作品でその着用者に絞り込んだ一覧へ
  const wearerLinks = (c.wearers || []).length
    ? el("ul", { class: "plain" }, c.wearers.map((w) =>
        el("li", {}, [wearerIcon(w, wearerMeta), el("a", {
          href: "index.html?series=" + encodeURIComponent(c.series || "") + "&wearers=" + encodeURIComponent(w),
          text: w,
        })])))
    : el("span", { class: "muted", text: "—" });

  // 参考ページ(https のURLのみリンク化)
  const sourceLink = /^https:\/\//.test(c.source || "")
    ? el("a", { href: c.source, target: "_blank", rel: "noopener noreferrer", text: c.source })
    : el("span", { class: "muted", text: "—" });

  const row = (th, td) => el("tr", {}, [el("th", { text: th }), el("td", {}, [td])]);

  // ツイート埋め込み(twitter.com / x.com のURLのみ許可)
  const tweetUrls = (c.tweets || []).filter((u) => /^https:\/\/(twitter|x)\.com\/[^/]+\/status\/\d+/.test(u));
  const tweetBox = el(
    "div",
    { class: "tweets" },
    tweetUrls.map((u) =>
      el("blockquote", { class: "twitter-tweet" }, [el("a", { href: u.replace("https://x.com/", "https://twitter.com/"), text: u })])
    )
  );

  app.replaceChildren(
    el("a", { class: "back", href: "index.html", text: "← 衣装一覧へ戻る" }),
    el("article", { class: "costume" }, [
      (() => {
        const s = seriesList.find((x) => x.id === c.series);
        return s
          ? el("p", { class: "series-line" }, [
              seriesBadge(s, 24),
              el("a", { href: "index.html?series=" + encodeURIComponent(s.id), text: s.name }),
            ])
          : "";
      })(),
      el("h2", { class: "title", text: c.name }),

      el("div", { class: "illust" }, [
        el("img", { src: c.image || "images/placeholder.svg", alt: c.name + "のイラスト" }),
      ]),

      el("section", {}, [
        el("h3", { text: "衣装データ" }),
        el("table", { class: "data" }, [
          row("初登場時期", document.createTextNode(c.firstAppearance || "—")),
          row("着用ライブ", listOrDash(c.lives)),
          row("着用者", wearerLinks),
          row("歌唱楽曲", listOrDash(c.songs)),
          row("検索用タグ", tagLinks.length ? el("div", { class: "tags" }, tagLinks) : el("span", { class: "muted", text: "—" })),
        ]),
      ]),

      el("section", {}, [
        el("h3", { text: "関連データ" }),
        el("table", { class: "data" }, [
          row("登場コミュ", listOrDash(c.stories)),
          row("参考ページ", sourceLink),
        ]),
        el("h4", { text: "名前が出てきたツイート" }),
        tweetUrls.length ? tweetBox : el("p", { class: "muted", text: "登録されているツイートはありません。" }),
      ]),
    ])
  );

  if (tweetUrls.length) {
    const s = document.createElement("script");
    s.src = "https://platform.twitter.com/widgets.js";
    s.async = true;
    s.charset = "utf-8";
    document.body.appendChild(s);
  }
})();
