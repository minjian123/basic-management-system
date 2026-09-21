<script setup lang="ts">
// 组织复合选择弹窗（06_05）：左部门树 × 右人员 / 岗位列表 + 搜索 + 已选标签；确认回填受控值、取消恢复快照。
import { ElCheckbox, ElDialog, ElInput, ElTree } from 'element-plus'
import {
  ORG_EMPTY_TEXT,
  ORG_PLACEHOLDER_TEXT,
  ORG_SEARCH_DEBOUNCE,
  orgTagSummary,
  toOrgTreeNodes,
  type BaseUserDisplay,
  type OrgKind,
  type OrgSourceAdapter,
  type OrgTreeNode,
} from '@bms/core'
import { computed, onScopeDispose, ref, watch } from 'vue'

import { useBaseOrgSelect } from '../../composables/useBaseOrgSelect'
import { debounce } from '../../utils/debounce'
import EmptyState from '../feedback/EmptyState.vue'

/** 字段值类型。 */
export type OrgCompositeValue = string | string[] | undefined

interface Props {
  /** 显隐（受控）。 */
  visible?: boolean
  /** 值（受控；多选为数组）。 */
  modelValue?: OrgCompositeValue
  /** 对象类型（人员 / 岗位）。 */
  kind?: OrgKind
  /** 多选（缺省多选）。 */
  multiple?: boolean
  /** 多选上限（0 不限）。 */
  limit?: number
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 组织数据源（未注入即占位零请求）。 */
  source?: OrgSourceAdapter
  /** 用户展示能力（缺省由投影内建花名册）。 */
  userDisplay?: BaseUserDisplay
  /** 标题。 */
  title?: string
  /** 列表页长。 */
  pageSize?: number
  /** 部门过滤是否含下级。 */
  includeChildren?: boolean
  /** 占位提示（搜索框）。 */
  placeholder?: string
  /** 降级文案。 */
  degradeText?: string
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  visible: false,
  modelValue: undefined,
  kind: 'user',
  multiple: true,
  limit: 0,
  ready: false,
  source: undefined,
  userDisplay: undefined,
  title: '选择人员',
  pageSize: 20,
  includeChildren: false,
  placeholder: '搜索',
  degradeText: ORG_PLACEHOLDER_TEXT,
  emptyText: ORG_EMPTY_TEXT,
})

const emit = defineEmits<{
  'update:visible': [value: boolean]
  'update:modelValue': [value: OrgCompositeValue]
  change: [value: OrgCompositeValue]
  confirm: []
  cancel: []
  retry: []
  'limit-exceed': [limit: number]
}>()

const api = useBaseOrgSelect({
  ready: props.ready,
  kind: props.kind === 'post' ? 'post' : 'user',
  multiple: props.multiple,
  limit: props.limit,
  source: props.source,
  userDisplay: props.userDisplay,
  disabled: false,
})

/** 打开时快照（取消恢复用）。 */
let snapshot: string | string[] | undefined
const activeDept = ref('')
const page = ref(1)

watch(
  () => props.ready,
  (next) => api.setReady(next),
  { immediate: true },
)
watch(
  () => props.source,
  (next) => api.setSource(next),
)
watch(
  () => props.userDisplay,
  (next) => api.setUserDisplay(next),
)
watch(
  () => props.multiple,
  (next) => api.setMultiple(next),
)
watch(
  () => props.limit,
  (next) => api.setLimit(next),
)
watch(
  () => props.visible,
  (visible) => {
    if (visible) {
      snapshot = api.value.value
      api.setKeyword('')
      api.setDeptFilter('')
      api.setPage(1)
      page.value = 1
      activeDept.value = ''
      api.syncValue(props.modelValue)
      void api.loadDeptTree()
      void api.load()
    }
  },
  { immediate: true },
)
watch(
  () => api.limitExceeded.value,
  (exceeded) => {
    if (exceeded) {
      emit('limit-exceed', props.limit)
    }
  },
)

const loadDebounced = debounce(() => {
  api.setPage(1)
  page.value = 1
  void api.load()
}, ORG_SEARCH_DEBOUNCE)
onScopeDispose(() => loadDebounced.cancel())

const treeNodes = computed<OrgTreeNode[]>(() => toOrgTreeNodes(api.deptNodes.value))
const pageCount = computed(() => Math.max(1, Math.ceil(api.total.value / Math.max(1, props.pageSize))))
const tag = computed(() => orgTagSummary(api.selectedItems.value, 3))

/**
 * 搜索输入（300ms 防抖）。
 *
 * @param value 关键词。
 */
function onSearchInput(value: string): void {
  api.setKeyword(value)
  loadDebounced()
}

/** 上一页。 */
function onPrev(): void {
  if (page.value <= 1) {
    return
  }
  page.value -= 1
  api.setPage(page.value)
  void api.load()
}

/** 下一页。 */
function onNext(): void {
  if (page.value >= pageCount.value) {
    return
  }
  page.value += 1
  api.setPage(page.value)
  void api.load()
}

/**
 * 部门树节点点击（联动列表过滤）。
 *
 * @param node 树节点。
 */
function onDeptClick(node: OrgTreeNode): void {
  activeDept.value = node.key
  api.setDeptFilter(node.key, props.includeChildren)
  page.value = 1
  api.setPage(1)
  void api.load()
}

/**
 * 勾选 / 取消勾选候选。
 *
 * @param id 标识。
 */
function onToggle(id: string): void {
  api.toggle(id)
}

/** 关闭弹窗（不提交）。 */
function onCancel(): void {
  api.setValue(snapshot)
  emit('cancel')
  emit('update:visible', false)
}

/** 确认回填受控值。 */
function onConfirm(): void {
  const next = api.value.value
  const value = Array.isArray(next) ? (next.length === 0 ? undefined : next) : next
  emit('update:modelValue', value)
  emit('change', value)
  emit('confirm')
  emit('update:visible', false)
}

/** 重试加载（失效缓存后重取）。 */
function onRetry(): void {
  api.invalidate()
  void api.load()
  emit('retry')
}
</script>

<template>
  <el-dialog
    class="bms-org-composite-picker"
    data-test="org-composite-picker"
    :model-value="visible"
    :title="title"
    width="720px"
    @update:model-value="emit('update:visible', $event)"
  >
    <div v-if="api.degraded.value" data-test="composite-degrade">
      <slot name="degrade">
        <div class="bms-field-placeholder" data-test="placeholder">{{ degradeText }}</div>
      </slot>
    </div>

    <div v-else class="bms-org-composite-picker__body">
      <div class="bms-org-composite-picker__tree" data-test="composite-tree">
        <el-tree
          :data="treeNodes"
          node-key="key"
          :props="{ label: 'label', children: 'children', disabled: 'disabled' }"
          default-expand-all
          highlight-current
          @node-click="onDeptClick"
        />
      </div>
      <div class="bms-org-composite-picker__list">
        <el-input
          class="bms-org-composite-picker__search"
          data-test="composite-search"
          :model-value="api.keyword.value"
          :placeholder="placeholder"
          clearable
          @update:model-value="onSearchInput"
        />
        <div v-if="api.items.value.length > 0" class="bms-org-composite-picker__rows">
          <div
            v-for="item in api.items.value"
            :key="item.id"
            class="bms-org-composite-picker__row"
            :data-test="`composite-row-${item.id}`"
          >
            <el-checkbox
              :model-value="api.selectedIds.value.includes(item.id)"
              :disabled="item.deleted || item.status === 'disabled'"
              :data-test="`composite-check-${item.id}`"
              @update:model-value="onToggle(item.id)"
            />
            <span class="bms-org-composite-picker__name">{{ api.labelOf(item.id) }}</span>
            <span v-if="item.code" class="bms-org-composite-picker__code">{{ item.code }}</span>
          </div>
        </div>
        <slot v-else name="empty">
          <empty-state type="result" data-test="composite-empty" :description="emptyText" />
        </slot>
        <div class="bms-org-composite-picker__pager">
          <button type="button" data-test="composite-page-prev" :disabled="page <= 1" @click="onPrev">上一页</button>
          <span data-test="composite-page">{{ page }} / {{ pageCount }}</span>
          <button type="button" data-test="composite-page-next" :disabled="page >= pageCount" @click="onNext">下一页</button>
        </div>
      </div>
    </div>

    <div class="bms-org-composite-picker__tags" data-test="composite-tags">
      <span v-for="item in tag.visible" :key="item.id" class="bms-org-composite-picker__tag" :data-test="`composite-tag-${item.id}`">
        {{ api.labelOf(item.id) }}
        <button type="button" :aria-label="`移除 ${api.labelOf(item.id)}`" @click="onToggle(item.id)">×</button>
      </span>
      <span v-if="tag.overflow > 0" data-test="composite-tag-overflow">+{{ tag.overflow }}</span>
    </div>

    <p v-if="api.errorText.value !== ''" class="bms-field-error" data-test="composite-error">{{ api.errorText.value }}</p>
    <button v-if="api.error.value" type="button" data-test="composite-retry" @click="onRetry">重试</button>

    <template #footer>
      <slot name="footer">
        <button type="button" data-test="composite-cancel" @click="onCancel">取消</button>
        <button type="button" data-test="composite-confirm" @click="onConfirm">确定</button>
      </slot>
    </template>
  </el-dialog>
</template>

<style scoped>
.bms-org-composite-picker__body {
  display: flex;
  gap: var(--bms-spacing-lg);
  min-height: 320px;
}
.bms-org-composite-picker__tree {
  width: 240px;
  padding: var(--bms-spacing-sm);
  overflow: auto;
  border: 1px solid var(--bms-org-border);
  border-radius: var(--bms-radius-md);
  background: var(--bms-org-panel-bg);
}
.bms-org-composite-picker__list {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--bms-spacing-sm);
}
.bms-org-composite-picker__rows {
  flex: 1;
  overflow: auto;
}
.bms-org-composite-picker__row {
  display: flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  padding: var(--bms-spacing-sm);
  border-radius: var(--bms-radius-sm);
}
.bms-org-composite-picker__row:hover {
  background: var(--bms-org-option-hover-bg);
}
.bms-org-composite-picker__code {
  color: var(--bms-color-text-secondary);
  font-size: 12px;
}
.bms-org-composite-picker__pager {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--bms-spacing-md);
}
.bms-org-composite-picker__tags {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-spacing-sm);
  margin-top: var(--bms-spacing-md);
}
.bms-org-composite-picker__tag {
  display: inline-flex;
  align-items: center;
  gap: var(--bms-spacing-sm);
  padding: 0 var(--bms-spacing-sm);
  background: var(--bms-org-tag-bg);
  border: 1px solid var(--bms-org-border);
  border-radius: var(--bms-radius-sm);
}
.bms-org-composite-picker__tag button {
  color: var(--bms-color-text-secondary);
  background: transparent;
  border: none;
  cursor: pointer;
}
</style>
