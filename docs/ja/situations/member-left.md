# メンバーが抜けた

**1. まずアクセス権を外します。** キーを変える前に行います。
- 1Password の vault、GitHub の organization、各プラットフォーム（Vercel、Railway、Supabase、GCP…）のチーム

**2. その人が見られたキーをローテーションします。**

```bash
rekey rotate all                                  # vault 全体の権限があった場合
rekey rotate 'in:vercel/shop/*' 'in:file/shop/*'  # 一部のプロジェクトだけ担当していた場合
```

キーが多ければ、自動の分を先に終わらせ、ブラウザの手順で `q` を押して止めても構いません。残りは rekey が示すコマンドで続けます。

**3. その人が作ったキーを片付けます。** 各サービスのキー一覧に、その人が作ったキーが残っていれば削除します。rekey が作ったキーは名前が `rekey-` で始まります。
