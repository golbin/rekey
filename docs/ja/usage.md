# 使い方

コマンドはチームデータのフォルダ内で実行します。変更を伴うコマンド（`rotate`、`revoke`、`sync`、`import`）は `--dry-run` を付けるとプレビューだけ行います。

## ローカルの .env を作る

```bash
rekey sync targets/file/shop/web/.env.local.tpl
```

- キーは 1Password から埋めます。ファイル内のほかの行はそのままです。
- ローカルのテンプレートには**キーだけ**が入っています。ポートなどのローカル設定は自分で書くか、プロジェクトの `.env.example` を参照してください。
- チームで共有したいローカル設定は、テンプレートに `KEY=値` の行を追加してください。次の `sync` から一緒に書き込まれます。

## 既存の .env からテンプレートを作る

```bash
rekey init ~/code/shop/web/.env.local                   # ファイルひとつ
rekey init ~/code/shop --with-settings                   # フォルダ内の .env すべて、通常の設定値も含める
```

- キーは `{{ op://… }}` の参照に置き換わります。すでにテンプレートにあるキーと同じ値なら、そのキーを使います。
- テンプレートが既にあれば足りない変数だけを追加し、手で直した行はそのままです。
- `--with-settings` がなければ、ローカルのテンプレートに通常の設定値（ポート、URL など）は入れません。
- そのあと `rekey import` で新しい値を 1Password に保存します。

## キーを探す

```bash
rekey ls                     # 全体：サービス、発行方法、使用先の数、タグ
rekey ls 'openai.*'          # 一部だけ
rekey where openai.shop      # このキーを使うテンプレートと変数
```

## キーをローテーションする

```bash
rekey rotate openai.shop
```

1. 事前確認：足りないログインなどはその場で解決します。
2. 実行内容の要約を示し、開始してよいか尋ねます。
3. 新しいキーを用意します。
   - **自動：** API で発行するか、ローカルで生成します。権限がないなどで失敗したら理由を示してブラウザに切り替えます。
   - **ブラウザ：** ページが開いたら名前欄で ⌘V（名前はコピー済み）→ 作成 → 新しいキーを**コピー**。コピーした瞬間に次へ進みます。`s` でスキップ、`q` で中止。
   - 古いキーやほかのサービスのキーをコピーすると知らせます。新しいキーが動かなければコピーし直せます。
   - 途中で止めたら同じコマンドをもう一度実行します。終わったキーは飛ばします。新しいキーを間違えたら `rekey rotate <キー> --redo`。
4. 1Password に保存します。古い値は無効化するまで保管します。
5. すべての使用先を更新します。Vercel production と Railway は再デプロイし、正常になるまで待ちます。
   - Supabase Edge Function、Fly、Worker はすぐに反映されます。GitHub Actions は次の実行から反映されます。
   - **GCP Secret Manager を読むサービスは手動で再起動**しないと新しいキーを使いません。
6. 古いキーをいま無効化するか尋ねます。もう少し様子を見るなら N にして、あとで無効化します。

```bash
rekey revoke openai.shop
```

- まだ古い値を使っている場所があれば無効化を止め、実行すべきコマンドを示します。
- 無効化 API のないサービスでは、古いキーの末尾 4 文字を示してページを開きます。
- 途中で止まっても、同じコマンドを再実行すれば残りから続けます。ローテーション済みのキーは、古いキーを無効化するまで再ローテーションしません。
- 一部の使用先に書き込めなくても残りは続行し、最後に書き直すコマンドを示します。

## 複数のキーをまとめて

```bash
rekey rotate 'cartesia.*'              # 名前のパターン
rekey rotate tag:breach-2026           # keys.toml のタグ
rekey rotate 'in:vercel/shop/*'        # これらのテンプレートが使うキーすべて
```

自動のキーを先に処理し、ブラウザの手順は最後にサービスごとにまとめます。

## 設定を変える

プラットフォームのテンプレートには通常の設定も入っています。

```bash
# targets/vercel/shop/production.tpl の値を直したら
rekey diff targets/vercel/shop/production.tpl            # 実際の値と比較
rekey sync targets/vercel/shop/production.tpl --deploy   # 反映して再デプロイ
git commit -am "shop: change APP_URL"
```

`sync all` はすべてのプラットフォームに書き込みます。本当に必要なときだけ使ってください。

## キーを追加する

1. 使うテンプレートに行を追加します。名前は `<サービス>.<プロジェクト>`、自社アプリ同士で使うトークンは `self.<プロジェクト>.<用途>` とします。
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/stripe.shop/credential }}
   ```
2. 値を入れます。すでに使っている値なら `rekey import stripe.shop`、新しく発行するなら `rekey rotate stripe.shop`。
3. `git commit`

使用先から外すには、テンプレートからその行を消すだけです。

## リファレンス

**テンプレートのパス = 値を書き込む場所**（`targets/` 配下、`.tpl` は省略）

| パス | 書き込み先 |
|---|---|
| `file/<パス>` | ローカルのファイル（チームデータフォルダの親フォルダが基準） |
| `vercel/<プロジェクト>/<production·preview·development>` | Vercel |
| `railway/<プロジェクト>/<環境>/<サービス>` | Railway |
| `supabase/<project ref>` | Supabase Edge Function secrets |
| `gcp/<プロジェクト>` | GCP Secret Manager |
| `github/<owner>/<repo>[/<環境>]` | GitHub Actions secrets |
| `fly/<アプリ>`、`worker/<名前>` | Fly、Cloudflare Worker |

テンプレートにある変数だけを書き込みます。書き込み先のほかの変数には触れません。

**keys.toml** には例外だけを書きます。

```toml
["self.shop.data-master-key"]
locked = "理由"                 # rotate がスキップ（--force のみで上書き）
note = "ローテーション前のメモ"   # rotate と where で表示
tags = ["check", "retire"]      # check：rotate がスキップ / retire：all から除外
page = "https://…"              # ブラウザ手順で開くページ
```

**管理者キー**：同じ vault に `rekey.openai-admin`、`rekey.cloudflare-admin`、`rekey.resend-admin`、`rekey.anthropic-admin`（無効化用）があれば、そのサービスを自動で処理します。`rekey setup` が登録を手伝います。

**環境変数**：`REKEY_HOME`（チームデータのフォルダ。既定は現在の場所から上にたどって最初に `targets/` か `keys.toml` がある場所）、`REKEY_ROOT`（`file/` の基準フォルダ。既定は `REKEY_HOME` の親）、`REKEY_STORE=file:<パス>`（1Password の代わりにファイル、テスト用）、`REKEY_NO_BROWSER=1`、`REKEY_LANG`（en、ko、zh、ja、es）
