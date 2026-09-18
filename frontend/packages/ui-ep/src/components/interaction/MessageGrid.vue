<script setup lang="ts">
// 国际化文案网格（占位，08_01_02）：由 I18nMessageEditor 异步懒加载的独立分包入口，真实实现（08_07）承载虚拟滚动与批量保存。
import { watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import type { I18nLocale, I18nMessageRow } from './I18nMessageEditor.vue'

interface Props {
  /** 语言清单。 */
  locales?: I18nLocale[]
  /** 文案行。 */
  messages?: I18nMessageRow[]
  /** 聚焦语言（仅显示该语言列）。 */
  activeLocale?: string
}

const props = withDefaults(defineProps<Props>(), {
  locales: () => [],
  messages: () => [],
  activeLocale: '',
})

const emit = defineEmits<{
  'cell-change': [payload: { key: string; locale: string; value: string }]
  'remove-key': [key: string]
}>()

const { state, setState } = useBaseDataState()
watch(
  () => props.messages.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)

function columns(): I18nLocale[] {
  const enabled = props.locales.filter((item) => item.status === 'enabled')
  return props.activeLocale ? enabled.filter((item) => item.code === props.activeLocale) : enabled
}
</script>

<template>
  <div class="bms-message-grid" data-test="message-grid" data-subpackage="i18n" :data-state="state">
    <p v-if="messages.length === 0" data-test="grid-empty">暂无文案数据（占位，真实实现接语言包维护接口）</p>
    <table v-else class="bms-message-grid__table">
      <thead>
        <tr>
          <th>msg_key</th>
          <th v-for="locale in columns()" :key="locale.code" :data-test="`column-${locale.code}`">{{ locale.code }}</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in messages" :key="row.key" :data-test="`message-${row.key}`">
          <td data-test="message-key">
            {{ row.key }}
            <button type="button" :data-test="`remove-${row.key}`" @click="emit('remove-key', row.key)">删除</button>
          </td>
          <td v-for="locale in columns()" :key="locale.code" :data-missing="row.missing?.includes(locale.code) || undefined">
            <input
              type="text"
              :value="row.values[locale.code] ?? ''"
              :data-test="`cell-${row.key}-${locale.code}`"
              @change="
                emit('cell-change', {
                  key: row.key,
                  locale: locale.code,
                  value: ($event.target as HTMLInputElement).value,
                })
              "
            />
          </td>
        </tr>
      </tbody>
    </table>
  </div>
</template>
