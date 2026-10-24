# アイドルマスター衣装図鑑(GitHub Pages)

衣装の「見た目」と「名前」を結びつけるための非公式ファンサイトです。ビルド不要の静的サイトで、そのまま GitHub Pages で動きます。

## 構成

```
index.html        トップページ(一覧 + タグ絞り込み)
costume.html      衣装紹介ページ(?id=衣装ID で表示)
data/costumes.json 衣装データ(ここだけ編集すれば衣装を追加できる)
images/           衣装イラスト置き場
css/style.css
js/common.js      データ読み込み共通処理
js/index.js       トップページの一覧・絞り込み
js/costume.js     衣装紹介ページの描画・ツイート埋め込み
```

## 衣装の追加方法

`data/costumes.json` に1件追加し、イラストを `images/` に置きます。

```json
{
  "id": "一意のID(英数字とハイフン)",
  "series": "作品ID(data/series.json の id。shinycolors / gakumas)",
  "name": "衣装名",
  "image": "images/ファイル名.png",
  "firstAppearance": "2020年1月",
  "lives": ["着用ライブ名"],
  "wearers": ["着用者(ユニット名・アイドル名)"],
  "songs": ["歌唱楽曲名"],
  "tags": ["ワンピース", "青系"],
  "stories": ["登場コミュ名"],
  "tweets": ["https://twitter.com/ユーザー名/status/ツイートID"],
  "source": "参考ページのURL(https のみ)",
  "note": "メモ(画面には表示されません)"
}
```

- 作品は `data/series.json` で定義します。新しい作品は1行追加し、衣装データの `series` に同じIDを書けば、トップの切り替えアイコンに自動で並びます。
- 学マスの共通衣装は1件にまとめ、`wearers` に複数のアイドル名を入れて、タグに「共通衣装」を付けています。髪型は掲載していません。
- `songs`(歌唱楽曲)は省略または空配列でもOKです。衣装紹介ページの「衣装データ」に表示され、トップページの検索対象にもなります。
- `wearers`(着用者)はタグとは別の絞り込み欄になります。選択中の作品に存在するユニット・アイドルだけが表示され、複数選ぶとどれかを着用している衣装が出ます(OR)。
- 着用者の横のアイコンは、標準では名前の頭文字の丸バッジです。画像に差し替える場合は `images/wearers/` に置いて、`data/wearers.json` に書きます(ファイルが無くても動きます)。

  ```json
  { "花海咲季": { "icon": "images/wearers/saki.png", "color": "#e8505b", "textColor": "#ffffff" } }
  ```
- 着用者絞り込みボタンの色は `data/wearers.json` で設定します。`color` はボタンの枠線・通常時の文字色・選択時の背景色、`textColor` は選択時の文字色です。どちらも `#RRGGBB` 形式で指定してください。未設定時は既定色を使います。
- トップの並びは「作品 → 着用者で絞り込み → 詳細検索(検索バー・タグ)→ 一覧」です。詳細検索は初期状態で閉じており、条件が入っていると件数が表示されます。
- `tags` がトップページの絞り込みボタンに自動で反映されます(複数選択はAND条件)。
- `tweets` は twitter.com / x.com のツイートURLのみ埋め込まれます。
- 絞り込み状態はURL(`?tags=青系,ワンピース`)に保存されるので、そのまま共有できます。

## 公開手順(GitHub Pages)

1. このフォルダの中身をリポジトリのルートに置いて push
2. リポジトリの Settings → Pages → Source を「Deploy from a branch」、Branch を `main` / `(root)` にして保存
3. `https://<ユーザー名>.github.io/<リポジトリ名>/` で公開されます

## ローカル確認

`fetch` で JSON を読むため、ファイルを直接開かず簡易サーバー経由で確認してください。

```
python3 -m http.server 8000
# http://localhost:8000/ を開く
```

## 画像について

ゲーム内のスクリーンショットや公式イラストは権利者に帰属します。掲載する場合は、各権利者のガイドラインを確認してください。
