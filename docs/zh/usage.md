# 使用方法

在团队数据文件夹内运行命令。会修改内容的命令（`rotate`、`revoke`、`sync`、`import`）加上 `--dry-run` 时只预览，不做修改。

## 生成本地 .env

```bash
rekey sync targets/file/shop/web/.env.local.tpl
```

- 密钥从 1Password 填入。文件中的其他行保持不变。
- 本地模板里**只有密钥**。端口等本地配置请自己填写，或参考项目的 `.env.example`。
- 团队共用的本地配置，在模板中加一行 `KEY=值`，下次 `sync` 起会一起写入。

## 从现有 .env 生成模板

```bash
rekey init ~/code/shop/web/.env.local                   # 一个文件
rekey init ~/code/shop --with-settings                   # 文件夹下所有 .env，包含普通配置
```

- 密钥会变成 `{{ op://… }}` 引用。如果某个值已经是模板中的密钥，就沿用那个密钥。
- 模板已存在时，只追加缺少的变量，你改过的行保持不变。
- 不加 `--with-settings` 时，本地模板不包含普通配置（端口、URL 等）。
- 然后用 `rekey import` 把新值存入 1Password。

## 查找密钥

```bash
rekey ls                     # 全部：服务、签发方式、使用处数量、标签
rekey ls 'openai.*'          # 部分
rekey where openai.shop      # 使用这个密钥的模板和变量
```

## 轮换密钥

```bash
rekey rotate openai.shop
```

1. 准备检查：缺少的登录等当场解决。
2. 显示将要做的事，询问是否开始。
3. 获取新密钥：
   - **自动：** 通过 API 签发或本地生成。失败时（例如没有权限）会说明原因并转到浏览器。
   - **浏览器：** 页面打开后，在名称栏按 ⌘V（名称已复制到剪贴板）→ 创建 → **复制**新密钥。一复制就会继续。按 `s` 跳过，按 `q` 停止。
   - 复制了旧密钥或其他服务的密钥会提示你。新密钥不可用时可以重新复制。
4. 保存到 1Password。旧值会保留到吊销为止。
5. 更新所有使用处。Vercel production 和 Railway 会重新部署，并等待部署正常。
   - Supabase Edge Function、Fly、Worker 立即生效。GitHub Actions 从下次运行开始生效。
   - **读取 GCP Secret Manager 的服务需要手动重启**才会使用新密钥。
6. 询问是否现在吊销旧密钥。想再观察一下就选 N，之后再吊销：

```bash
rekey revoke openai.shop
```

- 如果还有地方在用旧值，吊销会停止，并给出要运行的命令。
- 对没有吊销 API 的服务，rekey 会显示旧密钥的最后 4 位并打开页面。
- 中途中断时，重新运行同一命令即可从剩下的部分继续。已轮换的密钥在旧密钥吊销前不会再次轮换。
- 部分使用处写入失败时，其余照常进行，最后会给出重新写入的命令。

## 一次处理多个密钥

```bash
rekey rotate 'cartesia.*'              # 按名称
rekey rotate tag:breach-2026           # 按 keys.toml 中的标签
rekey rotate 'in:vercel/shop/*'        # 这些模板用到的全部密钥
```

自动的先处理，浏览器步骤放在最后，并按服务分组。

## 修改配置

平台模板中也包含普通配置。

```bash
# 修改 targets/vercel/shop/production.tpl 后
rekey diff targets/vercel/shop/production.tpl            # 与线上值比较
rekey sync targets/vercel/shop/production.tpl --deploy   # 写入并重新部署
git commit -am "shop: change APP_URL"
```

`sync all` 会写入所有平台，请只在确实需要时使用。

## 添加新密钥

1. 在需要它的模板里加一行。密钥命名为 `<服务>.<项目>`，自家应用之间共用的令牌命名为 `self.<项目>.<用途>`。
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/stripe.shop/credential }}
   ```
2. 设置值：已经在用的值用 `rekey import stripe.shop`，要新签发用 `rekey rotate stripe.shop`。
3. `git commit`

不再在某处使用时，删除那一行即可。

## 参考

**模板路径 = 值写入的地方**（`targets/` 之下，省略 `.tpl`）

| 路径 | 目标 |
|---|---|
| `file/<路径>` | 本地文件（以团队数据文件夹的上一级为基准） |
| `vercel/<项目>/<production·preview·development>` | Vercel |
| `railway/<项目>/<环境>/<服务>` | Railway |
| `supabase/<project ref>` | Supabase Edge Function secrets |
| `gcp/<项目>` | GCP Secret Manager |
| `github/<owner>/<repo>[/<环境>]` | GitHub Actions secrets |
| `fly/<应用>`、`worker/<名称>` | Fly、Cloudflare Worker |

只写入模板中列出的变量，目标中的其他变量不受影响。

**keys.toml** 只记录例外：

```toml
["self.shop.data-master-key"]
locked = "原因"                 # rotate 跳过（只有 --force 可覆盖）
note = "轮换前要看的备注"        # 在 rotate 和 where 中显示
tags = ["check", "retire"]      # check：rotate 跳过 / retire：不包含在 all 中
page = "https://…"              # 浏览器步骤要打开的页面
```

**管理员密钥**：在同一个 vault 中有 `rekey.openai-admin`、`rekey.cloudflare-admin`、`rekey.resend-admin`、`rekey.anthropic-admin`（用于吊销）条目时，这些服务会自动处理。`rekey setup` 会帮你添加。

**环境变量**：`REKEY_HOME`（团队数据文件夹；默认是从当前位置向上找到的第一个含有 `targets/` 或 `keys.toml` 的文件夹）、`REKEY_ROOT`（`file/` 的基准文件夹，默认是 `REKEY_HOME` 的上一级）、`REKEY_STORE=file:<路径>`（用文件代替 1Password，用于测试）、`REKEY_NO_BROWSER=1`、`REKEY_LANG`（en、ko、zh、ja、es）
