<script setup lang="ts">
// 顶栏区域条目（**紧凑件**）：只做**接线**——渲染 Element Plus `ElButton`，点击进模块的「组件契约演示」整页
// （`/demo/toolbox`）。
//
// 依据（强制）：
// - 《前端开发规范》「组件库件复用」：业务侧（宿主应用与**运行时模块**）模板内**不得出现裸原生交互元素**
//   （`<input>`/`<button>`/…），一律经组件库件 / Element Plus 基础件承载；缺件先补进 `@bms/ui-ep` 并在
//   《组件设计》登记。护栏：`apps/desktop/tests/guard-library-components.spec.ts`（`button` 的替代件即
//   `ElButton`）。
// - 区域条目契约：`layout.header` 是一行高窄容器，**只注册紧凑件**；整页/大面板走页面路由
//   （回归：曾整页 `DemoToolbox` 误注册进顶栏，页面 DOM 溢出污染框架页，见 05 域 `06_01` 台账）。
//
// 导航经**宿主注入上下文**（`context.router`）消费——模块不 import / 不持有宿主 router 实例；
// 未注入时回落整页跳转（独立预览场景）。
import { ElButton } from 'element-plus'

import { hostRouterOf } from '../runtime'

defineOptions({ name: 'DemoToolboxEntry' })

/** 进「组件契约演示」整页（宿主 router 优先，未注入回落整页跳转）。 */
function openToolbox(): void {
  const router = hostRouterOf()
  if (router?.push !== undefined) {
    void router.push('/demo/toolbox')
    return
  }
  window.location.assign('/demo/toolbox')
}
</script>

<template>
  <el-button data-test="demo-toolbox-entry" link size="small" type="primary" @click="openToolbox">
    组件契约演示
  </el-button>
</template>
