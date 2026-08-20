# ESLint 与 Prettier 技术介绍

> 代码规范双工具 · BMS 前端质量门禁

[文档首页](../../../文档首页.md) › [知识档案](../技术栈知识档案总览.md) › [前端](../技术栈知识档案总览.md#frontend) › ESLint 与 Prettier 技术介绍　|　[← 返回总览](../技术栈知识档案总览.md)

---

## 1. 技术概述 <a id="overview"></a>

**ESLint** 是可插拔的 JavaScript/TypeScript
代码质量检查器，查的是**错误与坏味道**
（未定义变量、不可达代码、Vue 模板问题等）；
**Prettier** 是有主见的代码格式化工具，
管的是**统一格式**（缩进、引号、换行、分号）。
两者分工明确：ESLint 管错、Prettier 管格式，
用 `eslint-config-prettier` 关掉 ESLint 里
与 Prettier 冲突的格式规则，避免「两个工具打架」。

- **定位**：BMS 前端代码规范工具链，MR 流水线门禁之一（见《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节）。
- **版本**：ESLint 10.x（v10.0.0 于 2026 年 2 月发布，flat config 为唯一配置格式；9.x 已于 2026 年 8 月 EOL）；Prettier 3.9.x（截至 2026 年）。
- **许可**：均为 MIT，OSI 认证开源。
- **Vue 插件链**：eslint-plugin-vue（Vue 官方）+ typescript-eslint + eslint-config-prettier（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。

## 2. 核心概念与原理 <a id="principles"></a>

| 概念 | 说明 |
| --- | --- |
| Rule（规则） | ESLint 的最小检查单元，级别三档：`off` 关闭 / `warn` 警告 / `error` 报错 |
| Flat Config | `eslint.config.js` 扁平配置：ESLint 9 起默认、10 起唯一支持的配置格式，数组式组织多组规则 |
| Plugin（插件） | 规则集扩展：`eslint-plugin-vue`（Vue 模板/SFC 规则）、`typescript-eslint`（TS 规则） |
| Shareable Config | 可分享的配置包：`eslint-config-prettier` 专门关闭与 Prettier 冲突的格式类规则 |
| --fix | ESLint 自动修复可修复的规则（未使用变量、部分格式类），`eslint --fix` 一键处理 |
| Prettier Parser | 按文件扩展名自动选解析器（JS/TS/Vue/JSON/MD），无需逐个配置 |
| Prettier 选项 | `printWidth`、`singleQuote`、`semi` 等，统一写在 `.prettierrc`，全团队一份口径 |
| 编辑器集成 | VSCode 装 ESLint + Prettier 扩展，保存即检查/格式化，本地与 CI 同一套配置 |
| CI 门禁 | `npm run lint` 有 error 即流水线失败，规范不靠自觉靠门禁（见《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节） |

## 3. 在 BMS 项目中的用途 <a id="usage"></a>

- **代码规范**：frontend 与 frontend-mobile 双工程各自独立配置（各自 package-lock.json、ESLint/Prettier/TS 配置，互不共享），规范统一、工程独立（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **MR 流水线门禁**：前端 ESLint + Vitest（含 coverage 门禁）+ 双端构建，lint 不过 MR 不能合入（见《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 GitLab CI）。
- **Vue 官方插件链**：eslint-plugin-vue 覆盖 SFC/模板规则，typescript-eslint 覆盖 TS 规则，与 Prettier 经 eslint-config-prettier 解冲突（见《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节）。
- **编辑器体验**：开发机 VSCode 扩展含 ESLint、Prettier（见《[开发部署规划](../../../规划/开发部署规划.md#devpc-tools)》5.1 节），保存即规范，提交前无惊喜。
- **双工程一致**：两个工程规则口径保持一致（同一份规则清单），避免 PC 端与移动端风格分裂。

最小示例（flat config + Prettier 配置）：

```js
// eslint.config.js
import js from '@eslint/js'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'
import prettier from 'eslint-config-prettier'

export default [
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{js,ts,vue}'],
    rules: {
      'vue/multi-word-component-names': 'off',
    },
  },
  prettier, // 必须放最后：关闭与 Prettier 冲突的 ESLint 格式规则
]

// .prettierrc.json
{
  "semi": false,
  "singleQuote": true,
  "printWidth": 100
}
```

## 4. 选型对比 <a id="compare"></a>

| 候选技术 | 优缺点 | 结论 |
| --- | --- | --- |
| **ESLint + Prettier（选中）** | 分工清晰（查错 vs 格式）、Vue/TS 插件链完整、社区最大、MIT | 与 BMS「Vue 3 + TS 双工程 + CI 门禁」诉求完全匹配 |
| Biome | lint + format 一体、速度快；但 Vue 支持仍在实验阶段，规则生态不如 ESLint 全 | Vue 场景成熟度不足，暂不选 |
| ruff | Python 世界 lint + format 一体、极快；但不支持 JS/Vue | 语言不符：后端用 ruff（见《[ruff 技术介绍](../工程化与质量/ruff技术介绍.md)》） |
| Stylelint | CSS 专项 lint 强；但 BMS 样式是 SCSS，当前栈未列入 | 如样式问题突出可后续补充，不阻塞 |
| 自研脚本 | 完全可控；但规则、解析、修复全是坑 | 重复造轮子，不选 |

## 5. 常见问题与注意事项 <a id="pitfalls"></a>

- **eslint-config-prettier 必须放最后**：它靠「后配置覆盖前配置」生效，位置错了冲突规则关不掉。
- **flat config 迁移**：ESLint 9/10 用 `eslint.config.js`，旧 `.eslintrc.*` 在 10 中已移除，老项目要迁移（官方有 `@eslint/v8-to-9-config` codemod）。
- **双工程独立配置**：frontend 与 frontend-mobile 各自一份配置，别跨工程共享文件（规划既定决策）。
- **别在 ESLint 里写格式规则**：缩进、引号、换行全交给 Prettier，ESLint 只管错误类规则。
- **门禁不绕过**：CI 里 lint 有 error 即失败，别用 `--no-verify` 或临时关规则糊弄过去。
- **版本锁定**：ESLint/Prettier/插件版本锁在 package-lock.json，本地与 CI 一致，避免「本地过、CI 挂」。
- **大版本升级走评审**：ESLint 大版本涉及配置迁移，走 [Renovate](../部署与运维/Renovate技术介绍.md) 提 MR + 回归。
- **忽略清单**：`dist`、`node_modules` 等产物在配置里显式忽略，别全量扫。

## 6. 学习与参考资料 <a id="learn"></a>

| 资源 | 网址 | 说明 |
| --- | --- | --- |
| ESLint 官网 | https://eslint.org | 文档、规则目录与迁移指南 |
| ESLint GitHub | https://github.com/eslint/eslint | 源码、Changelog 与 issue |
| Prettier 官网 | https://prettier.io | 选项说明与在线体验 |
| Prettier GitHub | https://github.com/prettier/prettier | 源码与插件开发文档 |
| eslint-plugin-vue | https://github.com/vuejs/eslint-plugin-vue | Vue 官方 ESLint 插件，规则说明详尽 |
| eslint-config-prettier | https://github.com/prettier/eslint-config-prettier | ESLint 与 Prettier 解冲突的官方方案 |
| typescript-eslint | https://github.com/typescript-eslint/typescript-eslint | TypeScript 规则集 |

## 7. 项目内关联文档 <a id="related"></a>

| 文档 | 说明 |
| --- | --- |
| 《[项目规划说明](../../../规划/项目规划说明.md#stack-frontend)》2.2 节 | 前端技术栈（ESLint + Prettier 条目） |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-frontend)》3.2 节 | 选型理由：与 Vue 官方插件链配合 |
| 《[项目规划说明](../../../规划/项目规划说明.md#sel-ops)》3.4 节 | GitLab CI：MR 流水线前端门禁 |
| 《[Vitest 技术介绍](Vitest技术介绍.md)》 | 同一 MR 门禁的单元测试与覆盖率部分 |
| 《[ruff 技术介绍](../工程化与质量/ruff技术介绍.md)》 | 后端对应工具（Python lint + format） |
| 《[pytest 技术介绍](../工程化与质量/pytest技术介绍.md)》 | 后端对应门禁（测试 + 覆盖率） |
| 《[命名规范](../../../规范/命名规范.md)》 | 代码标识符命名口径（工具链执行其一部分） |

---

> 依《[文档生成规范](../../../规范/文档生成规范.md)》编写 · 生成日期：2026-08-19