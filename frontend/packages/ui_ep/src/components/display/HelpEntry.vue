<script setup lang="ts">
// 帮助入口（09_02）：一套解析与五态（加载 / 命中 / 有锚点无文章 / 无锚点 / 失败），工具栏与顶栏共用。
// 页内按锚点显隐（无锚点不显示）；顶栏常驻。正文经 `sanitizeHtml` 清洗后渲染，长文走 640px 长文对话框。
import { ElButton, ElTag } from 'element-plus'
import { computed, ref, watch } from 'vue'

import {
  HELP_EMPTY_TEXT,
  HELP_NO_ARTICLE_TEXT,
  helpLevelLabel,
  helpSourceLabel,
  type HelpContextFetcher,
  type HelpDescriptor,
} from '@bms/core'

import { useBaseHelpContext } from '../../composables/useBaseHelpContext'
import { sanitizeHtml } from '../../utils/sanitizeHtml'
import LongTextDialog from '../modal/LongTextDialog.vue'

interface Props {
  /** 形态（页内文字按钮 / 顶栏图标按钮常驻）。 */
  mode?: 'toolbar' | 'header'
  /** 帮助描述符（上下文 + 元数据锚点可用性；未提供时页内不显示）。 */
  descriptor?: HelpDescriptor
  /** 取数器（未注入时打开即报 `19001`，入口不请求）。 */
  fetcher?: HelpContextFetcher
  /** 按钮文案（缺省「帮助」）。 */
  label?: string
  /** 按钮尺寸。 */
  size?: 'small' | 'default' | 'large'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'toolbar',
  descriptor: undefined,
  fetcher: undefined,
  label: '帮助',
  size: 'default',
})

const emit = defineEmits<{
  open: []
  close: []
  category: [categoryId: string]
  retry: []
  error: [message: string]
}>()

const help = useBaseHelpContext({ ready: false })

/** 本地错误（取数器未注入等能力层抛出的错误）。 */
const localError = ref('')
/** 是否已因「无锚点」关闭（关闭后不再显示）。 */
const dismissed = ref(false)
/** 弹层显隐。 */
const dialogOpen = ref(false)

watch(
  () => props.fetcher,
  (fetcher) => {
    help.setFetcher(fetcher)
    help.setReady(props.descriptor?.ready ?? fetcher !== undefined)
  },
  { immediate: true },
)

watch(
  () => props.descriptor?.ready,
  (ready) => {
    help.setReady(ready ?? props.fetcher !== undefined)
  },
)

watch(
  () => props.descriptor?.context,
  (context) => {
    help.setContext(context ?? {})
    dismissed.value = false
  },
  { deep: true, immediate: true },
)

/** 入口是否可见（顶栏常驻；页内按元数据锚点或解析结果）。 */
const visible = computed(() => {
  if (props.mode === 'header') {
    return true
  }
  if (dismissed.value) {
    return false
  }
  return props.descriptor?.anchorAvailable === true || help.anchorFound.value
})

/** 错误文案（本地错误优先）。 */
const errorText = computed(() => localError.value || help.errorMessage.value)

/** 弹层标题。 */
const dialogTitle = computed(() => (help.matched.value ? (help.article.value?.title ?? '帮助') : '帮助'))

/** 层级标签。 */
const levelLabel = computed(() => helpLevelLabel(help.result.value?.level))

/** 来源标签（按文章）。 */
const sourceLabel = computed(() => helpSourceLabel(help.article.value?.source))

/** 清洗后的正文。 */
const safeContent = computed(() => sanitizeHtml(help.article.value?.content ?? ''))

/** 相关内容。 */
const related = computed(() => help.result.value?.related ?? [])

/** 分类列表。 */
const categories = computed(() => help.result.value?.categories ?? [])

/** 是否解析中。 */
const loading = computed(() => help.state.value === 'loading' && dialogOpen.value)

/** 打开帮助（打开时解析一次；同上下文复用结果）。 */
async function onOpen(): Promise<void> {
  dialogOpen.value = true
  localError.value = ''
  emit('open')
  try {
    await help.resolve()
    if (help.errorMessage.value !== '') {
      emit('error', help.errorMessage.value)
    }
  } catch (cause) {
    localError.value = cause instanceof Error && cause.message !== '' ? cause.message : '帮助内容加载失败'
    emit('error', localError.value)
  }
}

/** 重试（强制重取）。 */
async function onRetry(): Promise<void> {
  localError.value = ''
  emit('retry')
  try {
    await help.retry()
    if (help.errorMessage.value !== '') {
      emit('error', help.errorMessage.value)
    }
  } catch (cause) {
    localError.value = cause instanceof Error && cause.message !== '' ? cause.message : '帮助内容加载失败'
    emit('error', localError.value)
  }
}

/** 关闭弹层（无锚点时关闭后不再显示）。 */
function onClose(): void {
  dialogOpen.value = false
  if (!help.anchorFound.value) {
    dismissed.value = true
  }
  emit('close')
}

/**
 * 分类跳转（帮助中心占位；内容维护归 12_01）。
 *
 * @param categoryId 分类主键（空串表示打开帮助中心）。
 */
function onCategory(categoryId: string): void {
  emit('category', categoryId)
}
</script>

<template>
  <span v-if="visible" class="bms-help-entry">
    <el-button
      v-if="mode === 'header'"
      circle
      text
      :size="size"
      title="帮助"
      aria-label="帮助"
      data-test="header-help"
      @click="onOpen"
    >
      ?
    </el-button>
    <el-button v-else :size="size" data-test="help-entry" @click="onOpen">{{ label }}</el-button>

    <long-text-dialog v-model="dialogOpen" :title="dialogTitle" @close="onClose">
      <div v-if="loading" class="bms-help-entry__state" data-test="help-loading">加载中…</div>

      <div v-else-if="errorText !== ''" class="bms-help-entry__state" data-test="help-error">
        <p>{{ errorText }}</p>
        <el-button size="small" data-test="help-retry" @click="onRetry">重试</el-button>
      </div>

      <template v-else-if="help.matched.value">
        <div class="bms-help-entry__tags">
          <el-tag v-if="levelLabel !== ''" size="small" type="info" data-test="help-level">{{ levelLabel }}</el-tag>
          <el-tag v-if="sourceLabel !== ''" size="small" data-test="help-source">{{ sourceLabel }}</el-tag>
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <div class="bms-help-entry__content" data-test="help-article-content" v-html="safeContent" />
        <div v-if="related.length > 0" class="bms-help-entry__related" data-test="help-related">
          <p class="bms-help-entry__section">相关内容</p>
          <ul>
            <li v-for="item in related" :key="item.id">{{ item.title }}</li>
          </ul>
        </div>
        <div v-if="categories.length > 0" class="bms-help-entry__categories" data-test="help-categories">
          <p class="bms-help-entry__section">帮助分类</p>
          <el-button v-for="item in categories" :key="item.id" size="small" text @click="onCategory(item.id)">
            {{ item.name }}
          </el-button>
        </div>
      </template>

      <div v-else-if="help.anchorFound.value" class="bms-help-entry__state" data-test="help-no-article">
        <p>{{ HELP_NO_ARTICLE_TEXT }}</p>
        <div v-if="categories.length > 0" class="bms-help-entry__categories">
          <el-button v-for="item in categories" :key="item.id" size="small" text @click="onCategory(item.id)">
            {{ item.name }}
          </el-button>
        </div>
      </div>

      <div v-else class="bms-help-entry__state" data-test="help-empty">
        <p>{{ HELP_EMPTY_TEXT }}</p>
        <el-button size="small" data-test="help-open-center" @click="onCategory('')">打开帮助中心</el-button>
      </div>
    </long-text-dialog>
  </span>
</template>

<style scoped>
.bms-help-entry {
  display: inline-flex;
  align-items: center;
}

.bms-help-entry__state {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--bms-space-3);
  color: var(--bms-color-text-secondary);
}

.bms-help-entry__tags {
  display: flex;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-3);
}

.bms-help-entry__content {
  color: var(--bms-color-text);
}

.bms-help-entry__section {
  margin: var(--bms-space-4) 0 var(--bms-space-2);
  font-weight: var(--bms-font-weight-medium, 500);
}

.bms-help-entry__related ul {
  margin: 0;
  padding-left: var(--bms-space-4);
}

.bms-help-entry__categories {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
}
</style>
