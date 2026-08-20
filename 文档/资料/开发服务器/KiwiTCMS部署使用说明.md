# Kiwi TCMS 部署使用说明

> mjbk 测试用例管理平台部署实录 · 2026-08-19

[文档首页](../../文档首页.md) › [资料](../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明](开发服务器部署使用说明.md) › Kiwi TCMS 部署使用说明　|　[← 上一个：GitLab](GitLab部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 Kiwi TCMS（容器 `bms-kiwi`）是 BMS 项目的**测试用例唯一管理平台**（《[项目规划说明](../../规划/项目规划说明.md)》16.3）：
手工与自动化用例统一登记、执行结果导入归档；复用 mjbk MySQL（库 `kiwi`），宿主端口 8060。

占位符取值：`<mjbk-IP>`、`<内网网段>` 见《[本地资源](../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`（`MJBK_IP`）。

## 2. Compose 配置 <a id="compose"></a>

定义于仓库 `deploy/compose/kiwi.yml`（已同步至 mjbk `~/deploy/compose/kiwi.yml`）：

```yaml
services:
  kiwi:
    image: kiwitcms/kiwi:latest
    container_name: bms-kiwi
    restart: unless-stopped
    environment:
      TZ: Asia/Shanghai
      KIWI_DB_ENGINE: django.db.backends.mysql
      KIWI_DB_HOST: ${KIWI_DB_HOST}
      KIWI_DB_PORT: ${KIWI_DB_PORT}
      KIWI_DB_NAME: ${KIWI_DB_NAME}
      KIWI_DB_USER: ${KIWI_DB_USER}
      KIWI_DB_PASSWORD: ${KIWI_DB_PASSWORD}
      KIWI_SECRET_KEY: ${KIWI_SECRET_KEY}
    ports:
      - "8060:8443"
    volumes:
      - kiwi-uploads:/Kiwi/uploads

volumes:
  kiwi-uploads:
```

> 卷名实际带项目名前缀：compose 项目名为 `compose`（`docker compose -f compose/xxx.yml` 默认取文件所在目录名），实际卷名为 `compose_kiwi-uploads`，路径 `/mnt/ssd2t/docker/volumes/compose_kiwi-uploads/`。

> **镜像说明**：`kiwitcms/kiwi:latest` 为官方公共镜像，滚动发布（当前 16.x，随官方更新自动变化）。
> 镜像内 nginx 实际监听 **8443（HTTPS，自签名证书）/ 8080（HTTP，301 跳转 HTTPS）**，
> 因此端口映射为 `8060:8443`，访问地址是 `https://`。

## 3. 部署步骤 <a id="deploy"></a>

1. mjbk `~/deploy/.env` 追加 Kiwi 配置（键位见仓库 `deploy/.env.example`）：
   `KIWI_DB_HOST/PORT/NAME/USER/PASSWORD`（DB 连接）、`KIWI_SECRET_KEY`（随机生成）、`KIWI_ADMIN_PASSWORD`（管理员密码，仅记录不用于启动）。
2. 在 mjbk MySQL 中创建独立库与账号（库 `kiwi`，utf8mb4；账号 `kiwi`，仅授 `kiwi` 库权限）：

    ```sql
    mysql -h<mjbk-IP> -uroot -p \
      -e "CREATE DATABASE IF NOT EXISTS kiwi DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
          CREATE USER IF NOT EXISTS 'kiwi'@'%' IDENTIFIED BY '<密码>';
          GRANT ALL PRIVILEGES ON kiwi.* TO 'kiwi'@'%';
          FLUSH PRIVILEGES;"
    ```

3. 启动容器：

    ```bash
    cd ~/deploy
    docker compose -f compose/kiwi.yml --env-file ~/deploy/.env up -d
    ```

4. **手动执行数据库迁移**（16.x 公共镜像启动时不再自动迁移）：

    ```bash
    docker exec bms-kiwi /Kiwi/manage.py migrate
    ```

5. 创建管理员（账号 `admin`，密码取 `~/deploy/.env` 的 `KIWI_ADMIN_PASSWORD`）：

    ```bash
    docker exec -e DJANGO_SUPERUSER_PASSWORD=<密码> bms-kiwi \
      /Kiwi/manage.py createsuperuser --noinput --username admin --email admin@bms.local
    ```

> 排障提示：`KIWI_DB_ENGINE` 必须写完整 Django 引擎名 `django.db.backends.mysql`，写简写 `mysql` 会导致 uWSGI 启动报 `No module named 'mysql'`（见第 8 节）。

## 4. 验证 <a id="verify"></a>

```bash
docker ps --filter name=bms-kiwi                  # Up ... (healthy)
curl -sk -o /dev/null -w "%{http_code}" https://127.0.0.1:8060/accounts/login/   # 200
curl -sk https://<mjbk-IP>:8060/accounts/login/ | grep "<title>"      # Kiwi TCMS - Login
```

本次部署结果：容器 healthy，登录页 HTTP 200，管理员 `admin` 登录验证通过（POST 登录 302 → 首页含退出入口）。

## 5. 使用说明 <a id="use"></a>

| 项目 | 值 |
| --- | --- |
| 访问地址 | `https://<mjbk-IP>:8060`（自签名证书，浏览器首次访问需接受警告；仅内网） |
| 管理员账号 | `admin`（密码见 `~/deploy/.env` 的 `KIWI_ADMIN_PASSWORD`） |
| 界面语言 | 官方简体中文翻译为主，浏览器自动翻译兜底（系统设置 → 语言偏好） |
| 数据存储 | 业务数据在 MySQL `kiwi` 库；上传附件在命名卷 `compose_kiwi-uploads`（项目名 compose，位于 `/mnt/ssd2t/docker/volumes/`） |

BMS 项目中的用法（《[测试规范](../../规范/测试规范.md)》）：用例按模块建 **Category**、用 **Tag** 组织；用例名称/描述使用中文；自动化用例在代码中以用例 ID 标注关联；pytest/Playwright 执行结果经官方插件导入平台归档；平台缺陷链接指向 GitLab Issue。

## 6. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-kiwi` |
| 查看日志 | `docker logs -f bms-kiwi` |
| 重启 | `docker restart bms-kiwi` |
| 数据库迁移 | `docker exec bms-kiwi /Kiwi/manage.py migrate` |
| Django 管理命令 | `docker exec bms-kiwi /Kiwi/manage.py <命令>`（如 `createsuperuser`） |
| 修改管理员密码 | `docker exec bms-kiwi /Kiwi/manage.py changepassword admin` |

> 防火墙：mjbk ufw 当前处于**不活动**状态；若日后启用 ufw，需放行内网 8060（规则已预置：`allow from <内网网段> to any port 8060 proto tcp`），并注意 Docker 发布端口需 `ufw default allow routed`（见 GitLab 部署说明排障记录）。

## 7. 备份与恢复 <a id="backup"></a>

- **业务数据**：全部在 MySQL `kiwi` 库，随《[MySQL部署使用说明](MySQL部署使用说明.md)》每日 dump（`/mnt/data/backup/`）；恢复时重建库账号后导入 dump 即可，无需改动容器配置。
- **上传附件**：命名卷 `compose_kiwi-uploads`（挂载于容器 `/Kiwi/uploads`），位于 Docker data-root（`/mnt/ssd2t/docker/volumes/`）；备份该卷需 `docker run --rm -v compose_kiwi-uploads:/data -v /mnt/data/backup/kiwi-uploads:/backup alpine tar czf /backup/kiwi-uploads.tar.gz -C /data .`。
- **迁移注意事项**：卷仅挂载 `/Kiwi/uploads`（附件目录），nginx/uWSGI 配置与自签名证书在镜像内 `/Kiwi/etc`、`/Kiwi/ssl`，随镜像更新；首次挂载空卷时镜像自动复制默认内容。

## 8. 排障记录 <a id="trouble"></a>

| 问题 | 现象 | 处理 |
| --- | --- | --- |
| KIWI_DB_ENGINE 简写导致启动失败 | 容器 unhealthy，uWSGI 报 `no python application found`，日志根因 `ModuleNotFoundError: No module named 'mysql'` | `KIWI_DB_ENGINE` 须写完整 Django 引擎名 `django.db.backends.mysql`（镜像默认值即完整名，写简写 `mysql` 会覆盖默认值触发错误）；修正后重建容器 |
| 16.x 镜像不自动建表 | 容器 healthy、页面可访问，但登录/创建用户报 `Table 'kiwi.auth_user' doesn't exist`，且提示 100 个未应用迁移 | 公共镜像启动时不再自动迁移，需手动执行 `docker exec bms-kiwi /Kiwi/manage.py migrate`（约 1 分钟） |
| 端口映射后宿主机访问不通 | 映射 `8060:80` 后容器 healthy 但宿主 127.0.0.1:8060 连接被重置（RST） | 16.x 镜像内 nginx 只监听 8080（HTTP 跳转）与 8443（HTTPS 实际服务），不监听 80；映射改为 `8060:8443`，用 `https://` 访问（自签名证书） |

## 9. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明](开发服务器部署使用说明.md)》：服务部署总览与端口规划
- 《[MySQL部署使用说明](MySQL部署使用说明.md)》：数据库账号库规划与每日备份
- 《[开发部署规划](../../规划/开发部署规划.md)》：Kiwi TCMS 部署位（宿主 8060、复用 MySQL）
- 《[项目规划说明](../../规划/项目规划说明.md)》：16.3 测试用例管理（Kiwi TCMS）
- 《[测试规范](../../规范/测试规范.md)》：用例库组织、结果导入、缺陷管理流程
- 《[命名规范](../../规范/命名规范.md)》：容器名 `bms-组件`、数据库命名

> 依《文档生成规范》编写 · 记录 2026-08-19 实际部署过程（kiwitcms/kiwi:latest，MySQL 8.4 复用）