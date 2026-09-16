<script setup lang="ts">
/**
 * 组件根组件包装（可选形态）：单根元素 + attrs 透传合并 + 插槽下发组件根能力。
 *
 * 逻辑代码优先直接用 `useComponentBase()`；本组件用于需要在模板层统一分发组件根能力的场景。
 */

import { computed, onMounted, onUnmounted, useAttrs } from 'vue'

import { normalizeClassList, type ComponentDensity, type ComponentSize } from './BaseComponent'
import { useComponentBase } from './useComponentBase'

defineOptions({ inheritAttrs: false })

const props = withDefaults(
  defineProps<{
    ns?: string
    identifier?: string
    size?: ComponentSize
    density?: ComponentDensity
    loading?: boolean
    disabled?: boolean
    visible?: boolean
    dataTest?: string
  }>(),
  {
    ns: 'bms',
    identifier: '',
    size: 'default',
    density: undefined,
    loading: false,
    disabled: false,
    visible: true,
    dataTest: '',
  },
)

const emit = defineEmits<{
  /** 组件挂载后 */
  'base-mounted': []
  /** 组件卸载（先释放再发事件） */
  'base-unmounted': []
}>()

const attrs = useAttrs()
const base = useComponentBase(props)

/** 内部属性（令牌 / 可访问性 / 状态类）与外部透传属性合并：内部状态类在前，外部 class / style 保留 */
const rootAttrs = computed(() => {
  const own = base.rootAttrs()
  const external = { ...attrs } as Record<string, unknown>
  delete external.class
  delete external.style
  const merged: Record<string, unknown> = { ...own, ...external }
  const classes = [...normalizeClassList(own.class), ...normalizeClassList(attrs.class)]
  if (classes.length > 0) {
    merged.class = classes
  }
  if (attrs.style !== undefined) {
    merged.style = attrs.style
  }
  return merged
})

onMounted(() => {
  base.notifyLifecycle('mounted')
  emit('base-mounted')
})

onUnmounted(() => {
  base.notifyLifecycle('unmounted')
  base.dispose()
  emit('base-unmounted')
})

defineExpose({ base, mechanisms: base.mechanisms, setProps: base.setProps })
</script>

<template>
  <div v-if="base.visible" v-bind="rootAttrs">
    <slot :base="base" />
  </div>
</template>
