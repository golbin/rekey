# 平台被入侵了

Vercel、Railway、Supabase 等平台通知"保存的环境变量可能已泄露"。

**1. 选出该平台上的密钥。**

```bash
rekey ls 'in:railway/*'        # 按平台改为 vercel/*、supabase/*、gcp/* …
```

列表为空或看起来不全时，重新从平台读取以补全模板。已有的模板和名称不会改变。

```bash
rekey init --vault "Acme - Prod" --source railway
```

如果曾为了部署把整个本地 .env 上传到该平台，那个 .env 里的密钥也在范围内。追加选择即可：

```bash
rekey ls 'in:railway/*' 'in:file/shop/api/*'
```

**2. 用同样的选择进行轮换。** 密钥很多时，一次处理一个项目：

```bash
rekey rotate 'in:railway/*' 'in:file/shop/api/*' --only project:shop
```

自动的处理完后接着是浏览器步骤。被问到时重新部署（或用平常的方式），然后立即吊销：`rekey revoke 'in:railway/*' 'in:file/shop/api/*'`。

在 Railway 上，引用其他服务的变量（`${{ api.KEY }}`）跟随那个服务：轮换源头，两边都重新部署。

**3. 平台侧的清理**
- 同时轮换该平台的账号令牌和项目令牌（CI 使用的那些），通常在 `github/…` 模板中。
- 检查该平台的 GitHub 应用权限（GitHub → Settings → Applications）。
- 删除不再使用的项目。
