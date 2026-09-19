<script setup lang="ts">
// 数据范围件（08_04_02）：按动作配置规则表达式（默认无数据权限），编辑复用表达式编辑器（预置变量 / 字段插入、模板套用与校验）。
import type { DataScopeRow } from '@bms/core'
import { computed, ref, watch } from 'vue'

import { useBaseDataState } from '../../composables/useBaseDataState'
import ExpressionEditor, { type ExpressionTemplate, type ExpressionToken } from './ExpressionEditor.vue'

interface Props {
  /** 动作 → 规则表达式行。 */
  rows?: DataScopeRow[]
  /** 是否禁用。 */
  disabled?: boolean
  /** 预置变量令牌（由调用方下发）。 */
  variables?: ExpressionToken[]
  /** 已注册字段令牌（由调用方下发）。 */
  fields?: ExpressionToken[]
  /** 常用范围模板。 */
  templates?: ExpressionTemplate[]
  /** 当前编辑动作键（`v-model:activeKey`）。 */
  activeKey?: string
  /** 空态文案。 */
  emptyText?: string
}

const props = withDefaults(defineProps<Props>(), {
  rows: () => [],
  disabled: false,
  variables: () => [],
  fields: () => [],
  templates: () => [],
  activeKey: '',
  emptyText: '暂无数据范围配置',
})

const emit = defineEmits<{
  change: [payload: { actionKey: string; expression: string }]
  'update:activeKey': [key: string]
  'apply-template': [key: string]
}>()

const { state, setState } = useBaseDataState()
/** 内部当前动作（受控覆盖：`activeKey` 提供时优先）。 */
const innerActiveKey = ref('')

watch(props.rows, (rows) => setState(rows.length === 0 ? 'empty' : 'ready'), { immediate: true })

/** 生效当前动作键（缺省取首个动作）。 */
const activeKey = computed(() => {
  const key = props.activeKey !== '' ? props.activeKey : innerActiveKey.value
  if (key !== '' && props.rows.some((row) => row.actionKey === key)) {
    return key
  }
  return props.rows[0]?.actionKey ?? ''
})

/** 当前动作行。 */
const activeRow = computed(() => props.rows.find((row) => row.actionKey === activeKey.value))

/** 当前动作的规则表达式。 */
const expression = computed(() => activeRow.value?.expression ?? '')

/** 规则摘要（空表达式展示「无数据权限」）。 */
function summary(row: DataScopeRow): string {
  return row.expression.trim() === '' ? '无数据权限' : row.expression
}

/** 切换当前动作。 */
function selectAction(key: string): void {
  innerActiveKey.value = key
  emit('update:activeKey', key)
}

/** 表达式变更上抛。 */
function onExpression(value: string): void {
  if (activeKey.value === '') {
    return
  }
  emit('change', { actionKey: activeKey.value, expression: value })
}

/** 套用模板（写入当前动作表达式并上抛）。 */
function applyTemplate(template: ExpressionTemplate): void {
  if (activeKey.value === '') {
    return
  }
  emit('apply-template', template.key)
  emit('change', { actionKey: activeKey.value, expression: template.expression })
}

/** 清除数据范围（表达式置空，默认无数据权限）。 */
function clearExpression(): void {
  onExpression('')
}
</script>

<template>
  <div class="bms-data-scope-panel" data-test="data-scope-panel" :data-state="state">
    <p v-if="rows.length === 0" data-test="empty">{{ emptyText }}</p>

    <template v-else>
      <ul class="bms-data-scope-panel__actions" data-test="scope-actions">
        <li
          v-for="row in rows"
          :key="row.actionKey"
          :data-test="`scope-${row.actionKey}`"
          :data-active="row.actionKey === activeKey || undefined"
        >
          <button type="button" data-test="scope-select" @click="selectAction(row.actionKey)">
            {{ row.actionLabel }}
          </button>
          <code data-test="scope-summary">{{ summary(row) }}</code>
        </li>
      </ul>

      <div v-if="activeRow" class="bms-data-scope-panel__editor" data-test="scope-editor">
        <ExpressionEditor
          :model-value="expression"
          :read-only="disabled"
          :fields="fields"
          :variables="variables"
          :templates="templates"
          @update:model-value="onExpression"
          @insert="$emit('change', { actionKey: activeKey, expression: $event.token.insert })"
        />
        <div class="bms-data-scope-panel__actions-row">
          <button
            v-for="template in templates"
            :key="template.key"
            type="button"
            :data-test="`scope-template-${template.key}`"
            :disabled="disabled"
            @click="applyTemplate(template)"
          >
            {{ template.label }}
          </button>
          <button type="button" data-test="scope-clear" :disabled="disabled" @click="clearExpression">
            清除数据范围
          </button>
        </div>
      </div>
    </template>
  </div>
</template>
