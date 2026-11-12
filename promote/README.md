# アイマス楽曲プレゼンシート

アイドルマスターの対バンに向けて、「A ブランドから B ブランドへのオススメ曲」をプレゼンする画像を作れる、非公式のファンメイドツールです。GitHub Pages で動く静的サイトです（ビルド不要）。

## できること

- 名前を入力できます（未入力なら「名無しP」）。おすすめする側（A）とされる側（B）のブランドを選べ、⇄ で入れ替えられます。
- 1曲ごとにカードを作れます。カードには次の内容を入れられます。
  - お題（○○な曲）：既定のお題から選ぶことも、自由に入力することもできます（`data/themes.json`）。
  - 曲名：A ブランドの曲を検索できます（ひらがな・カタカナどちらでも可）。リストにない曲は自由に入力できます。
  - ジャケット：画像 URL を埋め込むか、端末の画像を選びます。
  - プレゼン内容：自由に書けます。
  - 歌唱予想メンバー：B ブランドのアイドルからタグとして選びます。リストにない名前やユニット名も追加できます。
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
data/jackets.json       楽曲ID → ジャケットURL の対応表（任意。書いた曲は選曲時に自動で入る）
data/songs/<brand>.json ブランド別の曲一覧（自動生成）
data/idols/<brand>.json ブランド別のアイドル一覧（自動生成）
scripts/fetch_data.py   ふじわらはじめ API から songs / idols を生成
.github/workflows/update-data.yml  毎週データを自動更新
```

## 公開手順（GitHub Pages）

1. このフォルダの中身を GitHub リポジトリに push します。
2. リポジトリの Settings → Pages → Source を「Deploy from a branch」にし、`main` ブランチの `/ (root)` を指定します。
3. Settings → Actions → General → Workflow permissions を「Read and write」にします（データ自動更新のコミット用）。

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
