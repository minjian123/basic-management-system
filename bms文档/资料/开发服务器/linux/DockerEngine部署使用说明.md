# Docker Engine 部署使用说明

> mjbk 容器引擎安装实录 · 2026-08-10

[文档首页](../../../文档首页.md) › [资料](../../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md) › Docker Engine 部署使用说明　|　[← 总览](开发服务器部署使用说明总览.md)　|　[下一个：Redis →](Redis部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

本文档记录 mjbk（Ubuntu 24.04.4）上 Docker Engine 的安装步骤与验证结果。
所有开发服务（数据库、缓存、GitLab 等）均以 Docker Compose 方式运行在本文安装的引擎上。
部署依据平台《开发部署规划》「基础环境准备」节；容器引擎方案：开发与生产统一 Docker Engine。
`<SSH账号>` 取值见《[本地资源](../../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`（`MJBK_SSH_USER`）。

## 2. 安装步骤 <a id="install"></a>

### 2.1 添加清华 docker-ce 源 <a id="install-source"></a>

```bash
sudo apt install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo sh -c 'echo "deb [arch=amd64 signed-by=/etc/apt/keyrings/docker.asc] https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu noble stable" > /etc/apt/sources.list.d/docker.list'
sudo apt update
```

> 注意：写入 `/etc/apt/sources.list.d/docker.list` 必须用 `sudo sh -c 'echo ... > 文件'` 包裹整条命令，
> 若写成 `echo ... | sudo tee` 或 `sudo echo ... > 文件`，重定向会在普通用户身份下执行导致写入失败（本次部署踩坑，见第 5 节）。

### 2.2 安装软件包 <a id="install-pkg"></a>

```bash
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
```

### 2.3 镜像加速 <a id="install-mirror"></a>

写入 `/etc/docker/daemon.json` 配置国内加速器（本次部署实测 daoCloud、1ms.run 加速器可用），然后重启 docker：

```bash
sudo sh -c 'mkdir -p /etc/docker && echo "{\"registry-mirrors\":[\"https://docker.m.daocloud.io\",\"https://docker.1ms.run\"],\"data-root\":\"/mnt/ssd2t/docker\"}" > /etc/docker/daemon.json'
sudo systemctl restart docker
```

### 2.4 data-root 迁移至 NVMe SSD <a id="install-dataroot"></a>

2026-08-15：新增 2T NVMe SSD（`/mnt/ssd2t`）后，Docker 运行数据（镜像/容器/全部命名卷）自系统盘 `/var/lib/docker` 迁至 `/mnt/ssd2t/docker`，系统盘只留系统，长期最省心。迁移步骤：

```bash
sudo systemctl stop docker
sudo rsync -a /var/lib/docker/ /mnt/ssd2t/docker/   # 保留源目录，验证后释放
# daemon.json 追加 "data-root": "/mnt/ssd2t/docker"（见 2.3 最终配置）
sudo systemctl start docker
docker info --format '{{.DockerRootDir}}'            # 应输出 /mnt/ssd2t/docker
docker ps                                            # 全部容器恢复正常
```

> 迁移完成并验证（6 个容器全部恢复、GitLab healthy）后，原 `/var/lib/docker`（约 8.5G）已删除释放空间。
> **注意**：stop 后若 systemd 启动失败且日志无详细报错，多半是 `daemon.json` 写入无效内容导致
> （见第 5 节排障记录）；`sudo systemctl reset-failed docker` 可清除启动限流后再启动。

### 2.5 docker 用户组 <a id="install-group"></a>

将 <SSH账号> 加入 docker 组，免 sudo 执行 docker 命令（加入后需重新登录 SSH 生效）：

```bash
sudo usermod -aG docker <SSH账号>
```

### 2.6 大镜像拉取与断点续传（2026-09-23 实测补记） <a id="install-resume"></a>

> **关键结论**：本机 Docker 用 **containerd 镜像存储**（`docker info` 的 `Storage Driver: overlayfs` + `driver-type: io.containerd.snapshotter.v1`），
> **blob 层按 HTTP Range 断点续传、已完成层落 content store 缓存**。因此 `docker pull` 被限速 / 中断后**重复执行即可续传**，
> **不会重下已完成层**——几百 MB 的大镜像（如可观测组件）在加速器限速下多次中断，累积重试即可拉完。

实测（2026-09-23，可观测性栈镜像）：`otel/opentelemetry-collector-contrib` / `tempo` / `loki` / `alloy` / `prometheus` / `grafana`
（约 0.2~0.6 GB/个）在加速器限速下常中途断开；**继续常规 `docker pull <镜像>`（可多次）** 逐个累积完成，无需切换源。
已完成的镜像用 `docker images` 核对，不必再拉。

**批量拉取工具（推荐）**：`scripts/tools/docker/拉取镜像.sh`（bms 仓根）——把「逐个拉 + 已就位跳过 + 中断重试（含单次超时防“挂住”）」固化为一条命令；
镜像清单默认读同目录 `镜像清单.txt`（每行一个、`#` 注释），可 `--host` 指定远程 Docker 主机（缺省读 `MJBK_SSH_USER@MJBK_IP`）。

```bash
# 仓库根执行；缺省读 脚本同目录/镜像清单.txt
scripts/tools/docker/拉取镜像.sh --host <SSH账号>@<mjbk-IP>          # 远程拉（断点续传 + 自动重试）
scripts/tools/docker/拉取镜像.sh nginx:1.27 redis:8                  # 本机拉指定镜像
scripts/tools/docker/拉取镜像.sh --file 我的清单.txt --retries 20    # 限定重试上限

# 等价的手工循环（无脚本时）
for img in <镜像1> <镜像2>; do docker pull "$img" && echo OK "$img" || echo RETRY "$img"; done
docker images --format '{{.Repository}}:{{.Tag}} {{.Size}}'   # 核对已就位
```

> **注意**：
> - **不要并发**多个 `docker pull` 拉同一镜像（内容锁争用会互相卡住、表现为“假死”）；上一个未结束前不要另起（脚本内部已按序逐个拉）。
> - 不要用 `docker system prune -a` 清掉已完成的层（会丢失续传缓存，需从头再拉）。
> - 加速器（daocloud / 1ms）在拉取中途限速 / 断连是常态，**“能续传、可重试”是解法**，而不是换源或拼接第三方镜像前缀。
> - **镜像副本可能损坏**：实测 `otel/opentelemetry-collector-contrib:0.116.0` 经加速器拉到的是坏副本（容器 `exec ... no such file or directory`，根 fs 缺 `/lib64` 加载器），换 tag（`0.115.1`）即正常；遇此类“能拉下但起不来”优先怀疑镜像副本，核实后换 tag 并回写清单。

## 3. 验证 <a id="verify"></a>



```bash
docker info | grep -E "Server Version|Storage Driver|Cgroup|Registry Mirrors" -A1
docker compose version
docker run --rm hello-world
```

本次部署结果：Server Version **29.7.2**，Storage Driver overlayfs，Cgroup systemd（v2），Compose **v5.4.0**，hello-world 与 alpine 镜像经加速器拉取成功。

## 4. 日常运维命令 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 服务状态 | `systemctl status docker` |
| 查看容器 | `docker ps -a` |
| 容器日志 | `docker logs -f <容器名>` |
| 磁盘占用 | `docker system df`；data-root 位置 `docker info --format '{{.DockerRootDir}}'` |
| 清理悬空镜像/缓存 | `docker system prune -f`（慎用 -a） |
| Compose 操作 | 各服务文档中的 `docker compose -f deploy/compose/xxx.yml ...` 命令 |

## 5. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| apt 找不到 docker 软件包 | `E: 无法定位软件包 docker-buildx-plugin`，且 `/etc/apt/sources.list.d/docker.list` 不存在 | 重定向在普通用户身份下执行导致写入失败；改用 `sudo sh -c 'echo ... > 文件'` 重写源文件后 apt update 正常 |
| permission denied（docker.sock） | 非 root 用户执行 docker 命令报 `permission denied while trying to connect` | <SSH账号> 加入 docker 组（`sudo usermod -aG docker <SSH账号>`），重新登录 SSH 生效 |
| 迁移 data-root 后 systemd 启动失败 | `systemctl start docker` 报 `Job for docker.service failed`，journalctl 无具体错误；`dockerd` 手动运行却能正常启动 | daemon.json 被写入无效内容（管道顺序错误导致写入的是密码而非 JSON）；用 `sudo bash -c 'echo 内容 > 文件'` 重写后 `sudo systemctl reset-failed docker`（清除 StartLimitBurst 限流）再启动 |

## 6. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)》：服务部署总览与顺序
- 平台《开发部署规划》：4.1 容器引擎方案
- `scripts/tools/docker/拉取镜像.sh` + `镜像清单.txt`（bms 仓根）：大镜像批量拉取（断点续传 + 自动重试），见 §2.6
- 《[Ubuntu安装部署使用说明](../../工具/Ubuntu安装部署使用说明.md)》：系统基础配置（apt 清华源、HDD 挂载、Timeshift）
- 《[文档生成规范](../../../规范/文档生成规范.md)》：本文档遵循的格式规范

> 依《文档生成规范》编写 · 记录 2026-08-10 实际部署过程