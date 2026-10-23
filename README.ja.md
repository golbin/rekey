[English](README.md) · [한국어](README.ko.md) · [中文](README.zh.md) · **日本語** · [Español](README.es.md)

# rekey

API キーをコマンドひとつで再発行し、使っているすべての場所（.env、Vercel、Railway、Supabase、GCP、GitHub…）に反映して、古いキーを無効化します。

```bash
pipx install git+https://github.com/golbin/rekey   # インストール
rekey rotate project:shop   # 新しいキーを発行 → すべての使用先を更新 → 各サービスの再デプロイはタイミングを選べる
rekey revoke project:shop   # 古いキーを無効化
```

- **忘れていたキーまで見つけます。** `rekey init` は記憶に頼らず、すべての .env ファイルと Vercel・Railway・Supabase・GCP を直接読み、同じ値をひとつにまとめます。誰も覚えていないプロジェクトを含め 20 か所にコピーされたキーも 1 件に整理されます。rekey が読めない場所（チームメンバーの PC、外部サービスの管理画面）は、テンプレートに一行書いておけば二度と忘れません。
- 各サービスに詳しくなくても大丈夫です。API で発行できるキーは自動で処理します。それ以外は rekey が該当ページを開くので、キーを作って**コピー**するだけです。
- キーの値は画面に表示されません。1Password にだけ保存されます。
- Python 3.11 以上、標準ライブラリのみ。
- メッセージはシステムの言語に合わせて表示されます（English、한국어、中文、日本語、Español）。`REKEY_LANG=ja` で指定もできます。

## 仕組み

| 何を | どこに |
|---|---|
| キーの値 | 1Password：環境ごとに vault ひとつ（`Acme - Prod`、`Acme - Dev`、`Acme - Local`）、1 アイテム = 1 キー、名前は `<project>.<service>` |
| 各キーの使用先と通常の設定値 | チームの非公開リポジトリの `targets/<project>/**.tpl` |
| 例外情報（ロック・タグ・メモ） | チームの非公開リポジトリの `keys.toml` |

テンプレートは 1Password 標準の書式そのままで、ファイルのパスが値を書き込む場所を表します。

```
# targets/shop/vercel/shop/production.tpl  →  Vercel プロジェクト "shop" の production 環境
APP_URL=https://shop.example.com
OPENAI_API_KEY={{ op://Acme - Prod/shop.openai/credential }}
```

## ガイド

0. [チームデータのサンプル](https://github.com/golbin/rekey-example)：どんな形か見てから **Use this template** で開始
1. [準備](docs/ja/setup.md)：10 分
2. [使い方](docs/ja/usage.md)
3. 状況別：[キーが漏れた](docs/ja/situations/key-leaked.md) · [プラットフォームが侵害された](docs/ja/situations/platform-breach.md) · [メンバーが抜けた](docs/ja/situations/member-left.md)

## 開発

```bash
python3 -m unittest discover -s tests
REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py   # 実際の端末操作を再現（macOS、クリップボードを使用）
```

MIT License
