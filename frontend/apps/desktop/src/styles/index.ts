/**
 * 宿主样式聚合入口（**唯一**样式引入落点）。
 *
 * 应用入口（`main.ts`）与全部开发态核对页入口（`src/dev/*.ts`）统一引本文件——核对页各有独立
 * HTML 入口，不引本文件就会渲染出无 Element Plus 底样式的组件库件（2026-10-03 实测发现）。
 *
 * 顺序口径（强制）：第三方 UI 库样式（Element Plus）**早于**设计令牌。`tokens.scss` 内的
 * `--el-*` 主题映射依赖「同优先级后声明覆盖」赢过 Element Plus 默认值，顺序颠倒会使主题色
 * 回退 EP 默认蓝。新增样式文件一律在此登记。
 *
 * 护栏：`tests/guard-library-components.spec.ts` 断言「仅本文件引 `tokens.scss`」且本文件内
 * EP 样式行号在令牌之前。
 */

import 'element-plus/dist/index.css'
import './tokens.scss'
