# プラットフォームが侵害された

Vercel、Railway、Supabase などから「保存された環境変数が漏れた可能性がある」と通知を受けた場合です。

**1. そのプラットフォームにあるキーを選ぶ。**

```bash
rekey ls 'in:railway/*'        # プラットフォームに合わせて vercel/*、supabase/*、gcp/* …
```

一覧が空、または足りないように見えるときは、プラットフォームを読み直してテンプレートを補ってください。既存のテンプレートと名前は変わりません。

```bash
rekey init --vault "Acme - Prod" --source railway
```

デプロイのためにローカルの .env を丸ごとそのプラットフォームに上げたことがあれば、その .env のキーも対象です。選択を続けて書けば OK です。

```bash
rekey ls 'in:railway/*' 'in:file/shop/api/*'
```

**2. 同じ選択でローテーションする。** キーが多ければプロジェクトごとに進めます。

```bash
rekey rotate 'in:railway/*' 'in:file/shop/api/*' --only project:shop
```

自動の処理が終わるとブラウザの手順が続きます。聞かれたら再デプロイし（またはいつもの方法で）、すぐに無効化してください：`rekey revoke 'in:railway/*' 'in:file/shop/api/*'`。

Railway でほかのサービスを参照する変数（`${{ api.KEY }}`）は、そのサービスに従います。参照元をローテーションし、両方を再デプロイしてください。

**3. プラットフォーム側の後始末**
- そのプラットフォームのアカウントトークンやプロジェクトトークン（CI が使うもの）もローテーションします。たいてい `github/…` テンプレートにあります。
- そのプラットフォームの GitHub アプリの権限を確認します（GitHub → Settings → Applications）。
- 使っていないプロジェクトは削除します。
