# 準備

rekey は**ツール**（このリポジトリ）と**チームデータ**（`targets/` と `keys.toml` を置くチームの非公開リポジトリ）を分けて使います。チームデータにキーの値はありませんが、インフラ構成が分かるので非公開にしてください。

## 全員（10 分）

**1. ツールとチームデータを取得する。** チームデータは各プロジェクトと**同じフォルダ**に置きます。`targets/file/…` のパスはここを基準にします。

```bash
git clone https://github.com/golbin/rekey.git ~/tools/rekey
git clone <チームデータのリポジトリ> ~/code/keys
```

`~/.zshrc`（または `~/.bashrc`）に追加して、新しいターミナルを開きます。

```bash
export REKEY_HOME=~/code/keys
alias rekey=~/tools/rekey/rekey
```

**2. 1Password CLI。**

```bash
brew install 1password-cli        # Linux: https://developer.1password.com/docs/cli/get-started
```

1Password アプリ → 設定 → 開発者 → **「1Password CLI と連携」** をオンにします。チームの vault が見えなければ管理者に権限を依頼してください。

**3. 確認。**

```bash
rekey ls                       # キー一覧が出れば rekey は OK
op vault get "Acme - Prod"     # vault の情報が出れば 1Password は OK
```

これで[ローカルの .env を作る](usage.md#ローカルの-env-を作る)ことができます。

## キーをローテーションする人（さらに 5 分）

```bash
rekey setup
```

足りないものを一つずつ示し、その場で解決します。
- 使っているプラットフォーム CLI（`vercel`、`railway`、`supabase`、`gcloud`、`gh` など）のログイン：rekey がログインコマンドを実行するので、ブラウザで承認するだけです。
- 管理者キー（任意）：あると OpenAI・Cloudflare・Resend のキーをブラウザなしで自動発行します。

準備完了と出れば終わりです。以後も `rotate` は開始のたびに同じ確認をします。

## チームで初めて導入する場合

空のチームデータリポジトリで一度だけ実行します。

```bash
mkdir ~/code/keys && cd ~/code/keys && git init
rekey init --vault "Acme - Prod" --source vercel --source supabase --source railway --source gcp:<プロジェクト>
rekey import all        # いま使っている値を 1Password に保存
git add . && git commit -m "rekey: initial templates"
```

- `init` は `~/code` 配下の .env ファイルと各プラットフォームを読んでテンプレートを作ります。同じ値はひとつのキーにまとめます。
- 複数のプロジェクトを入れたフォルダ（例：`~/code/clients/a`、`~/code/clients/b`）があれば `--group-dirs clients` を付けてください。その中のフォルダ名でキーに名前が付きます。
- 既存のテンプレートとキー名は変更しないので、あとから `--source` を追加して再実行しても安全です。
- 作成後は `git diff` で確認してください。`# … 추정`（「推定」）のコメントが付いた行は、Vercel で値を読めず名前で対応付けた変数です。
