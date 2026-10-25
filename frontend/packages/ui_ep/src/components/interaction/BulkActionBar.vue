<script setup lang="ts">
// 批量操作栏：选中后浮出 / 吸顶；显示选中数与跨页全选入口、常用动作 + 更多下拉、危险与超量确认、进度与结果反馈、完成后清空。
import { computed, ref, watch } from 'vue'

import type { BulkActionDef, BulkActionResult, SelectionKey, SelectionMode } from '@bms/core'
import { useBaseBulkAction } from '../../composables/useBaseBulkAction'

interface Props {
  /** 选中集合（`v-model:selected`）。 */
  selected?: SelectionKey[]
  /** 动作集合。 */
  actions?: BulkActionDef[]
  /** 当前查询总记录数。 */
  total?: number
  /** 选择模式（缺省允许跨页全选）。 */
  mode?: SelectionMode
  /** 当前页行键。 */
  pageKeys?: SelectionKey[]
  /** 超量确认阈值（0 表示不限制）。 */
  confirmThreshold?: number
  /** 完成后是否清空选择。 */
  clearAfterDone?: boolean
  /** 常用动作直显数。 */
  maxVisible?: number
  /** 呈现位置。 */
  position?: 'float' | 'sticky'
  /** 函数式权限判定（未提供时不过滤）。 */
  permChecker?: (perm: string) => boolean
  /** 外部加载态（禁用动作）。 */
  loading?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selected: () => [],
  actions: () => [],
  total: 0,
  mode: 'cross-page',
  pageKeys: () => [],
  confirmThreshold: 0,
  clearAfterDone: true,
  maxVisible: 3,
  position: 'float',
  permChecker: undefined,
  loading: false,
})

const emit = defineEmits<{
  'update:selected': [value: SelectionKey[]]
  action: [payload: { key: string; keys: SelectionKey[]; allAcrossPages: boolean }]
  done: [result: BulkActionResult]
  clear: []
  progress: [payload: { current: number; total: number }]
  'select-all-across': []
}>()

const {
  bulk,
  selected,
  count,
  summary,
  visibleActions,
  phase,
  running,
  pendingActionKey,
  progress,
  setActions,
  setTotal,
  setPageKeys,
  selectAllAcrossPages,
  clear,
  replace,
  request,
  confirm,
  cancel,
} = useBaseBulkAction({
  actions: props.actions,
  mode: props.mode,
  total: props.total,
  pageKeys: props.pageKeys,
  selected: props.selected,
  confirmThreshold: props.confirmThreshold,
  clearAfterDone: props.clearAfterDone,
  maxVisible: props.maxVisible,
  permChecker: props.permChecker,
})

/** 「更多」下拉展开态。 */
const moreOpen = ref(false)

watch(
  () => props.actions,
  (value) => setActions(value),
)
watch(
  () => props.total,
  (value) => setTotal(value),
)
watch(
  () => props.pageKeys,
  (value) => setPageKeys(value),
)
watch(
  () => props.selected,
  (value) => replace(value),
)
watch(
  () => props.confirmThreshold,
  (value) => {
    bulk.confirmThreshold = value
  },
)
watch(
  () => selected.value,
  (value) => emit('update:selected', [...value]),
  { deep: true },
)
watch(
  () => progress.value,
  (value) => emit('progress', { ...value }),
  { deep: true },
)

/** 是否处于确认阶段。 */
const confirming = computed(() => phase.value === 'confirming')
/** 直显动作。 */
const primaryActions = computed(() => visibleActions.value.slice(0, props.maxVisible))
/** 收进「更多」的动作。 */
const hiddenActions = computed(() => visibleActions.value.slice(props.maxVisible))
/** 是否展示跨页全选入口。 */
const canSelectAllAcross = computed(
  () => props.mode === 'cross-page' && !summary.value.allAcrossPages && summary.value.total > count.value,
)
/** 待确认动作。 */
const confirmAction_ = computed(() =>
  pendingActionKey.value === undefined ? undefined : bulk.actionOf(pendingActionKey.value),
)
/** 确认文案。 */
const confirmText = computed(() => {
  const action = confirmAction_.value
  if (action === undefined) {
    return ''
  }
  if (action.confirmText !== undefined && action.confirmText !== '') {
    return action.confirmText
  }
  const scope = summary.value.allAcrossPages ? `当前条件下共 ${summary.value.total} 项` : `${count.value} 项`
  return `确认对 ${scope} 执行「${action.label}」？`
})
/** 动作是否禁用。 */
const actionsDisabled = computed(() => running.value || props.loading)

/**
 * 触发动作（需确认时进入确认区，执行完成后上抛结果）。
 *
 * @param key 动作键。
 */
const runAction = async (key: string): Promise<void> => {
  moreOpen.value = false
  const action = bulk.actionOf(key)
  if (action !== undefined) {
    emit('action', {
      key,
      keys: summary.value.allAcrossPages ? [] : [...selected.value],
      allAcrossPages: summary.value.allAcrossPages,
    })
  }
  const result = await request(key)
  if (result !== undefined) {
    emit('done', result)
  }
}

/** 确认并执行待确认动作。 */
const confirmPending = async (): Promise<void> => {
  const result = await confirm()
  if (result !== undefined) {
    emit('done', result)
  }
}

/** 取消确认。 */
const cancelPending = (): void => {
  cancel()
}

/** 清空选择。 */
const clearSelection = (): void => {
  clear()
  emit('clear')
}

/** 跨页全选。 */
const selectAllAcross = (): void => {
  selectAllAcrossPages()
  emit('select-all-across')
}

defineExpose({
  clear: clearSelection,
  run: runAction,
  selectAllAcrossPages: selectAllAcross,
  count,
})
</script>

<template>
  <div
    v-if="count > 0"
    class="bms-bulk-bar"
    :data-position="position"
    :data-phase="phase"
    data-test="bulk-action-bar"
  >
    <div class="bms-bulk-bar__summary" data-test="bulk-action-bar-summary">
      <slot name="summary" :count="count" :all-across-pages="summary.allAcrossPages" :total="summary.total">
        <span class="bms-bulk-bar__count">已选 {{ count }} 项</span>
        <button
          v-if="canSelectAllAcross"
          type="button"
          class="bms-bulk-bar__link"
          data-test="bulk-action-bar-select-all-across"
          @click="selectAllAcross"
        >
          全选本条件下共 {{ summary.total }} 项
        </button>
        <span v-else-if="summary.allAcrossPages" class="bms-bulk-bar__hint">
          已按当前条件全选（共 {{ summary.total }} 项）
        </span>
      </slot>
    </div>

    <div class="bms-bulk-bar__actions" data-test="bulk-action-bar-actions">
      <slot name="actions" :actions="visibleActions" :run="runAction">
        <button
          v-for="action in primaryActions"
          :key="action.key"
          type="button"
          class="bms-bulk-bar__action"
          :data-danger="action.danger ? 'true' : 'false'"
          :data-test="`bulk-action-${action.key}`"
          :disabled="actionsDisabled"
          @click="runAction(action.key)"
        >
          {{ action.label }}
        </button>
        <span v-if="hiddenActions.length > 0" class="bms-bulk-bar__more">
          <button
            type="button"
            class="bms-bulk-bar__action"
            data-test="bulk-action-bar-more"
            :disabled="actionsDisabled"
            @click="moreOpen = !moreOpen"
          >
            更多
          </button>
          <span v-if="moreOpen" class="bms-bulk-bar__menu" data-test="bulk-action-bar-menu">
            <button
              v-for="action in hiddenActions"
              :key="action.key"
              type="button"
              class="bms-bulk-bar__menu-item"
              :data-danger="action.danger ? 'true' : 'false'"
              :data-test="`bulk-action-${action.key}`"
              :disabled="actionsDisabled"
              @click="runAction(action.key)"
            >
              {{ action.label }}
            </button>
          </span>
        </span>
      </slot>
      <button
        type="button"
        class="bms-bulk-bar__link"
        data-test="bulk-action-bar-clear"
        :disabled="running"
        @click="clearSelection"
      >
        清除
      </button>
    </div>

    <div v-if="running && progress.total > 0" class="bms-bulk-bar__progress" data-test="bulk-action-bar-progress">
      进度 {{ progress.current }} / {{ progress.total }}
    </div>

    <div v-if="confirming" class="bms-bulk-bar__confirm" data-test="bulk-action-bar-confirm">
      <span class="bms-bulk-bar__confirm-text">{{ confirmText }}</span>
      <button
        type="button"
        class="bms-bulk-bar__action"
        data-test="bulk-action-bar-confirm-ok"
        @click="confirmPending"
      >
        确认
      </button>
      <button type="button" class="bms-bulk-bar__link" data-test="bulk-action-bar-confirm-cancel" @click="cancelPending">
        取消
      </button>
    </div>

    <slot name="extra" />
  </div>
</template>

<style scoped>
.bms-bulk-bar {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-md, 8px);
  padding: var(--bms-spacing-sm, 6px) var(--bms-spacing-md, 8px);
  border: 1px solid var(--bms-color-primary-border);
  border-radius: var(--bms-radius-md, 6px);
  background: var(--bms-color-primary-light);
  color: var(--bms-color-text);
}

.bms-bulk-bar[data-position='sticky'] {
  position: sticky;
  top: 0;
  z-index: 10;
}

.bms-bulk-bar__summary {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  font-size: 13px;
}

.bms-bulk-bar__count {
  font-weight: 600;
}

.bms-bulk-bar__hint {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}

.bms-bulk-bar__actions {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  margin-left: auto;
}

.bms-bulk-bar__action {
  padding: 4px 10px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 4px);
  background: var(--bms-color-bg);
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.bms-bulk-bar__action[data-danger='true'] {
  border-color: var(--bms-color-danger);
  color: var(--bms-color-danger);
}

.bms-bulk-bar__action:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.bms-bulk-bar__link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--bms-color-primary);
  font: inherit;
  cursor: pointer;
}

.bms-bulk-bar__more {
  position: relative;
  display: inline-flex;
}

.bms-bulk-bar__menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  display: flex;
  flex-direction: column;
  min-width: 120px;
  padding: 4px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-sm, 4px);
  background: var(--bms-color-bg);
  box-shadow: var(--bms-shadow-sm);
  z-index: 20;
}

.bms-bulk-bar__menu-item {
  padding: 4px 8px;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
}

.bms-bulk-bar__menu-item[data-danger='true'] {
  color: var(--bms-color-danger);
}

.bms-bulk-bar__progress {
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}

.bms-bulk-bar__confirm {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm, 6px);
  margin-left: auto;
  font-size: 13px;
}
</style>
