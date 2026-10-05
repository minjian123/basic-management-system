<script setup lang="ts">
// 图标只读渲染件（08_02）：按 icon key 统一解析多来源图标（官方 / 业务 / 自定义），未知降级 + 去重告警。
import type { IconRegistry } from '@bms/core'
import { computed, ref, shallowRef, watch, type Component } from 'vue'

import { ensureOfficialIcons } from '../../icons/official'
import { useIconRegistry } from '../../composables/useIconRegistry'
import { sanitizeSvg } from '../../utils/sanitizeHtml'

interface Props {
  /** icon key（`el:` / `biz:` / `custom:`；无前缀按 `el:` 兼容）。 */
  name?: string
  /** 尺寸（数字 px 或 CSS 长度）。 */
  size?: number | string
  /** 颜色（缺省继承 `currentColor`）。 */
  color?: string
  /** 是否旋转（加载态）。 */
  spin?: boolean
  /** 兜底图标名（官方图标名，缺省 `QuestionFilled`）。 */
  fallback?: string
  /** 图标注册表（缺省取活动注册表）。 */
  registry?: IconRegistry
}

const props = withDefaults(defineProps<Props>(), {
  name: '',
  size: 16,
  color: 'currentColor',
  spin: false,
  fallback: 'QuestionFilled',
  registry: undefined,
})

const emit = defineEmits<{
  resolved: [key: string]
  missing: [key: string]
}>()

const registry = useIconRegistry(props.registry)
const iconSource = shallowRef<unknown>(undefined)
const resolvedKey = ref('')
const warned = new Set<string>()

/** 解析 icon key 前缀（历史裸名按 `el:` 兼容）。 */
function parseKey(key: string): { prefix: string; raw: string } {
  const index = key.indexOf(':')
  if (index < 0) {
    return { prefix: 'el', raw: key }
  }
  return { prefix: key.slice(0, index), raw: key.slice(index + 1) }
}

/**
 * `el:` 键名归一为 PascalCase（兼容 `setting` / `office-building` / `Setting` 三种写法）。
 *
 * 官方图标注册表键为 `el:{PascalCase}`（`@element-plus/icons-vue` 组件名）；菜单种子等数据源
 * 可能写全小写或 kebab-case，此处统一归一，避免图标静默缺失（消费面只见降级兜底图标）。
 *
 * @param raw 前缀后的原始名。
 * @returns PascalCase 名称。
 */
function toPascalCase(raw: string): string {
  return raw
    .split(/[-_\s]+/)
    .filter((part) => part !== '')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join('')
}

/** 解析并渲染图标。 */
async function resolveIcon(key: string): Promise<void> {
  resolvedKey.value = ''
  iconSource.value = undefined
  if (key === '') {
    return
  }
  await ensureOfficialIcons(registry)
  const parsed = parseKey(key)
  iconSource.value =
    parsed.prefix === 'el' ? registry.get(`el:${toPascalCase(parsed.raw)}`)?.source : registry.resolve(key)
  if (iconSource.value === undefined) {
    if (!warned.has(key)) {
      warned.add(key)
      console.warn(`[IconRenderer] 图标不可用：${key}`)
    }
    emit('missing', key)
    return
  }
  resolvedKey.value = key
  emit('resolved', key)
}

watch(
  () => props.name,
  (key) => {
    void resolveIcon(key)
  },
  { immediate: true },
)

/** 尺寸样式值。 */
const sizeValue = computed(() => (typeof props.size === 'number' ? `${props.size}px` : props.size))

/** 渲染组件（Vue 组件来源）。 */
const componentSource = computed<Component | undefined>(() => {
  const source = iconSource.value
  if (source !== undefined && (typeof source === 'object' || typeof source === 'function')) {
    return source as Component
  }
  return undefined
})

/** 是否为内联 SVG 文本来源（经清洗）。 */
const svgHtml = computed(() => {
  const source = iconSource.value
  if (typeof source !== 'string') {
    return ''
  }
  return sanitizeSvg(source)
})

/** 兜底组件。 */
const fallbackComponent = computed<Component | undefined>(
  () => registry.get(`el:${props.fallback}`)?.source as Component | undefined,
)

/** 生效组件（未解析时用兜底）。 */
const activeComponent = computed<Component | undefined>(() => componentSource.value ?? fallbackComponent.value)
</script>

<template>
  <span
    v-if="name"
    class="bms-icon-renderer"
    data-test="icon-renderer"
    :data-icon="name"
    :data-resolved="resolvedKey || undefined"
    :data-missing="resolvedKey ? undefined : 'true'"
    :data-spin="spin || undefined"
    :style="{ width: sizeValue, height: sizeValue, color, fontSize: sizeValue }"
  >
    <component :is="activeComponent" v-if="activeComponent" />
    <!-- eslint-disable-next-line vue/no-v-html -- 自定义图标 SVG 已经 DOMPurify 白名单清洗 -->
    <span v-else-if="svgHtml" data-test="icon-svg" v-html="svgHtml" />
  </span>
</template>

<style scoped>
.bms-icon-renderer {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex: none;
  line-height: 1;
}

/* 官方图标组件的 `<svg>` 无内联尺寸（依赖 `.el-icon` 包裹的 CSS）；此处统一按 1em 约束，
   否则 svg 会以浏览器默认尺寸溢出容器（表现为图标被裁切 / 与相邻元素重叠）。 */
.bms-icon-renderer :deep(svg) {
  width: 1em;
  height: 1em;
  fill: currentColor;
}
</style>
