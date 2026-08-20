# 达梦 DM8 部署使用说明

> mjbk 信创数据库部署实录 · 2026-08-10

[文档首页](../../文档首页.md) › [资料](../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明](开发服务器部署使用说明.md) › 达梦 DM8 部署使用说明　|　[← 上一个：PostgreSQL](PostgreSQL部署使用说明.md)　|　[下一个：GitLab →](GitLab部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的达梦数据库（DM8）与 MySQL、PostgreSQL 并称「常驻三库」，用于开发联调与 CI 三库方言测试
（《[开发部署规划](../../规划/开发部署规划.md)》4.4）。版本：**DM8（dm8_20260428_x86_Ubuntu22_64）**。
`<mjbk-IP>`、`<SSH账号>` 取值见《[本地资源](../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`（`MJBK_IP` / `MJBK_SSH_USER`）。

## 2. 部署方式说明（原生安装） <a id="plan"></a>

> 原规划以 Docker 镜像（`dmdbms/dm8`）部署，但 2026-08 实测镜像渠道全部不可用：Docker Hub 直连被墙、
> DaoCloud 加速器白名单拒绝该镜像、其余公共镜像站超时/限流，达梦官网也已停止提供 Docker 镜像下载。
> 本机改为**官方安装包原生安装**（Ubuntu 22 版安装包，兼容 Ubuntu 24.04）。

## 3. 安装步骤 <a id="install"></a>

### 3.1 安装包与依赖 <a id="install-pkg"></a>

从达梦官网（需注册账号）下载 `dm8_20260428_x86_Ubuntu22_64.zip`（约 960MB），解压后为 ISO，挂载提取安装程序：

```bash
unzip dm8_20260428_x86_Ubuntu22_64.zip
sudo mkdir -p /mnt/dm8iso
sudo mount -o loop,ro dm8_20260428_x86_Ubuntu22_64.iso /mnt/dm8iso
cp /mnt/dm8iso/DMInstall.bin ~/ && chmod +x ~/DMInstall.bin
```

依赖（Ubuntu 24.04 需补装 `libncurses5`，noble 仓库已移除，从 jammy 下载）：

```bash
sudo apt install -y libaio1t64 libgomp1 libncurses6 libnsl2
curl -sL -o /tmp/libncurses5.deb https://mirrors.tuna.tsinghua.edu.cn/ubuntu/pool/universe/n/ncurses/libncurses5_6.3-2_amd64.deb
sudo apt install -y /tmp/libncurses5.deb
```

> 安装目录 `/opt/dmdbms` 需提前创建并授权普通用户（安装程序校验写入权限）：`sudo mkdir -p /opt/dmdbms && sudo chown -R <SSH账号>:<SSH账号> /opt/dmdbms`。

### 3.2 交互安装应答序列 <a id="install-run"></a>

`DMInstall.bin -i` 为交互安装，全程应答序列（实测 2026-08-10）：

| 提示 | 应答 | 说明 |
| --- | --- | --- |
| 请选择安装语言 | `1` | 简体中文 |
| 是否输入Key文件路径? | `n` | 无 Key，使用默认试用授权（至 2027-04） |
| 是否设置时区? | `y` | 随后从序号列表选时区 |
| 请选择时区 [21] | `21` | 21 = 中国标准时间（GTM+08:00） |
| 请选择安装类型的数字序号 | `1` | 典型安装（所需空间约 1929M） |
| 请选择安装目录 | `/opt/dmdbms` | 默认 `~/dmdbms`，改系统路径 |
| 是否确认安装路径? | `y` | — |
| 是否确认安装?（安装前小结后） | `y` | 最终确认，开始安装 |
| 是否初始化数据库? | `n` | 稍后手动 dminit 初始化 |

> 踩坑：安装脚本逐字符读取应答（read 1 字节），**管道方式（printf | DMInstall.bin）输入耗尽后脚本会 100% CPU 死循环**，
> 且不响应 EOF。必须用 PTY 交互逐句应答，每步确认提示出现后再发送。

### 3.3 root 脚本与服务 <a id="install-root"></a>

```bash
sudo /opt/dmdbms/script/root/root_installer.sh   # 移动 dm_svc.conf、创建并启动 DmAPService
```

## 4. 实例初始化 <a id="instance"></a>

```bash
mkdir -p /opt/dmdbms/data
/opt/dmdbms/bin/dminit PATH=/opt/dmdbms/data INSTANCE_NAME=DMSERVER PORT_NUM=5236 \
  PAGE_SIZE=16 CHARSET=1 TIME_ZONE=+08:00 \
  SYSDBA_PWD="<强密码>" SYSAUDITOR_PWD="<强密码>"
```

> SYSDBA/SYSAUDITOR 密码要求 8-48 位、含大小写字母与数字（本次部署已生成随机密码存入
> `~/deploy/.env` 的 `DAMENG_SYSDBA_PWD` / `DAMENG_SYSAUDITOR_PWD`）。
> PAGE_SIZE=16（16KB 页）、CHARSET=1（UTF-8）。

注册并启动服务（systemd）：

```bash
sudo /opt/dmdbms/script/root/dm_service_installer.sh -t dmserver -p DMSERVER -dm_ini /opt/dmdbms/data/DAMENG/dm.ini
sudo systemctl enable --now DmServiceDMSERVER
```

## 5. 开发库（schema） <a id="schema"></a>

达梦以「模式（schema）」承载库语义（规划 4.4），开发联调库即 `bms_dev` schema：

```sql
CREATE SCHEMA bms_dev;
```

> 踩坑：disql 经管道/文件输入执行 `CREATE SCHEMA` 会挂起（显示 `SQL> 2 3` 后无响应，原因未明），
> 而 SELECT/建表语句正常。本次部署改用**达梦自带 JDBC 驱动**（`/opt/dmdbms/jdk` + `DmJdbcDriver8.jar`）
> 执行 DDL，稳定可靠。dmPython 驱动部署时亦可作为替代。

## 6. 验证 <a id="verify"></a>

```bash
systemctl is-active DmServiceDMSERVER                 # active
echo "SELECT NAME FROM ALL_USERS;" | /opt/dmdbms/bin/disql SYSDBA/"<密码>"@localhost:5236
# 登录成功输出「服务器[localhost:5236]:处于普通打开状态」
```

本次部署结果：服务 active，disql 与 JDBC 均可连接，`bms_dev` schema 已创建并验证建表/删表成功。

## 7. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 服务状态 | `systemctl status DmServiceDMSERVER` |
| 启动 / 停止 / 重启 | `sudo systemctl start|stop|restart DmServiceDMSERVER` |
| 命令行连接 | `/opt/dmdbms/bin/disql SYSDBA/密码@<mjbk-IP>:5236` |
| 查看日志 | `tail -f /opt/dmdbms/data/DAMENG/log/dm_DMSERVER*.log` |
| 备份（每日 cron 2 点） | `/opt/dmdbms/bin/dmrman CTLSTMT="BACKUP DATABASE '/opt/dmdbms/data/DAMENG/dm.ini' FULL TO BAK_$(date +%F) BACKUPSET '/mnt/data/backup/dameng/$(date +%F)'"` |
| 现场导出（缺陷重现，见《[测试规范](../../规范/测试规范.md)》9 节） | `mkdir -p /mnt/data/backup/defects/<缺陷号> && /opt/dmdbms/bin/dexp SYSDBA/密码@localhost:5236 FILE=<缺陷号>.dmp DIRECTORY=/mnt/data/backup/defects/<缺陷号> OWNER=<模式名> LOG=exp.log` |
| 防火墙 | ufw 已放行内网 5236（含 3306/5432/6379/9000/9001，见总览） |

## 8. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| 安装进程 100% CPU 死循环 | `DMInstall.bin -i` 管道输入耗尽后，在「是否确认安装」提示处空转 | 改用 PTY 交互逐句应答（见 3.2 警告）；安装应答序列共 9 项 |
| 没有写入权限 | 安装目录选 `/opt/dmdbms` 报「没有写入权限！」 | `sudo chown -R <SSH账号>:<SSH账号> /opt/dmdbms` |
| dminit 初始化失败 | 「please set [SYSDBA_PWD] and [SYSAUDITOR_PWD] values」 | 必须显式提供两个强密码（8-48 位，大小写+数字） |
| disql 执行 CREATE SCHEMA 挂起 | 管道输入显示 `SQL> 2 3` 后不执行 | 改用 JDBC 执行 DDL（见第 5 节警告） |
| libncurses5 装不上 | noble 仓库无此包 | 从清华镜像 jammy 池下载 deb 安装（见 3.1） |

## 9. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明](开发服务器部署使用说明.md)》：服务部署总览
- 《[开发部署规划](../../规划/开发部署规划.md)》：4.4 常驻数据库方案（schema 承载库语义）
- 《[MySQL部署使用说明](MySQL部署使用说明.md)》/《[PostgreSQL部署使用说明](PostgreSQL部署使用说明.md)》：另两库
- 《[命名规范](../../规范/命名规范.md)》：库名约定（bms_dev）

> 依《文档生成规范》编写 · 记录 2026-08-10 实际部署过程（Docker 镜像渠道不可用，改原生安装） · 更新日期：2026-08-10