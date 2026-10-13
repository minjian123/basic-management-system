# MIRIX 中文记忆面板

自建单文件静态页（`index.html`）+ nginx 反代配置（`nginx.conf`），部署在 mjbk 容器 `mirix-panel`（`:5173`）。
概览、端口、用法见《[MIRIX部署使用说明](../../../../bms文档/资料/AI/MIRIX部署使用说明.md)》6.4 节。

## 部署（mjbk）

```bash
mkdir -p ~/mirix/panel
cp index.html nginx.conf ~/mirix/panel/
cd ~/mirix && docker compose --env-file .env up -d mirix-panel
```

`nginx.conf` 把 `/api/` 反代到 `http://mirix_api:8531/`（compose 里用 `extra_hosts: mirix_api:host-gateway` 指向宿主机）。
进入面板时填客户端 API Key（见《本地资源》）。
