# Kiwi TCMS 部署使用说明

> mjbk 测试用例管理平台部署实录 · 2026-08-19

[文档首页](../../../文档首页.md) › [资料](../../工具/Ubuntu安装部署使用说明.md) › [开发服务器部署使用说明总览](开发服务器部署使用说明总览.md) › Kiwi TCMS 部署使用说明　|　[← 上一个：GitLab](GitLab部署使用说明.md)

## 1. 目的与适用范围 <a id="purpose"></a>

mjbk 上的 Kiwi TCMS（容器 `bms-kiwi`）是本项目的**测试用例唯一管理平台**（平台《项目规划说明》「回归策略」节）：
手工与自动化用例统一登记、执行结果导入归档；复用 mjbk MySQL（库 `kiwi`），宿主端口 8060。

占位符取值：`<mjbk-IP>`、`<内网网段>` 见《[本地资源](../../../用户文档/本地资源.md)》与 mjbk 本机 `deploy/.env`（`MJBK_IP`）。

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
      - "8061:8080"                                  # 内网 HTTP 入口（2026-09-15 增）：见下方说明
    volumes:
      - kiwi-uploads:/Kiwi/uploads
      - ./kiwi-nginx.conf:/etc/nginx/nginx.conf:ro   # 改写镜像内 8080 的策略：反代本机 8443 并跳过上游证书校验

volumes:
  kiwi-uploads:
```

> 卷名实际带项目名前缀：compose 项目名为 `compose`（`docker compose -f compose/xxx.yml` 默认取文件所在目录名），实际卷名为 `compose_kiwi-uploads`，路径 `/mnt/ssd2t/docker/volumes/compose_kiwi-uploads/`。

> **镜像说明**：`kiwitcms/kiwi:latest` 为官方公共镜像，滚动发布（当前 16.x，随官方更新自动变化）。
> 镜像内 nginx 实际监听 **8443（HTTPS，自签名证书）/ 8080（HTTP，301 跳转 HTTPS）**，
> 因此端口映射为 `8060:8443`，访问地址是 `https://`。

> **8061（内网 HTTP 入口，2026-09-15 增）**：镜像把 8080 做成「301 跳 HTTPS」，而 Kiwi 应用层 `SECURE_SSL_REDIRECT`
> **硬编码为真**（`tcms/settings/common.py`，无法用环境变量关闭），自签名证书 SAN 又是容器内主机名（用 IP 访问必报校验失败），
> 故 CI 侧无法直连 8443。解法：宿主 **8061 → 容器 8080**，并用 `deploy/compose/kiwi-nginx.conf` 覆盖镜像内 nginx 配置——
> 8080 不再跳转，改为**反向代理本机 8443 且 `proxy_ssl_verify off`**（Django 侧仍认为自己是 https，不再触发跳转）。
> 用途：`kiwitcms-pytest-plugin` 在流水线中经该入口以明文 HTTP 导入执行结果（口径见《[测试规范](../../../规范/测试规范.md)》「结果导入平台归档」节）。
> 该端口用于「GitLab Runner 容器 → 宿主端口」的内部调用，经 Docker 自身链放行，**未单独加入 ufw 规则**；若跨主机访问须另行放行。

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
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8061/xml-rpc/                               # 415（XML-RPC 服务在，未带 POST 体）
curl -s -X POST -H "Content-Type: application/xml" -d '<methodCall><methodName>Auth.login</methodName></methodCall>' \
  http://127.0.0.1:8061/xml-rpc/                                                                     # 200 且 Content-Type: application/xml
```

本次部署结果：容器 healthy，登录页 HTTP 200，管理员 `admin` 登录验证通过（POST 登录 302 → 首页含退出入口）。
2026-09-15 增补：8061 HTTP 入口可用（`POST /xml-rpc/` 返回 200、`Content-Type: application/xml`，**不再 301**）；
流水线 178 的 `allure-report` job 经该入口把 424 条执行结果导入成功。

## 5. 使用说明 <a id="use"></a>

### 5.1 平台信息 <a id="use-info"></a>

| 项目 | 值 |
| --- | --- |
| 访问地址 | `https://<mjbk-IP>:8060`（自签名证书，浏览器首次访问需接受警告；仅内网） |
| 管理员账号 | `admin`（密码见 `~/deploy/.env` 的 `KIWI_ADMIN_PASSWORD`） |
| 界面语言 | 官方简体中文翻译为主，浏览器自动翻译兜底（系统设置 → 语言偏好） |
| 数据存储 | 业务数据在 MySQL `kiwi` 库；上传附件在命名卷 `compose_kiwi-uploads`（项目名 compose，位于 `/mnt/ssd2t/docker/volumes/`） |

### 5.2 用例约定 <a id="use-cases"></a>

本项目中的用法（《[测试规范](../../../规范/测试规范.md)》）：用例按模块建 **Category**、用 **Tag** 组织；用例名称/描述使用中文；自动化用例在代码中以用例 ID 标注关联；pytest/Playwright 执行结果经官方插件导入平台归档；平台缺陷链接指向 GitLab Issue。

各字段取值与登记口径：

| 字段 | 平台取值 | 约定 |
| --- | --- | --- |
| 分类 Category | 产品「BMS 基础管理系统」下按模块建分类 | 平台骨架类用例统一归「平台骨架」 |
| 优先级 Priority | `P1` ~ `P5` | 平台骨架用例用 `P2` |
| 状态 | `PROPOSED`（提议）/ `CONFIRMED`（已确认）/ `DISABLED`（停用）/ `NEED_UPDATE`（待更新） | 正式登记用 `CONFIRMED` |
| 标签 Tag | 自由标签 | 自动化用例加「自动化」 |
| 用例号 | 平台自增主键 | **先登记、后写自动化代码**，代码以 `@pytest.mark.kiwi_id(<用例号>)` 标注 |
| 用例文本 text | 中文 | 写覆盖范围（用例清单）与自动化文件路径 |
| 作者 author | 平台账号 | 当前 `admin` |

### 5.3 用例登记（脚本化批量） <a id="use-register"></a>

少量用例用 Web 界面单条录入；**批量登记走容器内 Django shell**（不依赖登录态、可脚本化、用例号顺延可预期）：

```bash
ssh <账号>@<mjbk-IP> "docker exec -i bms-kiwi /Kiwi/manage.py shell" < register_cases.py
```

`manage.py shell` 从标准输入读代码（非 tty），脚本不必落盘进容器。`register_cases.py` 模板：

```python
from django.contrib.auth import get_user_model
from tcms.management.models import Priority, Tag
from tcms.testcases.models import Category, TestCase, TestCaseStatus

author = get_user_model().objects.get(username="admin")
category = Category.objects.get(name="平台骨架")        # 分类：按模块建
priority = Priority.objects.get(value="P2")              # 优先级：P1 ~ P5
status = TestCaseStatus.objects.get(name="CONFIRMED")    # 状态：登记用 CONFIRMED

case = TestCase.objects.create(
    summary="<用例标题：任务编号 + 主题 + 关键断言摘要>",
    category=category,
    priority=priority,
    case_status=status,
    author=author,
    text="<覆盖范围（用例清单）/ 自动化文件路径 / kiwi_id 标注方式>",
)
tag, _ = Tag.objects.get_or_create(name="自动化")
case.add_tag(tag)
print("created case id =", case.pk)
```

登记后回读核对（用例号须与代码 `kiwi_id` 标注一致）：

```bash
ssh <账号>@<mjbk-IP> "docker exec bms-kiwi /Kiwi/manage.py shell -c \"from tcms.testcases.models import TestCase as T; print([(c.pk, c.summary) for c in T.objects.order_by('-pk')[:5]])\""
```

口径说明：

- 一个任务通常登记**一条**用例（多条自动化断言共用同一 `kiwi_id`），用例文本内列覆盖范围，避免平台条目碎片化。
- 中文脚本经管道传输按 UTF-8 编码；Windows 侧建议先写脚本文件再重定向（避免控制台编码把中文破坏）。
- 用例**先登记再写自动化代码**（《测试规范》「用例管理（Kiwi TCMS）」节），执行结果经官方插件导入归档。

### 5.4 JSON-RPC 接口 <a id="use-rpc"></a>

平台提供 JSON-RPC 端点 `https://<mjbk-IP>:8060/json-rpc/`，请求体形如 `{"jsonrpc": "2.0", "method": "<方法名>", "params": {...}, "id": 1}`：

- `jsonrpc` 字段**必填**，缺失直接返回 `Invalid request: jsonrpc required`；方法名不存在返回 `-32601 Method not found`。
- 需鉴权方法的**会话口径尚未验证**（实测 `Auth.login` 返回 `Invalid request: Unsupported field`）；批量登记与维护当前一律走 Web 界面或 Django shell（见 5.3 节），RPC 登录口径验证后再补充本节。

## 6. 日常运维 <a id="ops"></a>

| 操作 | 命令 |
| --- | --- |
| 查看状态 | `docker ps --filter name=bms-kiwi` |
| 查看日志 | `docker logs -f bms-kiwi` |
| 重启 | `docker restart bms-kiwi` |
| 数据库迁移 | `docker exec bms-kiwi /Kiwi/manage.py migrate` |
| Django 管理命令 | `docker exec bms-kiwi /Kiwi/manage.py <命令>`（如 `createsuperuser`） |
| 修改管理员密码 | `docker exec bms-kiwi /Kiwi/manage.py changepassword admin` |
| 列最近用例 | `docker exec bms-kiwi /Kiwi/manage.py shell -c "from tcms.testcases.models import TestCase as T; print([(c.pk, c.summary) for c in T.objects.order_by('-pk')[:10]])"` |
| 查分类 / 优先级 / 状态 | `docker exec bms-kiwi /Kiwi/manage.py shell -c "from tcms.testcases.models import Category as C, TestCaseStatus as S; from tcms.management.models import Priority as P; print([c.name for c in C.objects.all()], [p.value for p in P.objects.all()], [s.name for s in S.objects.all()])"` |

| 重建容器（**必须 --env-file**） | `cd ~/deploy && docker compose --env-file .env -f compose/kiwi.yml up -d`（漏 `--env-file` 会让 DB 变量插值为空，见排障第 4 项） |
| 核对 HTTP 入口 8061 | `curl -s -X POST -d '<methodCall/>' http://127.0.0.1:8061/xml-rpc/`（应为 200 + `application/xml`，非 301） |

> 批量建立用例、回读核对与用例约定见 5.2 / 5.3 节。
>
> 防火墙：mjbk ufw 已启用（2026-08-22），内网 8060 已放行；规则总表与维护口径见《[防火墙部署使用说明](防火墙部署使用说明.md)》。8061 为容器到宿主的内部调用（未单独入 ufw 规则）。

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
| HTTP 入口加到 8061 后仍 301 / 500（2026-09-15） | `SECURE_SSL_REDIRECT` 硬编码为真 + 自签名证书 SAN 为容器内主机名，CI 用 IP 直连必然失败 | 宿主 8061 → 容器 8080，并用 `kiwi-nginx.conf` 把 8080 从「跳转」改为**反代本机 8443 且 `proxy_ssl_verify off`**；Django 侧收到 https scheme 不再跳转 |
| **重建容器后落到未初始化态**（2026-09-15） | 在 `compose/` 目录直接 `docker compose -f kiwi.yml up -d`，全部请求 302 到 `/init-db/`，DB 环境变量为空 | compose 目录下没有 `.env`，缺省 `env_file` 导致 `${KIWI_DB_*}` 插值为空。必须用 `cd ~/deploy && docker compose --env-file .env -f compose/kiwi.yml up -d`（已核验容器内 `KIWI_DB_*` 非空） |

## 9. 关联文档 <a id="related"></a>

- 《[开发服务器部署使用说明总览](开发服务器部署使用说明总览.md)》：服务部署总览与端口规划
- 《[MySQL部署使用说明](MySQL部署使用说明.md)》：数据库账号库规划与每日备份
- 平台《开发部署规划》：Kiwi TCMS 部署位（宿主 8060、复用 MySQL）
- 平台《项目规划说明》：16.3 测试用例管理（Kiwi TCMS）
- 《[测试规范](../../../规范/测试规范.md)》：用例库组织、结果导入、缺陷管理流程
- 《[命名规范](../../../规范/命名规范.md)》：容器名 `bms-组件`、数据库命名

> 依《文档生成规范》编写 · 记录 2026-08-19 实际部署过程（kiwitcms/kiwi:latest，MySQL 8.4 复用）