<script setup lang="ts">
// AI 会话列表（08_10）：历史会话按更新时间降序，支持新建 / 切换 / 删除 / 模式筛选 / 关键字搜索。
import { modeLabel, sortSessions, type AiMode, type AiSession } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'

interface Props {
  /** 会话列表。 */
  sessions?: AiSession[]
  /** 当前会话标识。 */
  activeSessionId?: string
  /** 模式筛选。 */
  mode?: AiMode | 'all'
  /** 搜索关键字。 */
  keyword?: string
  /** 展示搜索（缺省 true）。 */
  showSearch?: boolean
  /** 展示删除（缺省 true）。 */
  showRemove?: boolean
  /** 禁用（占位态）。 */
  disabled?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  sessions: () => [],
  activeSessionId: '',
  mode: 'all',
  keyword: '',
  showSearch: true,
  showRemove: true,
  disabled: false,
})

const emit = defineEmits<{
  select: [sessionId: string]
  create: []
  remove: [sessionId: string]
  'update:mode': [mode: AiMode | 'all']
  'update:keyword': [keyword: string]
}>()

const { state, setState } = useBaseDataState()

/** 归一排序后的会话。 */
const ordered = computed(() => sortSessions(props.sessions))

/** 模式筛选后的会话。 */
const filtered = computed(() => {
  const keyword = props.keyword.trim()
  return ordered.value.filter((session) => {
    if (props.mode !== 'all' && session.mode !== props.mode) {
      return false
    }
    return keyword === '' || session.title.includes(keyword)
  })
})

watch(
  () => filtered.value.length,
  (count) => setState(count > 0 ? 'ready' : 'empty'),
  { immediate: true },
)
</script>

<template>
  <div class="bms-ai-sessions" data-test="session-list" :data-state="state" :data-disabled="disabled || undefined">
    <div class="bms-ai-sessions__head">
      <button type="button" data-test="new-session" :disabled="disabled" @click="emit('create')">新建会话</button>
    </div>
    <div v-if="showSearch" class="bms-ai-sessions__filter">
      <select
        data-test="session-filter"
        :disabled="disabled"
        :value="mode"
        @change="emit('update:mode', ($event.target as HTMLSelectElement).value as AiMode | 'all')"
      >
        <option value="all">全部模式</option>
        <option value="ask">通用对话</option>
        <option value="report">智能问数</option>
        <option value="approval">审批辅助</option>
        <option value="doc_qa">文档问答</option>
      </select>
      <input
        data-test="session-search"
        type="search"
        placeholder="搜索会话"
        :disabled="disabled"
        :value="keyword"
        @input="emit('update:keyword', ($event.target as HTMLInputElement).value)"
      />
    </div>
    <ul v-if="filtered.length > 0" class="bms-ai-sessions__list">
      <li
        v-for="session in filtered"
        :key="session.id"
        class="bms-ai-sessions__item"
        :data-test="`session-${session.id}`"
        :data-active="session.id === activeSessionId || undefined"
        @click="disabled || emit('select', session.id)"
      >
        <slot name="item" :session="session">
          <span class="bms-ai-sessions__mode">{{ modeLabel(session.mode) }}</span>
          <span class="bms-ai-sessions__title">{{ session.title }}</span>
        </slot>
        <button
          v-if="showRemove"
          type="button"
          class="bms-ai-sessions__remove"
          :data-test="`remove-session-${session.id}`"
          :disabled="disabled"
          @click.stop="emit('remove', session.id)"
        >
          删除
        </button>
      </li>
    </ul>
    <div v-else class="bms-ai-sessions__empty" data-test="session-empty">
      <slot name="empty">暂无会话</slot>
    </div>
  </div>
</template>

<style scoped>
.bms-ai-sessions {
  display: flex;
  flex-direction: column;
  width: 220px;
  border-right: 1px solid var(--bms-color-border, #ebeef5);
}
.bms-ai-sessions__head {
  padding: 8px 12px;
}
.bms-ai-sessions__head button {
  width: 100%;
  padding: 6px;
  color: #fff;
  cursor: pointer;
  background: var(--bms-color-primary, #409eff);
  border: none;
  border-radius: 4px;
}
.bms-ai-sessions__filter {
  display: flex;
  gap: 6px;
  padding: 0 12px 8px;
}
.bms-ai-sessions__filter select,
.bms-ai-sessions__filter input {
  min-width: 0;
  flex: 1 1 auto;
}
.bms-ai-sessions__list {
  flex: 1 1 auto;
  padding: 0;
  margin: 0;
  overflow: auto;
  list-style: none;
}
.bms-ai-sessions__item {
  display: flex;
  gap: 6px;
  align-items: center;
  padding: 8px 12px;
  cursor: pointer;
  border-bottom: 1px solid var(--bms-color-border, #ebeef5);
}
.bms-ai-sessions__item[data-active] {
  background: var(--bms-ai-citation-bg, #ecf5ff);
}
.bms-ai-sessions__mode {
  flex: 0 0 auto;
  padding: 0 6px;
  font-size: 12px;
  color: var(--bms-color-text-secondary, #909399);
  background: var(--bms-ai-bubble-assistant-bg, #f5f7fa);
  border-radius: 9px;
}
.bms-ai-sessions__title {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.bms-ai-sessions__remove {
  flex: 0 0 auto;
  font-size: 12px;
  color: var(--bms-color-danger, #f56c6c);
  cursor: pointer;
  background: none;
  border: none;
}
.bms-ai-sessions__empty {
  padding: 24px;
  color: var(--bms-color-text-secondary, #909399);
  text-align: center;
}
</style>
