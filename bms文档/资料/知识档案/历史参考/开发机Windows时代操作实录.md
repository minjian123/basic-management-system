# 开发机 Windows 时代操作实录（历史参考）

> 开发机 mjpc 换装 Ubuntu 前的 Windows 11 操作实录归档 · **辅助参考文档，不作为现行操作依据**

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › 历史参考 › 开发机 Windows 时代操作实录

---

## 1. 背景 <a id="background"></a>

开发机 mjpc 曾运行 Windows 11（专业版），2026-08 下旬换装 **Ubuntu 26.04.1 LTS**（GNOME，Wayland），
换装后开发机各实录文档自 2026-08-28 起均按 Ubuntu 记录（本机核实口径见《[开发机部署使用说明总览](../../开发机/开发机部署使用说明总览.md)》）。

换装前散见于正式文档中的 **Windows/PowerShell 版操作**已从正式文档移出，归集于本文档存档备查。
正式文档中的对应小节均已改写为现行 Linux/Ubuntu 口径。

## 2. mjbk SSH 免密配置（mjpc 侧，Windows PowerShell 版） <a id="ssh-keys"></a>

**出处**：《[Ubuntu安装部署使用说明](../../工具/Ubuntu安装部署使用说明.md)》「SSH 免密登录」节（2026-08-15 mjbk 装机实录，当时 mjpc 为 Windows 11）；
现行 Linux 版见该文档 6.1 节。

原文操作：

1. 若无密钥先生成：`ssh-keygen -t ed25519`（一路回车即可，默认存 `~/.ssh/`）。
2. 把公钥装到 mjbk：

```powershell
type $env:USERPROFILE\.ssh\id_ed25519.pub | ssh <SSH账号>@<mjbk-IP> "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys && chmod 700 ~/.ssh && chmod 600 ~/.ssh/authorized_keys"
```

## 3. mjbk 端口连通单端口验证模板（PowerShell 版） <a id="port-probe"></a>

**出处**：mjbk《[防火墙部署使用说明](../../开发服务器/linux/防火墙部署使用说明.md)》「验证」节（验证模板，当时 mjpc 为 Windows）；
现行 Linux 版见该文档第 4 节。

原文模板：

```powershell
$c = New-Object Net.Sockets.TcpClient
$t = $c.BeginConnect('<mjbk-IP>', 8060, $null, $null)
$t.AsyncWaitHandle.WaitOne(1500) -and $c.Connected   # True=通 False=不通
$c.Close()
```

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 归集 2026-09-10，mjpc 换装 Ubuntu 后由各正式文档移出存档
