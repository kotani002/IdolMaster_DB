# アイマス楽曲プレゼンシート

アイドルマスターの対バンに向けて、「A ブランドのおすすめ曲」をプレゼンする画像を作れる、非公式のファンメイドツールです。Cloudflare Workers（静的アセット）で公開している静的サイトです（ビルド不要）。

公開URL：https://imas-presen-songs.283production-staff.workers.dev/ （旧URL の GitHub Pages で開くと、新URLが公開されていればこのURLへ自動で移動します）

## できること

- 名前を入力できます（未入力なら「名無しP」）。おすすめするブランド（A）を選べます。
- 1曲ごとにカードを作れます。カードには次の内容を入れられます。
  - お題（○○な曲）：既定のお題から選ぶことも、自由に入力することもできます（`data/themes.json`）。
  - 曲名：A ブランドの曲を検索できます（ひらがな・カタカナどちらでも可）。リストにない曲は自由に入力できます。
  - ジャケット：画像 URL を埋め込むか、端末の画像を選びます。
  - プレゼン内容：自由に書けます。
  - 歌唱予想メンバー：初期表示はその曲のブランドのアイドル。ブランドのタグや「★ デレミリ対バン」（Day1/Day2 の出演者、`data/events.json`）で切り替えられます。リストにない名前やユニット名も追加できます。
- 「＋ 新しい曲を追加する」でカードを増やせます。並べ替え（↑↓）と削除もできます。
- 入力内容はブラウザに自動保存されます。
- 「画像を作る」で PNG を出力し、保存・コピー・共有・X へのポストができます。

## ファイル構成

```
index.html              画面
assets/style.css        見た目（.x-* は出力画像用）
assets/app.js           処理
data/brands.json        ブランド定義（名前・テーマカラー）
data/themes.json        お題の候補
data/events.json        イベントの出演者（デレミリ対バン Day1/Day2）
data/jackets.json       楽曲ID → ジャケットURL の対応表（任意。書いた曲は選曲時に自動で入る）
data/songs/<brand>.json ブランド別の曲一覧（自動生成）
data/idols/<brand>.json ブランド別のアイドル一覧（自動生成）
scripts/fetch_data.py   ふじわらはじめ API から songs / idols を生成
scripts/fetch_jackets.py 公式ディスコグラフィーからジャケットURLを照合
scripts/jackets_csv.py  ジャケット未登録曲の CSV 書き出し / 取り込み
scripts/make_ogp.py     SNS カード画像（assets/ogp.png）を生成
```

データの週次自動更新は、リポジトリ直下の `.github/workflows/update-promote-data.yml` です（GitHub Actions はリポジトリ直下のものしか動かないため）。

## 公開手順（Cloudflare Workers）

`release` ブランチの `promote/` フォルダを公開しています。`release` に push すると自動で公開されます。

Cloudflare のダッシュボード → Workers & Pages → `imas-presen-songs` → 設定 の内容：

- Git リポジトリ：`kotani002/IdolMaster_DB`
- プロダクション ブランチ：`release`
- ビルド コマンド：（なし）
- デプロイ コマンド：`npx wrangler deploy`
- ルート ディレクトリ：`promote`（リポジトリ直下には別サイトの index.html があるため、`promote` を指定して `promote/index.html` をトップページにする）

GitHub の Settings → Actions → General → Workflow permissions は「Read and write」にします（データ自動更新のコミット用）。

`release` 以外のブランチに push すると、確認用のプレビューURL（`*-imas-presen-songs.283production-staff.workers.dev`）が作られます。

公開URLを変えた場合は、`index.html` の旧URLからの転送先（`NEW_SITE`）・`canonical`・`og:url`・`og:image`・`twitter:image` も書き換えてください。

## ローカルで確認する

`fetch` で JSON を読み込むため、ファイルを直接開くのではなくローカルサーバーで表示してください。

```bash
python -m http.server 8765
```

## データを更新する

```bash
python scripts/fetch_data.py
```

ブランドを追加するときは、`scripts/fetch_data.py` の `BRANDS` と `data/brands.json` の両方に追記します。例：シャイニーカラーズは `music_type: "sc"`、`production: "283"`。

## ジャケットを更新する

```bash
python scripts/fetch_jackets.py cg
python scripts/fetch_jackets.py ml
```

公式のディスコグラフィーから各CDのジャケット・発売日・収録曲を取得し、`data/songs/<brand>.json` の曲名と照合して `data/jackets.json` に書き込みます。

- 取得元：シンデレラガールズは公式ポータル、ミリオンライブはランティスのサイト（`scripts/fetch_jackets.py` の `SOURCES`）。
- 同じ曲が複数のCDに入っている場合は、本人歌唱版が入ったCDのうち一番早く発売されたもののジャケットを使います。ライブBD・カラオケ版は、CDで見つからない曲にだけ使います。
- 取得したページは `scripts/.cache/` に保存されます。照合ルールだけ変えたいときは `--offline` を付ければ再取得しません。
- 照合できなかった曲は `scripts/.cache/<brand>_unmatched.txt` に出力されます。これらの曲は、サイト上でユーザーが自分でジャケットを設定します。

### 照合できなかった曲を手作業で登録する

```bash
python scripts/jackets_csv.py export
```

ジャケットが未登録の曲を、全ブランド分まとめて `jackets_todo.csv` に書き出します（Excel で開けます）。`jacket_url` 列に画像URLを記入して保存したら、次のコマンドで取り込みます。

```bash
python scripts/jackets_csv.py import
```

`jacket_url` を記入した行だけが `data/jackets.json` に追加されます。空欄の行は何も変更しません。

## ライセンス・クレジット

- 楽曲・アイドルデータは [アイマス楽曲DB ふじわらはじめ](https://fujiwarahaji.me/) の API を利用しています（[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.ja)）。非営利で利用し、クレジット表記を残してください。
- 楽曲・ジャケット等の著作権は各権利者に帰属します。© BANDAI NAMCO Entertainment Inc.
- URL で埋め込んだジャケット画像は、配信元が CORS を許可していない場合、画像出力の時だけ `images.weserv.nl`（画像プロキシ）経由で読み込みます。
