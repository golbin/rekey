# 有成员离开了

**1. 先收回权限**，再更换密钥：
- 1Password vault、GitHub 组织、各平台（Vercel、Railway、Supabase、GCP…）的团队

**2. 轮换他能看到的密钥。**

```bash
rekey rotate all                                  # 他有整个 vault 的权限
rekey rotate 'in:vercel/shop/*' 'in:file/shop/*'  # 他只参与了部分项目
```

密钥很多时，可以先让自动的部分完成，在浏览器步骤按 `q` 停止，之后用 rekey 给出的命令继续。

**3. 清理他创建的密钥。** 在各服务的密钥列表中删除他创建的密钥。rekey 创建的密钥名以 `rekey-` 开头。
