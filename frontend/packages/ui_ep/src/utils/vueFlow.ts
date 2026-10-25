/**
 * vue-flow 单一落点：集中引入画布内核与附带背景 / 控件（含样式）。
 *
 * 仅由自由画布 `ScreenCanvas.vue` 动态装载（独立分包，不进首屏）；其它组件不得直接引入 `@vue-flow/*`。
 */

import '@vue-flow/core/dist/style.css'
import '@vue-flow/core/dist/theme-default.css'
import '@vue-flow/controls/dist/style.css'

import { Background } from '@vue-flow/background'
import { Controls } from '@vue-flow/controls'
import { VueFlow, type Node as VueFlowNode, type NodeProps as VueFlowNodeProps } from '@vue-flow/core'

export { Background, Controls, VueFlow }
export type { VueFlowNode, VueFlowNodeProps }

/** 画布内核标识（降级判定与用例断言用）。 */
export const VUE_FLOW_KERNEL = 'vue-flow'
