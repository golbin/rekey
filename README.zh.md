[English](README.md) · [한국어](README.ko.md) · **中文** · [日本語](README.ja.md) · [Español](README.es.md)

# rekey

一条命令重新签发 API 密钥，更新到所有用到它的地方（.env、Vercel、Railway、Supabase、GCP、GitHub…），并吊销旧密钥。

```bash
rekey rotate 'openai.*'   # 签发新密钥 → 更新所有使用处 → 确认重新部署
rekey revoke 'openai.*'   # 吊销旧密钥
```

- 不需要了解每个服务。能通过 API 签发的密钥会自动处理；其余的，rekey 会打开对应页面，你只需创建密钥并**复制**。
- 密钥值不会显示在屏幕上，只保存在 1Password 中。
- Python 3.11+，只用标准库。
- 提示语言跟随系统语言（English、한국어、中文、日本語、Español），也可以用 `REKEY_LANG=zh` 指定。

## 工作方式

| 内容 | 位置 |
|---|---|
| 密钥值 | 1Password（一个条目 = 一个密钥） |
| 每个密钥的使用位置和普通配置 | 团队私有仓库中的 `targets/**.tpl` |
| 例外信息（锁定、标签、备注） | 团队私有仓库中的 `keys.toml` |

模板使用 1Password 自己的语法，文件路径就是值要写入的地方。

```
# targets/vercel/shop/production.tpl  →  Vercel 项目 "shop" 的 production 环境
APP_URL=https://shop.example.com
OPENAI_API_KEY={{ op://Acme - Prod/openai.shop/credential }}
```

## 指南

1. [准备](docs/zh/setup.md)：10 分钟
2. [使用方法](docs/zh/usage.md)
3. 场景：[密钥泄露了](docs/zh/situations/key-leaked.md) · [平台被入侵了](docs/zh/situations/platform-breach.md) · [有成员离开了](docs/zh/situations/member-left.md)

## 开发

```bash
python3 -m unittest discover -s tests
REKEY_TEST_CLIPBOARD=1 python3 -m unittest discover -s tests -p test_interactive.py   # 模拟真实终端操作（macOS，会使用剪贴板）
```

MIT License
