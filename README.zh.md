[English](README.md) · [한국어](README.ko.md) · **中文** · [日本語](README.ja.md) · [Español](README.es.md)

# rekey

一条命令重新签发 API 密钥，更新到所有用到它的地方（.env、Vercel、Railway、Supabase、GCP、GitHub…），并吊销旧密钥。

```bash
pipx install git+https://github.com/golbin/rekey   # 安装
rekey rotate project:shop   # 签发新密钥 → 更新所有使用处 → 由你决定各服务何时重新部署
rekey revoke project:shop   # 吊销旧密钥
```

- **连你忘了的密钥也能找到。** `rekey init` 不靠记忆：它直接读取所有 .env 文件以及 Vercel、Railway、Supabase、GCP，并把相同的值归为一个，所以复制到二十个地方（包括没人记得的项目）的密钥也会整理成一条。rekey 读不到的地方（同事的电脑、第三方后台），在模板里写一行，以后就不会再忘。
- 不需要了解每个服务。能通过 API 签发的密钥会自动处理；其余的，rekey 会打开对应页面，你只需创建密钥并**复制**。
- 密钥值不会显示在屏幕上，只保存在 1Password 中。
- Python 3.11+，只用标准库。
- 提示语言跟随系统语言（English、한국어、中文、日本語、Español），也可以用 `REKEY_LANG=zh` 指定。

## 工作方式

| 内容 | 位置 |
|---|---|
| 密钥值 | 1Password：每个环境一个 vault（`Acme - Prod`、`Acme - Dev`、`Acme - Local`），一个条目 = 一个密钥，命名为 `<project>.<service>` |
| 每个密钥的使用位置和普通配置 | 团队私有仓库中的 `targets/**.tpl` |
| 例外信息（锁定、标签、备注） | 团队私有仓库中的 `keys.toml` |

模板使用 1Password 自己的语法，文件路径就是值要写入的地方。

```
# targets/vercel/shop/production.tpl  →  Vercel 项目 "shop" 的 production 环境
APP_URL=https://shop.example.com
OPENAI_API_KEY={{ op://Acme - Prod/shop.openai/credential }}
```

## 指南

0. [团队数据示例](https://github.com/golbin/rekey-example)：先看看长什么样，再点 **Use this template**
1. [准备](docs/zh/setup.md)：10 分钟
2. [使用方法](docs/zh/usage.md)
3. 场景：[密钥泄露了](docs/zh/situations/key-leaked.md) · [平台被入侵了](docs/zh/situations/platform-breach.md) · [有成员离开了](docs/zh/situations/member-left.md)

## 开发

```bash
python3 -m unittest discover -s tests
REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py   # 模拟真实终端操作（macOS，会使用剪贴板）
```

MIT License
