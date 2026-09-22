<script setup lang="ts">
// 模块边界：捕获模块视图渲染 / 加载错误，渲染错误页兜底（带模块名与版本），支持单模块重试。
import { ErrorPage } from '@bms/ui-ep'
import { onErrorCaptured } from 'vue'
import { useRoute } from 'vue-router'

import { reportModuleError } from '@/observability'
import { setModuleError, useModuleError } from '../module/boundary'
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

onErrorCaptured((caught) => {
  const resolved = resolveRouteModule(route.name)
  const moduleName = props.module || resolved?.name || 'platform'
  const moduleVersion = props.version || resolved?.version || ''
  const reason = caught instanceof Error ? caught.message : String(caught)
  reportModuleError(moduleName, moduleVersion, 'render', caught)
  setModuleError({ module: moduleName, version: moduleVersion, reason })
  return false
})

// 单模块重试（仅重挂该模块，不整页刷新）；平台页面无模块可重挂时退回整页刷新。
async function retry(): Promise<void> {
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
    v-if="error !== null"
    :code="500"
    :title="`模块加载失败：${error.module}`"
    :description="`模块 ${error.module}@${error.version} 加载失败 —— ${error.reason}`"
    :retry="true"
    @retry="retry"
  />
  <slot v-else />
</template>
