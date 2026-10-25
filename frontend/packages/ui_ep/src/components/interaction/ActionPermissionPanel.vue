<script setup lang="ts">
// 操作权限面板（08-4-4，新口径）：某表单的动作码清单——默认无、勾选授予、来源判定（本来源可改、非本来源只读）。
// 样式（11-01）：勾选改 el-checkbox 承载，来源只读标记消费 --bms-perm-readonly-bg，补 <style scoped>。
import type { ActionMeta, PermissionEntry } from '@bms/core'
import { ElCheckbox } from 'element-plus'
import { computed } from 'vue'

import { useBasePermissionConfig } from '../../composables/useBasePermissionConfig'

interface Props {
  /** 该表单的动作码清单。 */
  actions?: ActionMeta[]
  /** 授权条目。 */
  entries?: PermissionEntry[]
  /** 当前上下文来源菜单 id（`'0'` = 表单级直接授予）。 */
  sourceMenuId?: string
  /** 是否禁用。 */
  disabled?: boolean
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  actions: () => [],
  entries: () => [],
  sourceMenuId: '0',
  disabled: false,
  emptyText: '暂无可授予的操作',
})

const emit = defineEmits<{ toggle: [payload: { actionId: string; checked: boolean }] }>()

// 挂链：件经基类投影组合式接入继承链（值引入投影）。
useBasePermissionConfig()

/** 动作行（含来源判定）。 */
const rows = computed(() =>
  props.actions.map((action) => {
    const sources = props.entries
      .filter((entry) => entry.permType === 'permission' && entry.targetId === action.id)
      .map((entry) => entry.sourceMenuId)
    const own = sources.includes(props.sourceMenuId)
    return {
      id: action.id,
      name: action.name,
      checked: sources.length > 0,
      readonly: sources.length > 0 && !own,
      sources,
    }
  }),
)

/** 勾选变更。 */
function onToggle(id: string, value: boolean | string | number): void {
  emit('toggle', { actionId: id, checked: value === true })
}
</script>

<template>
  <div class="bms-action-perm" data-test="action-perm" :data-disabled="disabled || undefined">
    <p v-if="rows.length === 0" class="bms-action-perm__empty" data-test="empty">{{ emptyText }}</p>
    <div v-for="row in rows" :key="row.id" class="bms-action-perm__row" :data-test="`action-${row.id}`">
      <el-checkbox
        :data-test="`action-check-${row.id}`"
        :model-value="row.checked"
        :disabled="disabled || row.readonly"
        @update:model-value="onToggle(row.id, $event)"
      >
        {{ row.name }}
      </el-checkbox>
      <span v-if="row.readonly" class="bms-action-perm__readonly" data-test="action-readonly">来自其它来源</span>
    </div>
  </div>
</template>

<style scoped>
.bms-action-perm {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-1);
}

.bms-action-perm__empty {
  margin: 0;
  padding: var(--bms-space-4) 0;
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
  text-align: center;
}

.bms-action-perm__row {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
  min-height: var(--bms-control-height);
}

.bms-action-perm__readonly {
  flex: none;
  padding: 0 var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-xs);
  font-style: normal;
  background: var(--bms-perm-readonly-bg);
  border-radius: var(--bms-radius-sm);
}
</style>
