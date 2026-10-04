<script setup lang="ts">
// 模块边界：捕获模块视图渲染 / 加载错误，渲染错误页兜底（带模块名与版本），支持单模块重试。
//
// 作用域口径（需求 01-7）：模块**加载 / 清单失败**只阻断「归属该失败模块」的路由；免登录 / 基础路由
// （`/login` / `/403` / `/404` / `/500`）与平台自身路由不受影响——模块产物服务不可用时仍能正常登录；
// **当前路由自身渲染失败**仍渲染错误页（保持既有行为，带重试）。
import { ErrorPage } from '@bms/ui-ep'
import { computed, onErrorCaptured, ref } from 'vue'
import { useRoute } from 'vue-router'

import { reportModuleError } from '@/observability'
import { resolvePublicPaths } from '@/router/guard'
import { blocksModuleFailure, setModuleError, useModuleError } from '../module/boundary'
import { resolveRouteModule, retryModule } from '../module/host'

interface Props {
  /** 模块名（缺省按当前路由解析所属模块）。 */
  module?: string
  /** 模块版本（缺省按当前路由解析所属模块）。 */
  version?: string
}

const props = withDefaults(defineProps<Props>(), { module: '', version: '' })

const route = useRoute()
const error = useModuleError()

/** 当前路由自身渲染失败（本地标记：不受全局错误态清理影响）。 */
const renderFailed = ref(false)

/** 兜底展示态：渲染失败（当前路由）或模块失败阻断本路由时非空。 */
const failure = computed(() => {
  const resolved = resolveRouteModule(route.name)
  if (renderFailed.value) {
    return (
      error.value ?? {
        module: props.module || resolved?.name || 'platform',
        version: props.version || resolved?.version || '',
        reason: '视图渲染失败',
      }
    )
  }
  const global = error.value
  if (global === null) {
    return null
  }
  const blocked = blocksModuleFailure({
    failure: global,
    path: route.path,
    routeModule: resolved?.name,
    publicPaths: resolvePublicPaths(),
  })
  return blocked ? global : null
})

onErrorCaptured((caught) => {
  const resolved = resolveRouteModule(route.name)
  const moduleName = props.module || resolved?.name || 'platform'
  const moduleVersion = props.version || resolved?.version || ''
  const reason = caught instanceof Error ? caught.message : String(caught)
  reportModuleError(moduleName, moduleVersion, 'render', caught)
  setModuleError({ module: moduleName, version: moduleVersion, reason })
  renderFailed.value = true
  return false
})

// 单模块重试（仅重挂该模块，不整页刷新）；平台页面无模块可重挂时退回整页刷新。
async function retry(): Promise<void> {
  renderFailed.value = false
  const resolved = resolveRouteModule(route.name)
  const moduleName = props.module || resolved?.name || ''
  if (moduleName === '' || moduleName === 'platform') {
    window.location.reload()
    return
  }
  try {
    await retryModule(moduleName)
  } catch {
    window.location.reload()
  }
}
</script>

<template>
  <error-page
    v-if="failure !== null"
    :code="500"
    :title="`模块加载失败：${failure.module}`"
    :description="`模块 ${failure.module}@${failure.version} 加载失败 —— ${failure.reason}`"
    :retry="true"
    @retry="retry"
  />
  <slot v-else />
</template>
