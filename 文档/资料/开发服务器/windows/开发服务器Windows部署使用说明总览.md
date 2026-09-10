# 开发服务器 Windows 部署使用说明总览

> mjw Windows 开发服务器部署总览 · 部署顺序与运维入口

[文档首页](../../../文档首页.md) › [资料](../../) › [开发服务器](../linux/开发服务器部署使用说明总览.md) › Windows　|　[相关：远程控制部署使用说明 →](远程控制部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

本文档是 Windows 开发服务器 **mjw**（Windows 11 专业版笔记本）的部署总览：
定位与职责、硬件配置、端口规划、远程通道、常驻策略与运维入口。
每项部署的详细步骤、调试记录与排障经验单独成文（见[第 6 节](#docs)），本文档只做汇总与导航。

**取值说明**：本文档中 `<mjw-IP>`、`<账号>` 等占位符的具体值见《[本地资源](../../../用户文档/本地资源.md)》（已 gitignore，不入库）。

部署依据《[开发部署规划](../../../规划/开发部署规划.md)》；mjw 与现有 mjbk / mjpc 的分工前提见该规划。

## 2. 环境概览 <a id="env"></a>

| 机器 | 系统                                   | 角色                                               |
| ---- | -------------------------------------- | -------------------------------------------------- |
| mjbk | Ubuntu 24.04.4 LTS（桌面版）           | 开发服务器（常驻服务，见《[开发服务器部署使用说明总览](../linux/开发服务器部署使用说明总览.md)》） |
| mjpc | Ubuntu 26.04.1 LTS（GNOME，Wayland）   | 开发机（本地编码、AI 助手、文档）                  |
| mjw  | Windows 11 专业版（Build 26200）       | Windows 开发服务器 / 本地模型机（GPU 推理）        |

### 2.1 已就绪项 <a id="env-ready"></a>

- 系统：Windows 11 专业版（Build 26200），静态 IP `<mjw-IP>`（路由器已按主机名绑定保留）
- 远程通道：WinRM（HTTP 5985）+ RDP（3389），防火墙均限制为内网网段
- 显卡：NVIDIA RTX 3070 Laptop GPU 8GB（本地模型 / 识图 / 翻译推理可用）
- 常驻策略：合盖不休眠、禁睡眠、休眠关闭；网卡 WOL 已验证（2026-09-06：S3 睡眠后魔术包唤醒成功，见《[远程控制部署使用说明](远程控制部署使用说明.md)》第 6 节）
- 管理员账号：`<账号>`（与 mjbk/mjpc 同用户名口径，密码见《本地资源》）
- PowerShell：**7.6.6**（2026-09-10 MSI 静默安装，`C:\Program Files\PowerShell\7\pwsh.exe` 已入 PATH；系统自带 Windows PowerShell 5.1 保留并存。安装实录：ghfast 加速下载官方 MSI（112 MB）→ `msiexec /i /quiet /norestart ADD_PATH=1` 退出码 0）
- DSH：**deepseek-harness 0.1.5-alpha.2**（源码 `C:\Users\minjian\develop\deepseek-harness`，install/build 完成；桌面「启动/停止 dsh web.cmd」手动启停；web 仅绑 127.0.0.1——官方禁止 `--host 0.0.0.0`，远程用 RDP 后本机浏览器访问。详见《[deepseek_harnessWindows部署使用说明](deepseek_harnessWindows部署使用说明.md)》）

## 3. 硬件配置 <a id="hardware"></a>

| 项       | 配置                                                         |
| -------- | ------------------------------------------------------------ |
| 机型     | 机械革命 MECHREVO 泰坦 Taitan Series GM7MG7M                 |
| 处理器   | Intel Core i7-10875H @ 2.30 GHz，8 核 16 线程                |
| 内存     | 32 GB                                                        |
| 显卡     | Intel UHD Graphics（核显）+ NVIDIA GeForce RTX 3070 Laptop GPU 8 GB GDDR6（`nvidia-smi` 确认） |
| 硬盘     | 希捷 ST2000LM015 2 TB（HDD）<br>梵想 Fanxiang S790 2 TB（NVMe SSD） |
| 有线网卡 | Realtek Gaming 2.5GbE（MAC 见《本地资源》，WOL 有线通道）    |
| 无线网卡 | Intel Wi-Fi 6 AX201                                          |

## 4. 端口规划 <a id="ports"></a>

| 端口 | 服务          | 说明                               |
| ---- | ------------- | ---------------------------------- |
| 5985 | WinRM HTTP    | 远程命令行（PowerShell Remoting）  |
| 3389 | RDP           | 远程桌面 GUI                       |

> Windows 防火墙对上述端口仅放行内网网段（见《[远程控制部署使用说明](远程控制部署使用说明.md)》第 3 节）。不启用 Windows 内置 OpenSSH（上次使用时部分命令执行异常，Windows 侧远程一律走 WinRM）。

## 5. 远程通道 <a id="remote"></a>

mjw 的远程控制（WinRM + RDP）完整配置、客户端工具、验证方法与历史排障记录见《[远程控制部署使用说明](远程控制部署使用说明.md)》：

- **WinRM（HTTP 5985）**：`<账号>` / 密码见《本地资源》，mjpc 侧以 pywinrm `ntlm` 认证连接，已联测通过
- **RDP（3389）**：远程桌面 GUI，已验证端口可连
- 账号归属：`Remote Management Users` + `Administrators` 本地组

## 6. 部署说明文档索引 <a id="docs"></a>

本目录下已落地的 Windows 侧部署文档：

- [远程控制部署使用说明](远程控制部署使用说明.md)：WinRM + RDP 部署、客户端使用、验证与排障记录
- [deepseek_harnessWindows部署使用说明](deepseek_harnessWindows部署使用说明.md)：DSH（deepseek-harness）在 mjw 的部署、桌面启停、访问边界与排障（2026-09-10）

## 7. 关联文档 <a id="related"></a>

- 《[远程控制部署使用说明](远程控制部署使用说明.md)》：mjw 远程控制详细部署与排障
- 《[本地资源](../../../用户文档/本地资源.md)》：机器硬件与账号（已 gitignore，不入库）
- 《[开发服务器部署使用说明总览](../linux/开发服务器部署使用说明总览.md)》：mjbk 开发服务器总览（Ubuntu）
- 《[开发机部署使用说明总览](../../开发机/开发机部署使用说明总览.md)》：mjpc 开发机总览
- 《[开发部署规划](../../../规划/开发部署规划.md)》：整体部署方案与机器分工
- 《[文档生成规范](../../../规范/文档生成规范.md)》与《[命名规范](../../../规范/命名规范.md)》：本文档遵循的规范

> 依《文档生成规范》编写 · mjw 部署随进度逐项补充