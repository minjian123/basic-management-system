<script setup lang="ts">
// 用户详情宿主页（**具名插槽宿主**）：只声明挂接点，**不 import 任何具体插件**。
// 插槽项由平台自身注册与模块注册经统一通道登记，按权限与顺序渲染；未登记即空（不兜底、不报错）。
import { ModuleAreaOutlet, PageContainer, SectionContainer } from '@bms/ui-ep'
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { registries, registriesRevision } from '@/module/registries'
import { useSessionStore } from '@/stores/session'

defineOptions({ name: 'SysUserDetail' })

/** 具名插槽标识（`{域}.{页面}.{区域}`）。 */
const USER_DETAIL_TABS = 'sys.user.detail.tabs'

const route = useRoute()
const session = useSessionStore()

/** 路由参数指定的用户标识（宿主页把作用实体标识放路由参数，插槽项经注入 router 只读读取）。 */
const userId = computed(() => String(route.params.id ?? ''))

/** 已持有权限码（插槽项按权限显隐；随会话变化刷新）。 */
const permissionCodes = computed(() => session.codes)
</script>

<template>
  <page-container title="用户详情" :description="`用户标识：${userId}`">
    <section-container title="扩展信息">
      <!-- 具名插槽：平台内建项与插件项同槽，按顺序提示与权限渲染；空区域渲染为空 -->
      <module-area-outlet
        :area="USER_DETAIL_TABS"
        variant="tabs"
        :registries="registries"
        :revision="registriesRevision"
        :permission-codes="permissionCodes"
      />
    </section-container>
  </page-container>
</template>
