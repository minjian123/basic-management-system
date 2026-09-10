# 基座同步工具（base-sync）

> 通用基座（bms 权威源）→ 产品仓库：按《[基座文档清单](../../../文档/基座文档清单.md)》比较差异、人工确认后覆盖。不引入 git submodule（清单 + 脚本 + 人工确认）。

## 适用场景

bms 提交涉及基座路径（`文档/规范`、`文档/资料` 基础设施部分、`文档/资源`）后，产品仓库（如 biz、cw）需要刷新时运行本工具。

## 组成

| 文件 | 作用 |
| --- | --- |
| `base-sync.py` | 基座同步主脚本：`list` / `sync`（dry-run 默认，`--apply` 写入）/ `check`（一致性自检，差异即退出码 1） |
| `check-base.py` | bms 侧基座完整性校验：链接自洽、无跨层引用、无措辞残留、清单与磁盘一致（CI job `base-integrity` 调用） |
| `pre-commit.sh` | 提交前校验入口：先跑 `check-base.py`，再按 `.targets` 登记逐个产品仓库跑 `base-sync.py check` |

## 用法

### 同步到产品仓库

在 bms 仓库根目录运行：

```
# 列出 bms 基座文件清单
python3 scripts/tools/base-sync/base-sync.py list

# 输出 bms 与产品仓库差异（dry-run，不写盘）
python3 scripts/tools/base-sync/base-sync.py sync --target /path/to/biz

# 只更新规则文件（产品侧已存在的改动）
python3 scripts/tools/base-sync/base-sync.py sync --target /path/to/biz --scope update

# 只同步子目录（如 规范）
python3 scripts/tools/base-sync/base-sync.py sync --target /path/to/biz --dir 规范

# 确认后实际写入（同时写入同步基线 文档/.base-sync-baseline.json）
python3 scripts/tools/base-sync/base-sync.py sync --target /path/to/biz --apply
```

### 一致性自检

```
# 基座完整性（bms 侧，CI 同款）
python3 scripts/tools/base-sync/check-base.py

# 产品仓库基座一致性（有差异退出码 1）
python3 scripts/tools/base-sync/base-sync.py check --target /path/to/biz
```

### 提交前校验（可选装为 git 钩子）

产品仓库路径登记在 `scripts/tools/base-sync/.targets`（一行一个路径，`#` 注释；**含本机路径，已 gitignore，不入库**）：

```
/home/minjian/develop/biz
/home/minjian/develop/cw
```

```
# 手动运行
bash scripts/tools/base-sync/pre-commit.sh

# 装为 git 钩子（按需）
ln -sf ../../scripts/tools/base-sync/pre-commit.sh .git/hooks/pre-commit
```

## 输出说明

- **更新**：产品侧已有该文件但内容不同，覆盖前请审阅差异（行数已标注）。
- **新增**：产品侧缺失的基座文件，按需补入（知识档案等可选全量）。
- **基座已删除**：产品侧残留、而权威源已删除的基座文件（依据同步基线识别），确认后手工删除。
- **产品独有**：产品业务专属文件（如 cw 的 ComfyUI/civitai 资料），不删不覆盖。

## 同步基线

`sync --apply` 后在目标仓库写入 `文档/.base-sync-baseline.json`（bms 提交号、时间、文件数、逐文件 md5）：

- 供「基座已删除」识别：文件在基线中登记过、而权威源已无 → 判为残留而非产品专属；
- 用于核对产品侧上次同步到哪个 bms 提交。该文件不入库，产品的 `.gitignore` 已登记。

## 排除项

- `文档/用户文档/`（本地资源凭据模板）：登记为基座但各仓库自带副本、内容各异，不参与同步。

## 首次同步

cw 早期规范为人工改编版（BMS→CW 前缀替换），按「基座唯一权威源」切源时覆盖为中性权威版；cw 特有增补（如 multilingual 简称条目）确认后迁到产品专属文档。
