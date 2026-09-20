<script setup lang="ts">
// 状态标签（07_05）：语义色三层取色 + 五种形态；只读呈现，经展示件投影挂链。
import { describeStatus, type StatusSemantic, type StatusShape } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseDisplay } from '../../composables/useBaseDisplay'

/** 状态标签形态。 */
export type StatusTagShape = StatusShape

/** 语义色五档。 */
export type StatusTagSemantic = StatusSemantic

interface Props {
  /** 状态值（库值，取色与内置映射的输入）。 */
  value?: string | number | boolean | null
  /** 展示文案（缺省回退原值文本）。 */
  text?: string
  /** 显式语义色（最高优先级）。 */
  semantic?: StatusTagSemantic
  /** 数据源自带色（字典条目 / 枚举选项）。 */
  sourceColor?: string
  /** 字段级 `值 → 语义色` 映射。 */
  colorMap?: Record<string, StatusTagSemantic>
  /** 形态（胶囊 / 点状 / 圆点 / 图标 / 浅色底）。 */
  shape?: StatusTagShape
  /** 尺寸。 */
  size?: 'default' | 'small'
  /** 图标字符（形态为 `icon` 时展示）。 */
  icon?: string
  /** 是否可点击（状态联动筛选入口）。 */
  clickable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  value: null,
  text: '',
  semantic: undefined,
  sourceColor: undefined,
  colorMap: undefined,
  shape: 'capsule',
  size: 'default',
  icon: '',
  clickable: false,
})

const emit = defineEmits<{ click: [value: string | number | boolean | null] }>()

const base = useBaseDisplay<string | number | boolean | null>()

watch(
  () => props.text,
  (next) => base.setValue(next === '' ? undefined : next),
  { immediate: true },
)

/** 状态解析结果（语义色 / 令牌 / 文案 / 已知性）。 */
const description = computed(() =>
  describeStatus(props.value, {
    semantic: props.semantic,
    sourceColor: props.sourceColor,
    colorMap: props.colorMap,
    text: props.text,
  }),
)

/** 语义色令牌样式（颜色一律引用设计令牌，不硬编码色值）。 */
const tagStyle = computed<Record<string, string>>(() => ({ '--bms-status-color': `var(${description.value.token})` }))

/** 悬浮提示（圆点形态必填文案来源）。 */
const titleText = computed(() => description.value.text)

/** 是否仅渲染圆点（无文案形态）。 */
const bulletOnly = computed(() => props.shape === 'bullet')

/** 是否渲染状态点（点状 / 圆点）。 */
const hasDot = computed(() => props.shape === 'dot' || props.shape === 'bullet')

/** 展示文案（值语义优先，缺省走状态解析文案）。 */
const displayText = computed(() => (base.value.value === undefined ? description.value.text : String(base.value.value)))

/**
 * 点击状态标签（可点击时上抛，供页面接入筛选）。
 */
function onClick(): void {
  if (props.clickable) {
    emit('click', props.value)
  }
}
</script>

<template>
  <span
    class="bms-status-tag"
    :class="[`bms-status-tag--${shape}`, size === 'small' ? 'is-small' : '', clickable ? 'is-clickable' : '']"
    data-test="status-tag"
    :data-semantic="description.semantic"
    :data-known="description.known"
    :style="tagStyle"
    :title="titleText"
    @click="onClick"
  >
    <span v-if="bulletOnly" class="bms-status-tag__dot" data-test="status-bullet" />
    <span v-else-if="hasDot" class="bms-status-tag__dot" data-test="status-dot" />
    <span v-if="shape === 'icon'" class="bms-status-tag__icon" data-test="status-icon">{{ icon }}</span>
    <template v-if="!bulletOnly">
      <slot>{{ displayText }}</slot>
    </template>
  </span>
</template>

<style scoped>
.bms-status-tag {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  color: var(--bms-status-color);
  font-size: var(--bms-font-size);
  line-height: var(--bms-line-height);
}

.bms-status-tag.is-small {
  font-size: 12px;
}

.bms-status-tag.is-clickable {
  cursor: pointer;
}

.bms-status-tag--capsule {
  padding: 0 var(--bms-spacing-md);
  border: 1px solid var(--bms-status-color);
  border-radius: var(--bms-radius-md);
}

.bms-status-tag--dot,
.bms-status-tag--bullet,
.bms-status-tag--icon {
  color: var(--bms-color-text);
}

.bms-status-tag--light {
  padding: 0 var(--bms-spacing-md);
  border-radius: var(--bms-radius-md);
  background: color-mix(in srgb, var(--bms-status-color) 12%, transparent);
}

.bms-status-tag__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--bms-status-color);
}

.bms-status-tag__icon {
  color: var(--bms-status-color);
}
</style>
