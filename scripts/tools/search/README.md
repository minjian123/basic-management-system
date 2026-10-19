# 内容检索工具（scripts/tools/search/）

面向 AI 助手与人的**工作区内容检索**：代码 + 文档统一检索，按相关性排序返回精简结果。

## 为什么需要它

实测本工作区 5002 个可检索文件、全库 `ripgrep` 扫描仅 **60~70ms**——**速度不是瓶颈**。
真正的瓶颈是**结果收敛**：同一个关键词在纯文本扫描下的命中量：

| 查询 | rg 命中文件 | rg 命中行 | 需人工判断 |
| --- | --- | --- | --- |
| 权限计算 | 162 | 347 | 逐个打开 |
| resolve_plugin | 168 | 391 | 逐个打开 |
| 租户隔离 | 105 | 177 | 逐个打开 |

本工具把上述场景收敛为 **≤10 条按相关度排序的结果**，实测平均 **MRR 0.74**（首条即相关的比例）。

## 与「已废止的索引方案」的区别

《[代码检索索引方式失效复盘](../../../bms文档/资料/知识档案/工程化与质量/代码检索索引方式失效复盘.md)》
判定「生成式导航索引」无效，原因是**无法机器验证、维护成本高、收益可被过滤替代**。
本工具针对性规避了这三点：

| 复盘教训 | 本工具做法 |
| --- | --- |
| 无法验证 → 必然漂移 | `--check` 比对索引与实际文件集，不一致即退出码 1 |
| 依赖 LLM 语义补全 → 重跑分钟级 | 纯静态抽取（H1 / 摘要 / 符号名），无任何 LLM 调用 |
| 收益可被工具过滤替代 | 提供的是**排序与收敛**，不是「去哪找」的导航——这是 rg 过滤做不到的 |

## 安装依赖

**装到系统 Python**（一次安装，所有工作区与 agent 直接可用）：

```bash
# 国内镜像（清华）
python3 -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r scripts/tools/search/requirements.txt
```

> 不用项目虚拟环境：虚拟环境不入 git，每个工作区克隆都要重装，且各 agent 得分别指向
> 对应 venv 的绝对路径。只引入两个纯 Python 包，污染全局的代价可接受。
> 后端 `backend/.venv` 由 uv 管理，**不要**往里装这两个包（会破坏依赖树）。

## 用法

### 人工检索（命令行）

```bash
# 在 bms 仓根运行
python3 scripts/tools/search/search_mcp.py -q 权限计算
python3 scripts/tools/search/search_mcp.py -q BaseService --kind code -n 5
python3 scripts/tools/search/search_mcp.py -q 认证 --path 设计 --snippet
python3 scripts/tools/search/search_mcp.py -q 租户隔离 --json
```

### 索引维护

```bash
python3 scripts/tools/search/search_mcp.py --rebuild   # 全量重建（约 40 秒）
python3 scripts/tools/search/search_mcp.py --update    # 增量（秒级，按 mtime）
python3 scripts/tools/search/search_mcp.py --check     # 一致性自检
```

索引落在 `<工作区根>/.cache/search/index.db`（约 62MB，已 gitignore）。

### 作为 MCP 服务接入 agent

`search_mcp.py` 不带 `-q` 参数时以 **stdio MCP 服务**运行。DSH 接入方式：在
`~/.dsh/profiles/<profile>/cordis.patch.yml` 追加一条：

```yaml
- id: mcp-bizs-search
  name: '@deepseek-ai/dsh-mcp-client'
  config:
    serverName: bizssearch
    transport: stdio
    command: 'python'
    args: ['<工作区根>/bms/scripts/tools/search/search_mcp.py']
```

**一条配置覆盖所有工作区**：服务按「当前会话工作目录」向上找 `bms/` 自动定位检索根，
索引随工作区落在 `<工作区根>/.cache/search/`。`bizs` 会话查 `bizs`、`cws` 会话查 `cws`，
无需各写一条。`SEARCH_ROOT` / `SEARCH_DB` 两个环境变量都可省略，仅在需要固定某个工作区时才设。

暴露的工具：

| 工具 | 用途 |
| --- | --- |
| `search_content` | 按相关性检索，返回路径 / 类型 / 标题 / 摘要 / 分数 |
| `search_with_snippet` | 附带命中行片段（省 token，不必整文件读） |
| `index_update` | 增量刷新索引（秒级） |

## 检索原理

1. **结构化抽取**：文档抽 H1 标题、`>` 摘要、面包屑、H2 小标题；代码抽 `def`/`class`/`function` 符号名
2. **中文分词**：jieba 分词，标识符按驼峰与下划线切分（`RBACService` → `rbac service`）
3. **倒排索引**：SQLite FTS5（`unicode61`），单文件、零常驻进程
4. **相关性排序**：`bm25()` 分列加权（标题 8 / 符号 6 / 摘要 4 / 面包屑 2 / 正文 1）
5. **路径加权与噪音抑制**：路径含查询词加分；测试夹具、锁文件等降权

## 自检与评测

```bash
python3 scripts/tools/search/selftest.py   # MCP 协议端到端冒烟（退出码 0/1）
python3 scripts/tools/search/bench.py      # 与 ripgrep 的 MRR / 召回对照
```

## 已知边界

- 不做语义检索（同义改写搜不到），需精确词或领域术语
- 索引不含图片、二进制；单文件上限 2MB
- 检索结果是**候选**，最终仍需读文件确认内容
