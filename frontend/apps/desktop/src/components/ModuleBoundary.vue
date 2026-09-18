<script setup lang="ts">
// 模块边界：捕获模块视图渲染 / 加载错误，渲染错误页兜底（带模块名与版本）。
import { ErrorPage } from '@bms/ui-ep'
import { onErrorCaptured } from 'vue'

import { setModuleError, useModuleError } from '../module/boundary'

interface Props {
  /** 模块名。 */
  module?: string
  /** 模块版本。 */
  version?: string
}

const props = withDefaults(defineProps<Props>(), { module: '', version: '' })

const error = useModuleError()

onErrorCaptured((caught) => {
  setModuleError({
    module: props.module,
    version: props.version,
    reason: caught instanceof Error ? caught.message : String(caught),
  })
  return false
})

function retry(): void {
  window.location.reload()
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
