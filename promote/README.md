# アイマス楽曲プレゼンシート

アイドルマスターの「A ブランドのおすすめ曲」をプレゼンする画像を作れる、非公式のファンメイドツールです。Cloudflare Pages で公開している静的サイトです（ビルド不要）。

公開URL：https://imasfan-presen.pages.dev/

旧URL（GitHub Pages の `kotani002.github.io/IdolMaster_DB/promote/`、Cloudflare Workers の `imas-presen-songs.283production-staff.workers.dev`）で開くと、新URLへ自動で移動します。

## できること

- 名前を入力できます（未入力なら「名無しP」）。おすすめするブランド（A）を選べます。
- 1曲ごとにカードを作れます。カードには次の内容を入れられます。
  - お題（○○な曲）：既定のお題から選ぶことも、自由に入力することもできます（`data/themes.json`）。
  - 曲名：A ブランドの曲を検索できます（ひらがな・カタカナどちらでも可）。ユニット名（一部やよみでも可）を入れるとそのユニットの曲が、アイドル名を正確に入れるとその人が歌った曲が出ます。リストにない曲は自由に入力できます。
  - ジャケット：画像 URL を埋め込むか、端末の画像を選びます。
  - プレゼン内容：自由に書けます。
  - 歌って欲しいアイドル：初期表示はその曲のブランドのアイドル。ブランドのタグや、対バンライブの出演者のタグ（「デレミリ対バン」「エムシャニ対バン」。Day1/Day2 で絞り込み、`data/events.json`）で切り替えられます。リストにない名前やユニット名も追加できます。
- 「＋ 新しい曲を追加する」でカードを増やせます（**8曲まで**。歌って欲しいアイドルは**1曲10人まで**（「○○全員」・ユニット名のタグも1人と数えます）。`assets/app.js` の `MAX_SONGS`・`MAX_TAGS` と、共有URLの `assets/share.js` の `LIMITS` を同じ数にしています）。並べ替え（↑↓）と削除もできます。
- 入力内容はブラウザに自動保存されます。
- 「画像を作る」で PNG を出力し、保存・コピー・共有・X へのポストができます。
- 同じ画面に**共有URL**が出ます。X へのポストの投稿文にも入ります。開いた人は、ブラウザで曲・お題・歌って欲しいアイドルを見て、曲を Apple Music の試聴（約30秒）で聴けます（`view.html`）。「続けて試聴する」で上から順に流せます。各曲に「Apple Musicで聴く」「Spotifyで探す」のリンクがあります。
  - **プレゼン内容（文章）は共有URLに入りません**（URL が長くなるため。文章は出力画像で伝えます）。
  - 共有URLは、シートを ID の並びにして URL の `#` 以降に入れたものです（例：`https://imasfan-presen.pages.dev/view#b…`）。サーバーには何も保存しません（`#` 以降はサーバーに送られません）。4曲・アイドル3人ずつのシートで約120文字です。
  - 形式（`assets/share.js`）：曲は曲ID、歌って欲しいアイドルはアイドルID、お題は `data/themes.json` の番号、ブランドは `BRAND_CODES` の番号にして、ビット単位で詰めています。名前や色は共有ページがデータから引きます。リストにない曲名・お題・名前、「Day1全員」などのタグだけは文字のまま入ります。
  - **番号を変えないこと**：共有済みの URL が別の曲・人・お題を指してしまうため、次のものは並べ替え・削除をしません（末尾への追加はできます）。
    - `data/themes.json` の並び
    - `assets/share.js` の `BRAND_CODES` の並び
    - アイドル・曲の ID（ふじわらはじめの ID。手で足したアイドルの文字の ID（`cg-chinatsu` など）も変えない）
- セキュリティ：共有URLの中身は誰でも作れるので、共有ページは中身を文字としてだけ表示し、データは実在する項目だけを引きます。長さ・件数に上限があり、壊れた URL は開きません。`_headers` で CSP（読み込んでよい場所の制限）・HSTS（https だけで開かせる）・iframe への埋め込み禁止などを設定しています。

## ファイル構成

```
index.html              画面
view.html               共有ページ（共有URLで開くシートの閲覧・お試し視聴）
assets/style.css        見た目（.x-* は出力画像用、.v-* は共有ページ用）
assets/app.js           処理
assets/share.js         共有URLの作成・読み取り（app.js と view.js が使う）
assets/view.js          共有ページの処理（試聴は iTunes の lookup API で、開いたときに試聴URLを取る）
data/previews.json      楽曲ID → Apple Music の trackId（試聴用。scripts/fetch_previews_itunes.py で作成）
data/brands.json        ブランド定義（名前・テーマカラー）
data/themes.json        お題の候補（共有URLが番号で参照するので、並べ替え・削除はしない。追加は末尾に）
_redirects              公開サイトで README・scripts・.claude などサイトに使わないファイルを開かれたらトップへ移す（GitHub 上では見えるので秘密は置かない）
_headers                Cloudflare Pages のヘッダー（キャッシュ・CSP などのセキュリティ設定。CSP は scripts/update_csp.py で作る）
scripts/update_csp.py   _headers の CSP を作り直す（index.html・view.html に直接書いた <script> を変えたら必ず実行）
data/events.json        イベントの出演者（デレミリ対バン・エムシャニ対バン Day1/Day2。公式の出演者ページを見て手で更新）
data/jackets.json       楽曲ID → ジャケットURL の対応表（任意。書いた曲は選曲時に自動で入る）
data/songs/<brand>.json ブランド別の曲一覧（自動生成。units に歌唱ユニット名）
data/units.json         ユニット名 → よみ（自動生成。ひらがなでユニット検索するため）
data/idols/<brand>.json ブランド別のアイドル一覧（自動生成）
scripts/fetch_data.py   ふじわらはじめ API から songs / idols を生成
scripts/fetch_jackets.py 公式ディスコグラフィーからジャケットURLを照合
scripts/jackets_csv.py  ジャケット未登録曲の CSV 書き出し / 取り込み
scripts/make_ogp.py     SNS カード画像（assets/ogp.png）を生成
```

データの更新は定期実行していません。必要なときに、リポジトリ直下の `.github/workflows/update-promote-data.yml` を Actions 画面から手動で実行するか、手元で `python scripts/fetch_data.py` を実行して commit します（GitHub Actions はリポジトリ直下のものしか動かないため、ワークフローはそこにあります）。

## 公開手順（Cloudflare Pages）

`release` ブランチの `promote/` フォルダを公開しています。`release` に push すると自動で公開されます。

Cloudflare のダッシュボード → Workers & Pages → `imasfan-presen`（Pages）→ 設定 の内容：

- Git リポジトリ：`kotani002/IdolMaster_DB`
- プロダクション ブランチ：`release`（プレビューのブランチは「なし」。`release` 以外の push では公開されない）
- ビルド コマンド：（なし）
- ビルド出力ディレクトリ：`promote`（リポジトリ直下には別サイトの index.html があるため、`promote/index.html` をトップページにする）

以前の公開先 Cloudflare Workers の `imas-presen-songs` も、同じく `release` の `promote/` を公開し続けています（共有済みの旧URL用）。こちらで開くと `index.html` の処理で新URLへ移動します。

GitHub の Settings → Actions → General → Workflow permissions は「Read and write」にします（ワークフローでデータを更新したときのコミット用）。

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

ブランドを追加するときは、`scripts/fetch_data.py` の `BRANDS` と `data/brands.json` の両方に追記します。例：シャイニーカラーズは `music_type: "sc"`、`production: "sc"`、学園アイドルマスターは `music_type: "gakuen"`、`production: "gakuen"`。
アイドルの色はふじわらはじめの一覧から取ります。SideM はふじわらはじめに色が無いので、[imas-db.jp のカラーコード一覧](https://imas-db.jp/misc/color.html) から取ります（`BRANDS` の `imasdb_colors`）。
ユニット名（曲検索用）はふじわらはじめのユニット一覧と API から取ります。全ユニットで歌う曲（ブランド全員のユニットが付いた曲か、5ユニット以上が歌う曲）は個別のユニット名では出さず、「全体曲」で探せるようにしています（`scripts/fetch_data.py` の `whole_song_units`）。
ブランドの垣根を越えた曲（VOY@GER・なんどでも笑おう・スタマスの曲など）は「越境曲」として、`CROSSOVER_SONGS` に書いたブランドの曲一覧に入れ、「越境曲」で検索できます。スタマスの曲は「スターリットシーズン」「スタマス」でも出ます（`CROSSOVER_TAGS`）。ブランドごとに別の盤が出ている曲は、`data/jackets.json` の「ブランド:曲ID」にそのブランドの盤のジャケットを入れ、無いブランドは `data/jacket_overrides.json` の `_all`（既定のジャケット）を使います。
シンデレラの「ゴキゲンParty Night」「ススメ☆オトメ」「Near to You」「認めてくれなくたっていいよ」は、Cute/Cool/Passion jewelries! と MASTER アルバムで歌うメンバーが違うので、「曲名 (Ver.Cute)」のようにバージョン別の曲に分けています（`SPLIT_VERSIONS`。曲ID は「元の曲ID-キー」）。SideM の「MEET THE WORLD!」も WORLD TRE@SURE 01〜13 の国別版に分け、元の曲（UNIT COLLECTION 版）も残しています（`SPLIT_KEEP_BASE`）。
Migratory Echoes（シャニマス）はユニットごとに曲調とジャケットが違うので、「Migratory Echoes (ユニット名Ver.)」を別の曲として登録しています（`EXTRA_SONGS` と `data/jacket_overrides.json`）。ユニットだけ取り直すときは `python scripts/fetch_data.py units`（約300ユニット分を取るので10分ほどかかります）。
`python scripts/fetch_data.py sc` のようにブランドを指定すると、そのブランドだけを取り直します（歌唱者もそのブランドのアイドル分だけ調べ、前回の内容に足します）。

## ジャケットを更新する

```bash
python scripts/fetch_jackets.py cg
python scripts/fetch_jackets.py ml
python scripts/fetch_jackets.py sc
python scripts/fetch_jackets.py sidem
python scripts/fetch_jackets.py gm
```

公式のディスコグラフィーから各CDのジャケット・発売日・収録曲を取得し、`data/songs/<brand>.json` の曲名と照合して `data/jackets.json` に書き込みます。

- 取得元：シンデレラガールズは公式ポータル、ミリオンライブ・シャイニーカラーズ・SideM はランティスのサイト、学園アイドルマスターは公式レーベルサイト（`scripts/fetch_jackets.py` の `SOURCES`）。
- 同じ曲が複数のCDに入っている場合は、本人歌唱版が入ったCDのうち一番早く発売されたもののジャケットを使います。ライブBD・カラオケ版は、CDで見つからない曲にだけ使います。
- SideM の F＠NTASTIC COMBINATION のように2つのユニットが同じ曲をそれぞれのCDで出している曲は、両方のジャケットを `data/jacket_alts.json` に書き出し、サイトのジャケット画面で「公式ジャケットから選ぶ」として切り替えられます（`scripts/fetch_jackets.py` の `ALT_SERIES`）。
- 使うジャケットを手で決めた曲は `data/jacket_overrides.json`（ブランド → 曲ID → ジャケットURL）に書きます。ここに書いた曲は、照合結果より優先されます。
- 取得したページは `scripts/.cache/` に保存されます。照合ルールだけ変えたいときは `--offline` を付ければ再取得しません。
- 照合できなかった曲は `scripts/.cache/<brand>_unmatched.txt` に出力されます。
- 公式で見つからなかった曲は、iTunes Search API（Apple Music）でも探せます。`python scripts/fetch_jackets_itunes.py` で結果を `scripts/.cache/itunes_report.txt` に出し、内容を確認してから `--apply` で `data/jackets.json` に書き込みます（設定済みのジャケットは変えません。出典はサイト下部に記載）。
- それでも見つからない曲は、サイト上で「NOW PRINTING...」画像になり、ユーザーが自分でジャケットを設定できます。

### 照合できなかった曲を手作業で登録する

```bash
python scripts/jackets_csv.py export
```

ジャケットが未登録の曲を、全ブランド分まとめて `jackets_todo.csv` に書き出します（Excel で開けます）。`jacket_url` 列に画像URLを記入して保存したら、次のコマンドで取り込みます。

```bash
python scripts/jackets_csv.py import
```

`jacket_url` を記入した行だけが `data/jackets.json` に追加されます。空欄の行は何も変更しません。

## お試し視聴のデータを更新する

```bash
python scripts/fetch_previews_itunes.py          # 全ブランド
python scripts/fetch_previews_itunes.py sc       # ブランドを指定
python scripts/fetch_previews_itunes.py sc --redo  # 登録済みの曲も探し直す
```

iTunes Search API で各曲の Apple Music の trackId を探し、`data/previews.json` に書きます。照合のしかたはジャケット（`fetch_jackets_itunes.py`）と同じです。ただし、カラオケ・インスト・ソロリミックスは使いません。歌唱者の名前が入った結果を優先します。結果は `scripts/.cache/previews_report.txt` に出るので、取り違えが無いか確認してください。API は1分あたり約20回までなので、初回は1ブランド数十分かかります。2回目以降は `scripts/.cache/itunes/` の保存分を使うので速くなります。登録済みの曲は、`--redo` を付けない限り探し直しません。

試聴URL（previewUrl）は変わることがあるので保存していません。共有ページを開いたときに、trackId で lookup API へまとめて1回だけ問い合わせます。

## ライセンス・クレジット

- 楽曲・アイドルデータは [アイマス楽曲DB ふじわらはじめ](https://fujiwarahaji.me/) の API を利用しています（[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/deed.ja)）。非営利で利用し、クレジット表記を残してください。
- 楽曲・ジャケット等の著作権は各権利者に帰属します。© BANDAI NAMCO Entertainment Inc.
- お試し視聴は Apple Music のプレビュー（iTunes Search API）を使っています。共有ページに「Apple Musicで聴く」リンクと出典を載せています。
- URL で埋め込んだジャケット画像は、配信元が CORS を許可していない場合、画像出力の時だけ `images.weserv.nl`（画像プロキシ）経由で読み込みます。
