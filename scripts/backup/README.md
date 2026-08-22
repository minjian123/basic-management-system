# scripts/backup — 开发服务器备份脚本

部署位置：mjbk `~/deploy/backup/`（本目录为版本管理源，修改后 scp 同步）。

## 组件与分工

| 脚本 | 覆盖 | cron |
| --- | --- | --- |
| `backup_daily.sh` | MySQL 全量（含 zentao/kiwi/bms_dev）、PostgreSQL 全量、达梦 DM8 dexp、GitLab（数据 + config） | 每日 02:30（总控串行） |
| `backup_zentao.sh`（仅 mjbk 本地，历史已部署） | 禅道库细粒度 dump + /data 卷 tar | 每日 02:00 |

- 凭据：读 mjbk `~/deploy/.env`（MYSQL_ROOT_PASSWORD / POSTGRES_PASSWORD / DM8_SYSDBA_PASSWORD），不硬编码。
- 落位：`/mnt/data/backup/{mysql,postgres,dameng,gitlab,zentao}/`（HDD 机械盘，与 NVMe 数据盘分盘）。
- 保留：7 天（`find -mtime +7 -delete`）。
- 日志：`/mnt/data/backup/cron.log`；任一组件 FAIL 总控以非零退出。
- GitLab 数据备份产物先落 NVMe（容器挂载 `/mnt/ssd2t/gitlab/data/backups/`），脚本内 `docker cp` 拷出至 HDD 并清理容器内侧本。

## 恢复演练

每季度一次，从备份恢复验证并登记（《开发部署规划》第 8 节口径）。要点：

- MySQL：`gunzip < all_*.sql.gz | docker exec -i bms-mysql mysql --user=root -p` 恢复到临时库抽查表行数。
- PostgreSQL：`gunzip < all_*.sql.gz | docker exec -i bms-postgres psql -U postgres <目标库>`。
- 达梦：dexp 配对 dimp 导入临时模式抽查。
- GitLab：按官方恢复流程 `gitlab-backup restore BACKUP=<时间戳>` + 解开 config 包覆盖 `/etc/gitlab`（需停服务），演练在低峰执行。
