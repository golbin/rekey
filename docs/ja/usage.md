# 使い方

コマンドはチームデータのフォルダ内で実行します。変更を伴うコマンド（`rotate`、`issue`、`revoke`、`sync`、`import`、`arrange`）は `--dry-run` を付けるとプレビューだけ行います。

## ローカルの .env を作る

```bash
rekey sync targets/shop/file/shop/web/.env.local.tpl
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
- そのあと `rekey arrange "Acme - {env}"` で新しいキーを正しい vault に振り分け、`rekey import` でその値を 1Password に保存します。

## キーを探す

```bash
rekey ls                     # 全体：サービス、発行方法、使用先の数、タグ
rekey ls project:shop        # ひとつのプロジェクト
rekey ls '*.openai'          # ひとつのサービス
rekey where shop.openai      # このキーを使うテンプレートと変数
```

## キーをローテーションする

```bash
rekey rotate shop.openai
```

1. 事前確認：足りないログインなどはその場で解決します。
2. 実行内容の要約を示し、開始してよいか尋ねます。
3. 新しいキーを用意します。
   - **自動：** API で発行するか、ローカルで生成します。権限がないなどで失敗したら理由を示してブラウザに切り替えます。
   - **ブラウザ：** ページが開き、どこを押すかを示します。名前欄で ⌘V（名前はコピー済み）、古いキーと同じ権限を付け（古いキーの末尾 4 文字を表示します）、作成して**コピー**。コピーした瞬間に次へ進みます。`s` でスキップ、`q` で中止。
   - ログイン用のコード、古いキー、ほかのサービスのキーは新しいキーとして受け付けません。
   - DB パスワードは最後に回します。新しいパスワードを保存した瞬間に古いものは使えなくなるためです。
4. 1Password に保存します。古い値は無効化するまで保管します。
5. すべての使用先を更新します。続いてサービスごとに今すぐ再デプロイするか尋ねます（既定：いいえ）。再起動で進行中のセッションが切れるなら N にして、あとでいつもの方法か `rekey deploy <テンプレート>` でデプロイします。
   - Supabase Edge Function、Fly、Worker はすぐに反映されます。GitHub Actions は次の実行から反映されます。
   - **GCP Secret Manager を読むサービスは手動で再起動**しないと新しいキーを使いません。
6. すべてのサービスを再デプロイしたら、古いキーをいま無効化するか尋ねます。そうでなければ、デプロイを済ませてから：

```bash
rekey revoke shop.openai
```

- まだ古い値を持つ使用先があると無効化を拒否します。確認するのは変数であって、動いているサービスが読み込んだ値ではないので、無効化はデプロイのあとに行ってください。
- 同じサービスのキーがある場所はすべて確認します。分けたりコピーしたりしたキーは、別の名前で古い値を持ち続けるからです。読めない場所（Vercel の sensitive 変数、GitHub・Supabase の secrets）は一覧を示し、無効化の前に確認します（既定：いいえ）。
- 無効化 API のないサービスでは、古いキーの末尾 4 文字を示してページを開きます。
- 一部の使用先に書き込めなくても残りは続行し、最後に書き直すコマンドを示します。

### 2 段階で

変える前に確認したいときは、先に発行し、反映はあとで行います。

```bash
rekey issue project:shop     # 新しいキーを 1Password にだけ保存。使用先は変えません
rekey apply project:shop     # すべての使用先に反映し、再デプロイはひとつずつ尋ねます
```

### うまくいかないとき

- **途中で止まった：** 同じコマンドをもう一度実行します。終わったキーは飛ばし、ローテーション済みのキーは古いキーを無効化するまで再ローテーションしません。
- **間違った値が入った**（ログイン用のコード、別のキー）：`rekey rotate <キー> --redo` で新しいキーを作り直します。無効化する対象は元の古いキーのままです。
- **無効化の前に戻したい：** `rekey undo <キー>` がすべての場所を古いキーに戻し、サービスの再デプロイ後に新しいキーを削除します。

## 複数のキーをまとめて

```bash
rekey rotate project:shop                  # ひとつのプロジェクトが使うキー全部（リポジトリ、Railway サービス、Vercel プロジェクト…）
rekey rotate tag:breach-2026               # keys.toml のタグ
rekey rotate 'in:railway/*'                # これらのテンプレートが使うキーすべて
rekey rotate '*.cartesia'                  # 名前のパターン
rekey rotate tag:breach-2026 --only shop   # 絞り込み：プロジェクトやサービス、名前、tag:、in:、project:
```

自動のキーを先に処理し、次にブラウザの手順をサービスごとにまとめ、DB パスワードは最後です。

## 環境ごとに vault ひとつ、プロジェクトごとにキーひとつ

```bash
rekey arrange "Acme - {env}" --dry-run     # 計画を確認
rekey arrange "Acme - {env}"
```

- 各キーを、それを使う環境の vault に移します：`Acme - Prod`、`Acme - Dev`、`Acme - Local`。
- 複数のプロジェクトや環境で共有されたキーは、プロジェクトと環境ごとに分けて `<project>.<service>` と名付けます。次の `rotate` までは同じ値のままで、ローテーション後は漏れたときにひとつのプロジェクトに絞れます。
- 分けないもの：自社サービス間のトークン（`.self.`）、DB パスワード、locked のキー、無効化待ちのキー。
- 1Password のアイテムは移動と名前変更だけで、削除はしません。`git diff` で確認してからコミットしてください。
- rekey 0.3 より前のチームデータはキー名が `<service>.<project>` です。一度だけ `--old-names` を付けると名前を変えます。

## 設定を変える

プラットフォームのテンプレートには通常の設定も入っています。

```bash
# targets/shop/vercel/shop/production.tpl の値を直したら
rekey diff targets/shop/vercel/shop/production.tpl   # 実際の値と比較
rekey sync targets/shop/vercel/shop/production.tpl   # 反映。再デプロイは尋ねます
git commit -am "shop: change APP_URL"
```

`sync all` はすべてのプラットフォームに書き込みます。本当に必要なときだけ使ってください。

## キーを追加する

1. 使うテンプレートに行を追加します。名前は `<project>.<service>`、自社アプリ同士で使うトークンは `<project>.self.<用途>` とします。
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/shop.stripe/credential }}
   ```
2. 値を入れます。すでに使っている値なら `rekey import shop.stripe`、新しく発行するなら `rekey rotate shop.stripe`。
3. `git commit`

使用先から外すには、テンプレートからその行を消すだけです。

## リファレンス

テンプレートはプロジェクトごとのフォルダに置きます：`targets/<プロジェクト>/<種類>/<アドレス>.tpl`。フォルダがプロジェクト（`project:shop`）で、残りが値を書き込む場所です：

**テンプレートのパス = 値を書き込む場所**（`targets/<プロジェクト>/` 配下、`.tpl` は省略）

| パス | 書き込み先 |
|---|---|
| `file/<パス>` | ローカルのファイル（チームデータフォルダの親フォルダが基準） |
| `vercel/<プロジェクト>/<production·preview·development>` | Vercel |
| `railway/<プロジェクト>/<環境>/<サービス>` | Railway |
| `supabase/<project ref>` | Supabase Edge Function secrets |
| `gcp/<プロジェクト>` | GCP Secret Manager |
| `github/<owner>/<repo>[/<環境>]` | GitHub Actions secrets |
| `fly/<アプリ>`、`worker/<名前>` | Fly、Cloudflare Worker |

テンプレートにある変数だけを書き込みます。書き込み先のほかの変数には触れません。ほかのサービスを参照する Railway の変数（`${{ api.OPENAI_API_KEY }}`）は上書きしません。rekey は止まってその旨を示します。

**キー名**：`<project>.<service>[.<用途>]`。キーの発行方法はサービスで決まります（`shop.openai` → OpenAI）。`self` は rekey が生成するもの、`other` は人がブラウザで発行するものです。

**keys.toml** には例外だけを書きます。

```toml
["shop.self.data-master-key"]
locked = "理由"                 # rotate がスキップ（--force のみで上書き）
note = "ローテーション前のメモ"   # rotate と where で表示
tags = ["check", "retire"]      # check：rotate がスキップ / retire：all から除外
page = "https://…"              # ブラウザ手順で開くページ
```

項目名は `["名前"]` です。同じ名前が 2 つの保管庫で別のキーなら `["保管庫/名前"]` と書きます。

**管理者キー**：`<チーム> - Admin` の保管庫（`<チーム> - Prod` と並べ、共有はできるだけ少人数に）に `rekey.openai-admin`、`rekey.cloudflare-admin`、`rekey.resend-admin`、`rekey.anthropic-admin`（無効化用）があれば、そのサービスを自動で処理します。`rekey setup` が登録を手伝います。

**環境変数**：`REKEY_HOME`（チームデータのフォルダ。既定は現在の場所から上にたどって最初に `targets/` か `keys.toml` がある場所）、`REKEY_ROOT`（`file/` の基準フォルダ。既定は `REKEY_HOME` の親）、`REKEY_STORE=file:<パス>`（1Password の代わりにファイル、テスト用）、`REKEY_NO_BROWSER=1`、`REKEY_LANG`（en、ko、zh、ja、es）
