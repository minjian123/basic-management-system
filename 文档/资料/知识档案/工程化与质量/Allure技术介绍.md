# Allure 技术介绍

> 多语言自动化测试报告框架 · BMS 测试报告与 CI 产物

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [工程化与质量](../技术栈知识档案总览.md#eng) › Allure 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**Allure**（全称 Allure Report）是一个多语言的自动化测试报告工具：
各测试框架把执行结果写成统一的中间格式（Allure Results），再由 Allure CLI 渲染成
一份可交互的静态网页报告——步骤、附件、失败分类、历史趋势一应俱全。
它不关心你用什么语言写测试，只关心结果的呈现与归档。

- **定位**：BMS 自动化测试报告框架——pytest（后端单元/接口测试）与 Playwright（E2E）的结果统一生成美观报告，作为 CI 产物归档。
- **版本**：2.x 系列（最新 2.45.0，2026-08 发布；迭代快，CI 中锁定版本）。
- **许可**：Apache-2.0，OSI 认证开源。
- **运行要求**：CLI 是 Java 程序，需要 JRE（版本要求以官方文档为准）；各语言的集成插件独立安装。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 一句话说明 |
| --- | --- |
| Allure Results | 中间结果格式：每个测试用例一个 JSON 文件，统一放在 `allure-results/` 目录，与语言无关，是报告的唯一数据源 |
| Allure Report | 静态网页报告（纯 HTML/JS）：由 CLI 从 Results 渲染生成，浏览器直接打开，无需后端服务 |
| Allure CLI | Java 命令行工具：`generate`（生成报告）、`open`（生成并起本地服务打开）、`serve`（不落地直接预览） |
| 集成插件 | 各框架的官方适配层：Python 用 `allure-pytest`，Playwright 用 `allure-playwright`，负责把框架事件翻译成 Results |
| Steps（步骤） | 用例内的执行步骤分解（API 调用、断言、页面操作），报告里可逐层展开，失败时直接定位到具体一步 |
| Labels 与 Links | 元数据标注：severity（严重级别）、tag（标签）；issue/tms 链接可指向缺陷系统与用例库（如 GitLab Issue、Kiwi TCMS 用例） |
| Categories（失败分类） | 按正则把失败归入"环境问题 / 产品缺陷 / 用例问题"等类别，报告首页直接给出分类统计，避免逐条翻 |
| History（历史趋势） | 跨多次运行的通过率趋势图：需要保留 `allure-results/history` 目录并在下次生成时带上，CI 里靠 artifact 传递 |
| Attachments（附件） | 截图、日志、请求报文等二进制/文本附件，报告内可在线查看；Playwright 的 trace 与截图走这里 |
| Environment Info | 运行环境信息（OS、版本、分支、构建号），报告头部展示，方便复现问题环境 |
| 两层结构 | Results（数据）与 Report（呈现）分离：数据可长期归档、跨平台流转，报告随时可重新渲染 |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- 后端 pytest 与前端 Playwright 的自动化测试结果，统一经 Allure 插件生成可视化报告（见《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节"测试报告：Allure"）。
- 报告作为 **CI 产物归档**：GitLab MR/main 流水线中生成 Allure 报告并保留为 job artifact，随时回看（见《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节流水线说明）。
- 结果**双出口**：Allure 负责"看得见的报告"，执行结果同时经 Kiwi TCMS 官方 pytest 插件导入用例库归档，平台统计执行情况与历史（见《[Kiwi TCMS 技术介绍](KiwiTCMS技术介绍.md)》）。
- 全量回归（每阶段末、MVP 验收前）的结果以 Allure 报告形式留档，作为验收材料（见《[项目规划说明](../../../规划/项目规划说明.md#test-report)》16.5 节"测试报告"）。
- 用例命名与分类使用中文（按模块 Category + 标签 Tag），Allure 报告完整支持中文展示。

常用命令（Windows 调用 `allure.bat`，Linux/macOS 调用 `allure`）：

```bash
# 安装 pytest 集成插件（Windows/Linux 相同）
python -m pip install allure-pytest

# 跑测试并输出 Allure 结果
pytest --alluredir=allure-results

# 生成静态报告 / 生成并打开
allure generate allure-results -o allure-report
allure open allure-report
```

Playwright 侧（前端工程）：

```bash
npm install -D allure-playwright
# playwright.config.ts 中登记 reporter
reporter: [["line"], ["allure-playwright"]]
npx playwright test
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **Allure（选中）** | 多语言统一报告（pytest/Playwright 同一套）；步骤、附件、失败分类、历史趋势齐全；静态报告易归档分发<br>缺点：CLI 依赖 JRE，多一个运行时 | 后端 pytest + 前端 Playwright 双栈需要统一报告出口，Allure 是唯一同时成熟支持两者的方案 |
| pytest-html | 轻量、纯 Python<br>缺点：单页平铺、无步骤分解与历史趋势，且只覆盖 pytest，Playwright 结果无法并入 | 只够看单次结果，撑不起回归报告与验收材料 |
| Playwright 自带 HTML reporter | 零配置、trace 体验好<br>缺点：只覆盖 E2E，与后端结果割裂，无跨语言汇总 | 保留用于本地调试，不作品级报告出口 |
| Kiwi TCMS 内置执行统计 | 与用例库一体、有历史<br>缺点：面向用例执行管理，不是可视化测试报告，无附件/步骤级展示 | 与 Allure 互补而非替代：用例归档走 Kiwi TCMS，报告走 Allure |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **CLI 需要 JRE**：Allure CLI 是 Java 程序，CI 镜像与开发机都要装好 Java，否则 `allure generate` 直接报错。
- **Results 与 Report 别混**：`allure-results/` 是数据（要归档、传历史），`allure-report/` 是渲染产物（可随时重建）；CI 两者都保留。
- **历史趋势要"接力"**：趋势图依赖上次运行的 history 数据，流水线里要把上次的 `allure-results/history` 带进本次生成，否则每次都从零开始。
- **Windows 命令名差异**：官方发行包在 Windows 下是 `allure.bat`，Linux/macOS 是 `allure`；脚本里按平台区分调用。
- **附件别贪大**：大视频、大日志塞进附件会让报告体积暴涨、CI 产物超限；只放定位问题必需的截图与关键日志。
- **与 Kiwi TCMS 的分工**：Allure 不管理用例、Kiwi TCMS 不出报告，两条线并行归档，不要试图用一方替代另一方。
- **版本锁定**：Allure 迭代快（2.x 小版本月更），CI 中固定 CLI 版本与插件版本，升级时重跑一轮全量报告确认格式无回归。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| Allure 官网 | https://allurereport.org/ | 官方首页，特性与版本信息 |
| Allure 官方文档 | https://allurereport.org/docs/ | 安装、CLI、各框架集成、报告配置 |
| Allure GitHub | https://github.com/allure-framework/allure2 | 报告引擎源码与 release 下载 |
| allure-pytest | https://github.com/allure-framework/allure-python | Python/pytest 官方集成插件 |
| allure-playwright | https://github.com/allure-framework/allure-js | Playwright 官方集成（allure-js 仓库内） |
| Playwright 集成文档 | https://allurereport.org/docs/playwright/ | Playwright + Allure 配置与 API 示例 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-eng)》2.3 节 | 工程化与质量技术栈（测试报告：Allure 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-eng)》3.3 节 | 选型说明：Allure 自动化测试报告（pytest/Playwright 结果生成，CI 产物归档） |
| 《[项目规划说明](../../../规划/项目规划说明.md#test-report)》16.5 节 | 测试报告：后端 pytest + Allure 生成自动化测试报告 |
| 《[开发部署规划](../../../规划/开发部署规划.md)》7 节 | 开发工作流与 CI：Allure 报告生成归档、结果导入 Kiwi TCMS |
| 《[Kiwi TCMS 技术介绍](KiwiTCMS技术介绍.md)》 | 用例库归档出口，与 Allure 报告双轨并行 |
| 《[pytest 技术介绍](pytest技术介绍.md)》 | allure-pytest 插件与 `--alluredir` 用法 |
| 《[Playwright 技术介绍](../前端/Playwright技术介绍.md)》 | allure-playwright reporter 配置 |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19