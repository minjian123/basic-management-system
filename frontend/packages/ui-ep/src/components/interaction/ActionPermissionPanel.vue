<script setup lang="ts">
// 操作权限面板（08-4-4，新口径）：某表单的动作码清单——默认无、勾选授予、来源判定（本来源可改、非本来源只读）。
import type { ActionMeta, PermissionEntry } from '@bms/core'
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
      .filter((entry) => entry.permType === 'action' && entry.targetId === action.id)
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
</script>

<template>
  <div class="bms-action-perm" data-test="action-perm" :data-disabled="disabled || undefined">
    <p v-if="rows.length === 0" data-test="empty">{{ emptyText }}</p>
    <label v-for="row in rows" :key="row.id" class="bms-action-perm__row" :data-test="`action-${row.id}`">
      <input
        type="checkbox"
        :data-test="`action-check-${row.id}`"
        :checked="row.checked"
        :disabled="disabled || row.readonly"
        @change="emit('toggle', { actionId: row.id, checked: ($event.target as HTMLInputElement).checked })"
      />
      <span>{{ row.name }}</span>
      <em v-if="row.readonly" data-test="action-readonly">来自其它来源</em>
    </label>
  </div>
</template>
