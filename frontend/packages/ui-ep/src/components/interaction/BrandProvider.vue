<script setup lang="ts">
// 品牌应用器：包裹应用根；挂载前同步预读主题（防闪烁），品牌与模式变更即时注入根元素（data-theme + 品牌令牌 + 标题 / favicon）。
import { onBeforeUnmount, watch } from 'vue'

import type { BasePersistedState, BrandConfig, ThemeMode } from '@bms/core'
import { useBaseTheme } from '../../composables/useBaseTheme'

interface Props {
  /** 租户品牌配置（空则用平台默认）。 */
  brand?: BrandConfig
  /** 主题模式（`v-model:mode`，写用户偏好）。 */
  mode?: ThemeMode
  /** 是否监听系统偏好。 */
  followSystem?: boolean
  /** 偏好持久化通道（`themeMode` 真源）。 */
  persisted?: BasePersistedState
  /** 是否设置文档标题。 */
  applyTitle?: boolean
  /** 是否设置 favicon。 */
  applyFavicon?: boolean
  /** 卸载时是否还原根属性。 */
  restoreOnUnmount?: boolean
  /** 品牌解析 / 加载态（展示兜底插槽）。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  brand: undefined,
  mode: undefined,
  followSystem: true,
  persisted: undefined,
  applyTitle: true,
  applyFavicon: true,
  restoreOnUnmount: false,
  loading: false,
})

const emit = defineEmits<{
  'update:mode': [value: ThemeMode]
  applied: [payload: { resolved: 'light' | 'dark'; primary: string }]
  'brand-error': [payload: { message: string }]
}>()

const { theme, mode, resolved, primary, setBrand, setMode, applyToElement, preload } = useBaseTheme({
  brand: props.brand,
  mode: props.mode,
  followSystem: props.followSystem,
  persisted: props.persisted,
  applyTitle: props.applyTitle,
  applyFavicon: props.applyFavicon,
})

/**
 * 探测品牌资源可用性（不可用则降级并发事件）。
 *
 * @param brand 品牌配置。
 */
const probeBrandAssets = (brand?: BrandConfig): void => {
  const source = brand?.favicon
  if (source === undefined || source === '' || typeof globalThis.Image !== 'function') {
    return
  }
  const probe = new globalThis.Image()
  probe.onerror = () => emit('brand-error', { message: `品牌资源不可用：${source}` })
  probe.src = source
}

// 挂载前同步预读：解析主题并写入根元素（避免首屏闪白 / 闪黑）。
const initialResolved = preload()
emit('applied', { resolved: initialResolved, primary: primary.value })
probeBrandAssets(props.brand)

watch(
  () => props.brand,
  (value) => {
    setBrand(value)
    applyToElement()
    emit('applied', { resolved: resolved.value, primary: primary.value })
    probeBrandAssets(value)
  },
  { deep: true },
)

watch(
  () => props.mode,
  (value) => {
    if (value !== undefined && value !== mode.value) {
      setMode(value)
      applyToElement()
      emit('applied', { resolved: resolved.value, primary: primary.value })
    }
  },
)

watch(resolved, () => applyToElement())

onBeforeUnmount(() => {
  if (!props.restoreOnUnmount) {
    return
  }
  const element = globalThis.document?.documentElement
  if (element === undefined) {
    return
  }
  element.removeAttribute('data-theme')
  for (const name of Object.keys(theme.brandTokens)) {
    element.style.removeProperty(name)
  }
})
</script>

<template>
  <div class="bms-brand-provider" :data-theme="resolved" :data-loading="loading ? 'true' : 'false'" data-test="brand-provider">
    <slot v-if="!loading" :resolved="resolved" :primary="primary" />
    <slot v-else name="fallback" />
  </div>
</template>

<style scoped>
.bms-brand-provider {
  display: contents;
}
</style>
