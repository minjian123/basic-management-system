# scripts/tools/backup — 开发服务器备份脚本（版本管理源）

脚本实际运行于 mjbk `~/deploy/backup/`；修改流程：改本目录 → scp 同步至 mjbk。

| 脚本 | 覆盖 | cron |
| --- | --- | --- |
| `backup_daily.sh` | MySQL 全量、PostgreSQL 单库、达梦 dexp、GitLab（数据 + config）、Kiwi uploads、百度网盘云同步（加密） | 每日 02:30 |

部署详情、云同步机制（BaiduPCS-Go + 官方客户端凭据提取 + gpg 加密）、解密恢复、
已知限制与踩坑：《[百度网盘云备份部署使用说明](../../文档/资料/开发服务器/百度网盘云备份部署使用说明.md)》。
