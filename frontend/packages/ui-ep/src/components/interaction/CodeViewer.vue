<script setup lang="ts">
// 只读高亮件（08_02）：highlight.js 模块级缓存（与编辑内核分工），长文折叠 + 最大高度滚动 + 复制。
import { computed, ref, watch } from 'vue'

import { escapeHtml, useHighlight } from '../../composables/useHighlight'

/** 只读高亮语言。 */
export type ViewerLanguage = 'sql' | 'json' | 'javascript' | 'text' | 'log'

interface Props {
  /** 代码 / JSON 文本。 */
  content?: string
  /** 语言。 */
  language?: ViewerLanguage
  /** 是否显示行号。 */
  lineNumbers?: boolean
  /** 最大高度。 */
  maxHeight?: string
  /** 是否自动换行。 */
  wrap?: boolean
  /** 是否长文折叠。 */
  collapsible?: boolean
  /** 折叠行数阈值。 */
  collapseLines?: number
  /** 是否可复制。 */
  copyable?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  content: '',
  language: 'text',
  lineNumbers: true,
  maxHeight: '320px',
  wrap: false,
  collapsible: true,
  collapseLines: 15,
  copyable: true,
})

const emit = defineEmits<{
  copy: []
}>()

const highlight = useHighlight()
const html = ref(escapeHtml(props.content))
const expanded = ref(false)

watch(
  () => [props.content, props.language] as const,
  async ([content, language]) => {
    if (content === '') {
      html.value = ''
      return
    }
    html.value = await highlight.highlight(content, language)
  },
  { immediate: true },
)

/** 行清单。 */
const lines = computed(() => props.content.split('\n'))

/** 是否处于折叠态。 */
const collapsed = computed(
  () => props.collapsible && !expanded.value && lines.value.length > props.collapseLines,
)

/** 生效最大高度。 */
const effectiveMaxHeight = computed(() =>
  collapsed.value ? `${props.collapseLines * 1.5}em` : props.maxHeight,
)

/** 复制内容。 */
function copy(): void {
  void globalThis.navigator?.clipboard?.writeText(props.content)
  emit('copy')
}
</script>

<template>
  <div
    class="bms-code-viewer"
    data-test="code-viewer"
    :data-language="language"
    :data-collapsed="collapsed || undefined"
    :data-lines="lines.length"
  >
    <div class="bms-code-viewer__header" data-test="header">
      <span data-test="language">{{ language }}</span>
      <button v-if="copyable" type="button" data-test="copy" @click="copy">复制</button>
      <button
        v-if="collapsible && lines.length > collapseLines"
        type="button"
        data-test="toggle-collapse"
        @click="expanded = !expanded"
      >
        {{ expanded ? '收起' : '展开' }}
      </button>
    </div>
    <div class="bms-code-viewer__body" :style="{ maxHeight: effectiveMaxHeight }">
      <pre v-if="lineNumbers" class="bms-code-viewer__gutter" data-test="gutter" aria-hidden="true"><span v-for="line in lines.length" :key="line">{{ line }}
</span></pre>
      <!-- eslint-disable vue/no-v-html -- highlight.js 输出为转义后的高亮 HTML -->
      <pre
        class="bms-code-viewer__code"
        data-test="code"
        :data-wrap="wrap || undefined"
        v-html="html"
      />
      <!-- eslint-enable vue/no-v-html -->
    </div>
  </div>
</template>
