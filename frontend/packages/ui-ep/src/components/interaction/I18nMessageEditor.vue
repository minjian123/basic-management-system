<script setup lang="ts">
// 国际化文案编辑器（占位版，08_01_02）：契约先行冻结；数据通路未就绪时不请求、编辑禁用 + 降级提示。文案网格独立分包懒加载。
import { defineAsyncComponent, watch } from 'vue'

import { useBaseLocale } from '../../composables/useBaseLocale'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

// 文案网格独立分包（真实实现 08_07 承载虚拟滚动与批量保存）。
const MessageGrid = defineAsyncComponent(() => import('./MessageGrid.vue'))

/** 语言项。 */
export interface I18nLocale {
  /** 语言标识（如 `zh-CN`）。 */
  code: string
  /** 语言名。 */
  name: string
  /** 是否从右到左。 */
  rtl?: boolean
  /** 状态。 */
  status: 'enabled' | 'disabled'
}

/** 文案行。 */
export interface I18nMessageRow {
  /** 文案键。 */
  key: string
  /** 各语言值。 */
  values: Record<string, string>
  /** 缺失翻译的语言标识。 */
  missing?: string[]
}

/** 变更载荷。 */
export interface I18nChangePayload {
  /** 变更类型。 */
  kind: 'message' | 'key' | 'locale'
  /** 变更值。 */
  value: unknown
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 语言清单。 */
  locales?: I18nLocale[]
  /** 文案行。 */
  messages?: I18nMessageRow[]
  /** 聚焦语言（仅显示该语言列）。 */
  activeLocale?: string
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 加载中。 */
  loading?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  locales: () => [],
  messages: () => [],
  activeLocale: '',
  dirty: false,
  loading: false,
  degradeText: '国际化文案未就绪（占位）',
})

const emit = defineEmits<{
  change: [payload: I18nChangePayload]
  save: []
  'invalidate-cache': []
  'add-key': []
  'remove-key': [key: string]
  'add-locale': []
  'toggle-locale': [payload: { code: string; enabled: boolean }]
  export: []
  import: []
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { locale, setLocale } = useBaseLocale()

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

watch(
  () => props.activeLocale,
  (next) => {
    if (next) {
      setLocale(next)
    }
  },
  { immediate: true },
)

/** 语言启停切换。 */
function toggleLocale(item: I18nLocale): void {
  emit('toggle-locale', { code: item.code, enabled: item.status !== 'enabled' })
}
</script>

<template>
  <div
    class="bms-i18n-message-editor"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-i18n-message-editor__toolbar" data-test="toolbar">
          <span data-test="locale">{{ locale }}</span>
          <button type="button" data-test="add-key" :disabled="placeholder.disabled.value" @click="emit('add-key')">
            新增 key
          </button>
          <button
            type="button"
            data-test="add-locale"
            :disabled="placeholder.disabled.value"
            @click="emit('add-locale')"
          >
            新增语言
          </button>
          <button type="button" data-test="save" :disabled="placeholder.disabled.value" @click="emit('save')">
            保存
          </button>
          <button
            type="button"
            data-test="invalidate-cache"
            :disabled="placeholder.disabled.value"
            @click="emit('invalidate-cache')"
          >
            缓存失效
          </button>
          <button type="button" data-test="export" :disabled="placeholder.disabled.value" @click="emit('export')">
            导出
          </button>
          <button type="button" data-test="import" :disabled="placeholder.disabled.value" @click="emit('import')">
            导入
          </button>
          <span v-if="dirty" data-test="dirty">未保存</span>
        </div>

        <div class="bms-i18n-message-editor__locales" data-test="locales">
          <span
            v-for="item in locales"
            :key="item.code"
            :data-test="`locale-${item.code}`"
            :data-status="item.status"
          >
            {{ item.name }}
            <button type="button" :data-test="`toggle-${item.code}`" @click="toggleLocale(item)">启停</button>
          </span>
        </div>

        <div class="bms-i18n-message-editor__grid" data-test="grid">
          <slot name="grid">
            <component
              :is="MessageGrid"
              :locales="locales"
              :messages="messages"
              :active-locale="activeLocale"
              @cell-change="emit('change', { kind: 'message', value: $event })"
              @remove-key="emit('remove-key', $event)"
            />
          </slot>
        </div>
      </slot>
    </template>
  </div>
</template>
