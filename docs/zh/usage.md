# 使用方法

在团队数据文件夹内运行命令。会修改内容的命令（`rotate`、`issue`、`revoke`、`sync`、`import`、`arrange`）加上 `--dry-run` 时只预览，不做修改。

## 生成本地 .env

```bash
rekey sync targets/shop/file/shop/web/.env.local.tpl
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
- 然后用 `rekey arrange "Acme - {env}"` 把新密钥放进正确的 vault，再用 `rekey import` 把它们的值存入 1Password。

## 查找密钥

```bash
rekey ls                     # 全部：服务、签发方式、使用处数量、标签
rekey ls project:shop        # 一个项目
rekey ls '*.openai'          # 一个服务
rekey where shop.openai      # 使用这个密钥的模板和变量
```

## 轮换密钥

```bash
rekey rotate shop.openai
```

1. 准备检查：缺少的登录等当场解决。
2. 显示将要做的事，询问是否开始。
3. 获取新密钥：
   - **自动：** 通过 API 签发或本地生成。失败时（例如没有权限）会说明原因并转到浏览器。
   - **浏览器：** 页面打开并提示要点哪里。在名称栏按 ⌘V（名称已复制到剪贴板），给新密钥和旧密钥相同的权限（会显示旧密钥的最后 4 位），创建后**复制**。一复制就会继续。按 `s` 跳过，按 `q` 停止。
   - 登录验证码、旧密钥或其他服务的密钥不会被当作新密钥。
   - 数据库密码放在最后：新密码一保存，旧密码就失效。
4. 保存到 1Password。旧值会保留到吊销为止。
5. 更新所有使用处。然后逐个服务询问是否现在重新部署（默认：否）。如果重启会中断进行中的会话，选 N，之后用平常的方式或 `rekey deploy <模板>` 部署。
   - Supabase Edge Function、Fly、Worker 立即生效。GitHub Actions 从下次运行开始生效。
   - **读取 GCP Secret Manager 的服务需要手动重启**才会使用新密钥。
6. 所有服务都重新部署后，会询问是否现在吊销旧密钥。否则，在你部署完之后：

```bash
rekey revoke shop.openai
```

- 只要还有地方保存着旧值，吊销就会拒绝执行。它检查的是变量，而不是运行中的服务已加载的值，所以请在部署之后再吊销。
- 它会检查所有放有同一服务密钥的地方，因为拆分或复制出来的密钥会以别的名字保留旧值。无法读取的地方（Vercel sensitive 变量、GitHub 和 Supabase secrets）会列出来，并在吊销前询问（默认：否）。
- 对没有吊销 API 的服务，rekey 会显示旧密钥的最后 4 位并打开页面。
- 部分使用处写入失败时，其余照常进行，最后会给出重新写入的命令。

### 分两步

想在改动前先确认，可以先签发，之后再替换到各处：

```bash
rekey issue project:shop     # 新密钥只存入 1Password；不改动任何使用处
rekey apply project:shop     # 写入所有地方，然后逐个询问是否重新部署
```

### 出问题时

- **中途停下：** 再次运行同一命令即可。已完成的密钥会跳过；已轮换的密钥在旧密钥吊销前不会再次轮换。
- **填错了值**（登录验证码、错误的密钥）：`rekey rotate <密钥> --redo` 重新获取新密钥；要吊销的仍是原来的旧密钥。
- **吊销前想回退：** `rekey undo <密钥>` 会把所有地方改回旧密钥，并在服务重新部署后删除新密钥。

## 一次处理多个密钥

```bash
rekey rotate project:shop                  # 一个项目用到的全部密钥（仓库、Railway 服务、Vercel 项目…）
rekey rotate tag:breach-2026               # 按 keys.toml 中的标签
rekey rotate 'in:railway/*'                # 这些模板用到的全部密钥
rekey rotate '*.cartesia'                  # 按名称
rekey rotate tag:breach-2026 --only shop   # 缩小范围：项目或服务、名称、tag:、in:、project:
```

自动的先处理，接着是按服务分组的浏览器步骤，数据库密码放在最后。

## 每个环境一个 vault，每个项目一个密钥

```bash
rekey arrange "Acme - {env}" --dry-run     # 查看计划
rekey arrange "Acme - {env}"
```

- 每个密钥移到使用它的环境对应的 vault：`Acme - Prod`、`Acme - Dev` 或 `Acme - Local`。
- 被多个项目或环境共用的密钥会按项目和环境拆开，命名为 `<project>.<service>`。在下次 `rotate` 之前各份的值相同；轮换之后，泄露就能指向一个项目。
- 不拆的：自家服务之间的令牌（`.self.`）、数据库密码、locked 密钥，以及等待吊销的密钥。
- 1Password 条目只会移动和改名，不会删除。用 `git diff` 检查后再提交。
- rekey 0.3 之前的团队数据把密钥命名为 `<service>.<project>`；加一次 `--old-names` 即可改名。

## 修改配置

平台模板中也包含普通配置。

```bash
# 修改 targets/shop/vercel/shop/production.tpl 后
rekey diff targets/shop/vercel/shop/production.tpl   # 与线上值比较
rekey sync targets/shop/vercel/shop/production.tpl   # 写入；会询问是否重新部署
git commit -am "shop: change APP_URL"
```

`sync all` 会写入所有平台，请只在确实需要时使用。

## 添加新密钥

1. 在需要它的模板里加一行。密钥命名为 `<project>.<service>`，自家应用之间共用的令牌命名为 `<project>.self.<用途>`。
   ```
   STRIPE_SECRET_KEY={{ op://Acme - Prod/shop.stripe/credential }}
   ```
2. 设置值：已经在用的值用 `rekey import shop.stripe`，要新签发用 `rekey rotate shop.stripe`。
3. `git commit`

不再在某处使用时，删除那一行即可。

## 参考

模板按项目放在各自的文件夹里：`targets/<项目>/<类型>/<地址>.tpl`。文件夹就是项目（`project:shop`），其余部分表示值写入的地方：

**模板路径 = 值写入的地方**（`targets/<项目>/` 之下，省略 `.tpl`）

| 路径 | 目标 |
|---|---|
| `file/<路径>` | 本地文件（以团队数据文件夹的上一级为基准） |
| `vercel/<项目>/<production·preview·development>` | Vercel |
| `railway/<项目>/<环境>/<服务>` | Railway |
| `supabase/<project ref>` | Supabase Edge Function secrets |
| `gcp/<项目>` | GCP Secret Manager |
| `github/<owner>/<repo>[/<环境>]` | GitHub Actions secrets |
| `fly/<应用>`、`worker/<名称>` | Fly、Cloudflare Worker |

只写入模板中列出的变量，目标中的其他变量不受影响。引用其他服务的 Railway 变量（`${{ api.OPENAI_API_KEY }}`）不会被覆盖：rekey 会停下并说明。

**密钥名**：`<project>.<service>[.<用途>]`。服务决定密钥的签发方式（`shop.openai` → OpenAI）；`self` 表示由 rekey 生成，`other` 表示由人在浏览器中签发。

**keys.toml** 只记录例外：

```toml
["shop.self.data-master-key"]
locked = "原因"                 # rotate 跳过（只有 --force 可覆盖）
note = "轮换前要看的备注"        # 在 rotate 和 where 中显示
tags = ["check", "retire"]      # check：rotate 跳过 / retire：不包含在 all 中
page = "https://…"              # 浏览器步骤要打开的页面
```

条目名是 `["名称"]`；同一名称在两个保险库中是不同密钥时，写成 `["保险库/名称"]`。

**管理员密钥**：在任意一个 vault（通常是 Prod）中有 `rekey.openai-admin`、`rekey.cloudflare-admin`、`rekey.resend-admin`、`rekey.anthropic-admin`（用于吊销）条目时，这些服务会自动处理。`rekey setup` 会帮你添加。

**环境变量**：`REKEY_HOME`（团队数据文件夹；默认是从当前位置向上找到的第一个含有 `targets/` 或 `keys.toml` 的文件夹）、`REKEY_ROOT`（`file/` 的基准文件夹，默认是 `REKEY_HOME` 的上一级）、`REKEY_STORE=file:<路径>`（用文件代替 1Password，用于测试）、`REKEY_NO_BROWSER=1`、`REKEY_LANG`（en、ko、zh、ja、es）
