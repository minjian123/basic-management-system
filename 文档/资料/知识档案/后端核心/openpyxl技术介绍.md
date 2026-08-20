# openpyxl 技术介绍

> Excel 读写库 · BMS 导入导出

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [后端核心](../技术栈知识档案总览.md#backend) › openpyxl 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**openpyxl** 是一个纯 Python 实现的 **Excel（Office Open XML）读写库**，
能读取与写出 `xlsx / xlsm / xltx / xltm` 等 2010+ 格式文件，
支持单元格读写、样式、公式、图表、数据校验等。
它是 Python 生态处理 xlsx 的事实标准，在 BMS 中支撑
**用户批量导入**与**列表导出**两类通用能力。

- **定位**：BMS Excel 读写（导入 / 导出）。
- **版本**：3.1.x 系列（持续维护，建议锁定依赖版本）。
- **许可**：MIT，OSI 认证开源。
- **语言**：Python（要求 3.8+，本项目 3.14+），纯 Python、无原生依赖。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Workbook | 一个 Excel 文件对象，包含一个或多个 Worksheet，是读写的入口 |
| Worksheet | 工作表（一个 sheet），由单元格网格组成，可读写行/列 |
| Cell | 单个单元格，有值（value）、坐标（row/column）、样式 |
| 读写模式 | `load_workbook` 读、`Workbook()` 建；`read_only`/`write_only` 模式省内存 |
| iter_rows | 按行迭代单元格的值，导入时逐行解析的常用方式 |
| append | 向工作表追加一行，导出时批量写数据的常用方式 |
| 样式（Style） | 字体、填充、边框、对齐、数字格式，导出时可美化表头与列宽 |
| 数据校验 | 单元格级校验（下拉、数值范围等），导入模板可约束用户填写 |
| 阻塞 I/O | 读写文件是同步阻塞操作，大文件耗时，需放线程池或交给 Celery 异步执行 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 支撑**用户批量导入**：解析上传的 xlsx，逐行校验后落库（见《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节、功能模块「导入导出」）。
- 支撑**列表导出**：把查询结果写为 xlsx 返回下载（见《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节）。
- 导入为写操作，支持**幂等键**（请求头 `Idempotency-Key`）防重复提交（见《[项目规划说明](../../../规划/项目规划说明.md#api)》8 节 API 设计规范）。
- 导出涉及敏感字段时做**脱敏**（手机号/邮箱掩码），持 `data:plain` 权限码才出明文（见《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节数据脱敏）。
- openpyxl 为同步库、阻塞 I/O，导入/导出应放入**线程池或 Celery 任务**执行，避免卡住事件循环（见《[FastAPI 技术介绍](FastAPI技术介绍.md)》注意事项）。
- 导入模板、导出文件经 [python-multipart](python-multipart技术介绍.md) 上传、产物可存 [MinIO](MinIO技术介绍.md)（见《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》文件管理）。
- 验收口径：「Excel 导入导出可用」纳入功能测试与 MVP 验收（见《[项目规划说明](../../../规划/项目规划说明.md#test)》16 节）。

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **openpyxl（选中）** | 纯 Python、无原生依赖、xlsx 读写全功能、社区主流 | Python 处理 xlsx 的默认选择 |
| xlsxwriter | 写性能强，但**只能写不能读**，无法做导入 | 不满足「导入 + 导出」双向需求 |
| xlrd | 老牌读取库，但只支持旧版 .xls，对 xlsx 支持已移除 | 格式不匹配，不适用 |
| pandas + 引擎 | 分析能力强，但偏数据分析、依赖重、样式控制弱 | 杀鸡用牛刀，导入导出用 openpyxl 更轻 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **阻塞事件循环**：读写 xlsx 是同步 CPU + I/O 操作，在 `async def` 接口里直接调用会卡住进程，需放线程池（`run_in_executor`）或交给 Celery。
- **大文件内存**：默认模式把整表载入内存，大文件易 OOM；导入用 `read_only=True`、导出用 `write_only=True` 流式处理。
- **只支持 2010+ 格式**：openpyxl 不读旧版 `.xls`，导入需明确告知用户用 `.xlsx`，或前置转换。
- **类型与精度**：Excel 数字可能变 float、长数字（如雪花 ID、手机号）丢精度或变科学计数法，导入时按列显式解析为字符串/整数。
- **公式与样式**：默认读到的可能是公式而非计算值（需 `data_only=True` 读缓存值）；导出样式要单独设置。
- **脱敏与权限**：导出前按数据权限与脱敏规则过滤，避免越权导出敏感明文（见《[安全开发规范](../../../规范/安全开发规范.md)》）。
- **版本锁定**：3.1.x 迭代中，升级后需回归导入解析与导出渲染用例。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| openpyxl 官方文档 | https://openpyxl.readthedocs.io/ | 权威文档：读写、样式、公式、性能模式 |
| openpyxl 源码（Heptapod） | https://foss.heptapod.net/openpyxl/openpyxl | 官方源码仓库与 issue（已从 Bitbucket 迁移） |
| openpyxl PyPI | https://pypi.org/project/openpyxl/ | 版本历史与安装信息 |
| xlsxwriter（对照） | https://xlsxwriter.readthedocs.io/ | 只写型对照库，了解取舍 |
| pandas Excel I/O | https://pandas.pydata.org/docs/user_guide/io.html | 数据分析场景的 Excel 读写（对照参考） |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-backend)》2.1 节 | 后端技术栈：Excel 处理（openpyxl）条目 |
| 《[项目规划说明](../../../规划/项目规划说明.md#modules)》5 节 | 功能模块：导入导出（用户批量导入、列表导出） |
| 《[项目规划说明](../../../规划/项目规划说明.md#api)》8 节 | API 设计规范：导入幂等键约定 |
| 《[项目规划说明](../../../规划/项目规划说明.md#security)》12 节 | 认证与安全：导出脱敏、data:plain 权限 |
| 《[python-multipart 技术介绍](python-multipart技术介绍.md)》 | 导入文件上传解析 |
| 《[MinIO 技术介绍](MinIO技术介绍.md)》 | 导出产物 / 导入模板的对象存储 |
| 《[FastAPI 技术介绍](FastAPI技术介绍.md)》 | 同步阻塞库需放线程池/Celery 的运行约束 |
| 《[安全开发规范](../../../规范/安全开发规范.md)》 | 导出脱敏与越权防护 |

---

> 本文档为 AI 生成 · 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19