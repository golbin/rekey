# 准备

rekey 把**工具**（本仓库）和**团队数据**（存放 `targets/`、`keys.toml` 的团队私有仓库）分开。团队数据里没有密钥值，但会暴露基础设施结构，所以请设为私有。

## 所有人（10 分钟）

**1. 安装工具并获取团队数据。** 团队数据放在和各项目**同一个文件夹**里，`targets/file/…` 路径以它为基准。

```bash
brew install pipx                                  # 如果还没有（Linux：https://pipx.pypa.io）
pipx install git+https://github.com/golbin/rekey
git clone <团队数据仓库> ~/code/keys
```

在那个文件夹（或其下任意位置）运行 `rekey`，它会自动找到团队数据。之后用 `pipx upgrade rekey` 更新工具。

**2. 1Password CLI。**

```bash
brew install 1password-cli        # Linux: https://developer.1password.com/docs/cli/get-started
```

在 1Password 应用中：设置 → 开发者 → 打开 **"与 1Password CLI 集成"**。看不到团队的 vault 时，请向管理员申请权限。

**3. 检查。**

```bash
cd ~/code/keys
rekey ls                       # 显示密钥列表：rekey 正常
op vault get "Acme - Prod"     # 显示 vault 信息：1Password 正常
```

到这里就可以[生成本地 .env](usage.md#生成本地-env) 了。

## 如果你负责轮换密钥（再加 5 分钟）

```bash
rekey setup
```

它会列出缺少的东西并当场解决：
- 所用平台 CLI（`vercel`、`railway`、`supabase`、`gcloud`、`gh` 等）的登录：rekey 运行登录命令，你只需在浏览器中批准。
- 管理员密钥（可选）：有了它，OpenAI、Cloudflare、Resend 的密钥无需浏览器即可自动签发。

显示准备完成即可。之后每次 `rotate` 开始时都会做同样的检查。

## 如果团队第一次引入 rekey

可以从[示例仓库](https://github.com/golbin/rekey-example)开始（**Use this template** → 私有仓库），或者在空的团队数据仓库中运行一次：

```bash
mkdir ~/code/keys && cd ~/code/keys && git init
rekey init --vault "Acme - Prod" --source vercel --source supabase --source railway --source gcp:<项目>
rekey import all        # 把当前在用的值存入 1Password
git add . && git commit -m "rekey: initial templates"
```

- `init` 读取 `~/code` 下的 .env 文件和各平台，生成模板。相同的值归为同一个密钥。
- 如果某个文件夹里有多个项目（如 `~/code/clients/a`、`~/code/clients/b`），加上 `--group-dirs clients`，密钥会按其下的文件夹命名。
- 已有的模板和密钥名不会被修改，之后加上更多 `--source` 再运行也是安全的。
- 生成后用 `git diff` 检查。带 `# …: guessed` 注释的行，是 Vercel 中无法读取值、按名称匹配的变量。
