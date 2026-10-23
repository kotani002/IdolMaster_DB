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
  "name": "衣装名",
  "image": "images/ファイル名.png",
  "firstAppearance": "2020年1月",
  "lives": ["着用ライブ名"],
  "idols": ["着用アイドル名"],
  "tags": ["ワンピース", "青系"],
  "stories": ["登場コミュ名"],
  "tweets": ["https://twitter.com/ユーザー名/status/ツイートID"]
}
```

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
