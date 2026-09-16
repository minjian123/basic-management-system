<script setup lang="ts">
/**
 * 根系组件包装（可选形态）：把根系能力经插槽下发给子树，并绑定组件生命周期钩子。
 *
 * 逻辑代码优先直接用 `useFrontendBase()`；本组件用于需要在模板层统一分发根系能力的场景。
 */

import { onMounted, onUnmounted } from 'vue'

import type { FrontendBaseOptions } from './BaseFrontend'
import { useFrontendBase } from './useFrontendBase'

const props = defineProps<FrontendBaseOptions>()

const emit = defineEmits<{
  /** 根系就绪（组件挂载后） */
  created: []
  /** 根系释放（组件卸载后） */
  disposed: []
}>()

const options: FrontendBaseOptions = {}
if (props.ns) {
  options.ns = props.ns
}
if (props.identifier) {
  options.identifier = props.identifier
}

const base = useFrontendBase(options)

onMounted(() => emit('created'))
onUnmounted(() => {
  base.dispose()
  emit('disposed')
})
</script>

<template>
  <slot :base="base" />
</template>
