# 基座同步工具（base-sync）

> 通用基座（bms 权威源）→ 产品仓库：按《[基座文档清单](../../../文档/基座文档清单.md)》比较差异、人工确认后覆盖。不引入 git submodule（清单 + 脚本 + 人工确认）。

## 适用场景

bms 提交涉及基座路径（`文档/规范`、`文档/资料` 基础设施部分、`文档/资源`）后，产品仓库（如 cw）需要刷新时运行本工具。

## 用法

在 bms 仓库根目录运行：

```
# 列出 bms 基座文件清单
python3 scripts/tools/base-sync/base-sync.py list

# 输出 bms 与产品仓库差异（dry-run，不写盘）
python3 scripts/tools/base-sync/base-sync.py sync --target /home/minjian/develop/cw

# 只更新规则文件（产品侧已存在的改动）
python3 scripts/tools/base-sync/base-sync.py sync --target /home/minjian/develop/cw --scope update

# 只同步子目录（如 规范）
python3 scripts/tools/base-sync/base-sync.py sync --target /home/minjian/develop/cw --dir 规范

# 确认后实际写入
python3 scripts/tools/base-sync/base-sync.py sync --target /home/minjian/develop/cw --apply
```

## 输出说明

- **更新**：产品侧已有该文件但内容不同，覆盖前请审阅差异（行数已标注）。
- **新增**：产品侧缺失的基座文件，按需补入（知识档案等可选全量）。
- **产品独有**：产品业务专属文件（如 cw 的 ComfyUI/civitai 资料），不删不覆盖。

## 排除项

- `文档/用户文档/`（本地资源凭据模板）：各仓库自带副本、内容各异，不参与同步。

## 首次同步

cw 早期规范为人工改编版（BMS→CW 前缀替换），按「基座唯一权威源」切源时覆盖为中性权威版；cw 特有增补（如 multilingual 简称条目）确认后迁到产品专属文档。