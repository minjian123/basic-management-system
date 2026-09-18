<script setup lang="ts">
// 权限配置（占位版，08_01_01）：契约先行冻结；数据通路未就绪时不请求、只读 + 降级提示。权限树挂树域（useBaseTreeData）。
import type { TreeNode } from '@bms/core'
import { computed, watch } from 'vue'

import { useBaseTreeData } from '../../composables/useBaseTreeData'
import { useInteractionPlaceholder } from '../../composables/useInteractionPlaceholder'

/** 权限页签。 */
export type PermissionTab = 'tree' | 'field' | 'scope' | 'subject'

/** 权限树节点（业务权限为推导只读）。 */
export interface PermissionNode {
  /** 节点键。 */
  key: string
  /** 节点名称。 */
  label: string
  /** 节点类型。 */
  type: 'menu' | 'form' | 'business' | 'action'
  /** 是否已授予。 */
  checked?: boolean
  /** 子节点。 */
  children?: PermissionNode[]
}

/** 字段权限矩阵行（表单 × 字段）。 */
export interface FieldPermRow {
  /** 表单键。 */
  formKey: string
  /** 表单名称。 */
  formLabel: string
  /** 字段权限项。 */
  fields: { key: string; label: string; visible: boolean; editable: boolean }[]
}

/** 动作数据范围行。 */
export interface DataScopeRow {
  /** 动作键。 */
  actionKey: string
  /** 动作名称。 */
  actionLabel: string
  /** 规则表达式。 */
  expression: string
  /** 是否预置模板。 */
  builtin?: boolean
}

/** 主体绑定项。 */
export interface SubjectItem {
  /** 主体标识。 */
  id: string
  /** 主体类型。 */
  type: 'user' | 'position' | 'dept'
  /** 主体名称。 */
  name: string
}

/** 扁平化权限树节点（含层级深度）。 */
interface FlatPermissionNode {
  /** 节点。 */
  node: PermissionNode
  /** 层级深度。 */
  depth: number
}

interface Props {
  /** 数据通路是否就绪。 */
  ready?: boolean
  /** 当前角色标识。 */
  roleId?: string | number
  /** 当前页签。 */
  tab?: PermissionTab
  /** 权限树数据。 */
  treeNodes?: PermissionNode[]
  /** 字段权限矩阵。 */
  fieldPerms?: FieldPermRow[]
  /** 动作数据范围。 */
  dataScopes?: DataScopeRow[]
  /** 主体绑定。 */
  subjects?: SubjectItem[]
  /** 加载中。 */
  loading?: boolean
  /** 是否存在未保存变更。 */
  dirty?: boolean
  /** 降级文案。 */
  degradeText?: string
}

const props = withDefaults(defineProps<Props>(), {
  ready: false,
  roleId: undefined,
  tab: 'tree',
  treeNodes: () => [],
  fieldPerms: () => [],
  dataScopes: () => [],
  subjects: () => [],
  loading: false,
  dirty: false,
  degradeText: '权限配置未就绪（占位）',
})

const emit = defineEmits<{
  'update:tab': [tab: PermissionTab]
  change: [payload: { kind: PermissionTab; value: unknown }]
  save: []
  reset: []
  retry: []
}>()

const placeholder = useInteractionPlaceholder({ ready: props.ready })
const { setNodes } = useBaseTreeData()

watch(
  () => props.ready,
  (next) => placeholder.setReady(next),
)

watch(
  [() => props.ready, () => props.treeNodes],
  () => {
    if (props.ready) {
      setNodes((props.treeNodes ?? []) as TreeNode[])
    }
  },
  { immediate: true },
)

/** 权限树扁平化（模板不做递归）。 */
const flatTree = computed<FlatPermissionNode[]>(() => flatten(props.treeNodes))

function flatten(nodes: readonly PermissionNode[], depth = 0): FlatPermissionNode[] {
  return nodes.flatMap((node) => [
    { node, depth },
    ...(node.children ? flatten(node.children, depth + 1) : []),
  ])
}

function toggleNode(node: PermissionNode): void {
  emit('change', { kind: 'tree', value: { key: node.key, checked: !node.checked } })
}

function toggleField(formKey: string, fieldKey: string, key: 'visible' | 'editable', value: boolean): void {
  emit('change', { kind: 'field', value: { formKey, fieldKey, key, value } })
}
</script>

<template>
  <div
    class="bms-permission-config"
    :data-ready="placeholder.ready.value"
    :data-degraded="placeholder.degraded.value"
  >
    <slot v-if="placeholder.degraded.value" name="degrade">
      <div class="bms-interaction-placeholder" data-test="placeholder">{{ degradeText }}</div>
    </slot>
    <template v-else>
      <slot name="live">
        <div class="bms-permission-config__tabs" data-test="tabs">
        <button
          v-for="item in (['tree', 'field', 'scope', 'subject'] as PermissionTab[])"
          :key="item"
          type="button"
          :data-test="`tab-${item}`"
          :data-active="tab === item || undefined"
          @click="emit('update:tab', item)"
        >
          {{ item }}
        </button>
      </div>

      <div class="bms-permission-config__panel" data-test="panel">
        <div v-if="tab === 'tree'" data-test="panel-tree">
          <p v-if="flatTree.length === 0" data-test="empty">暂无权限数据</p>
          <div
            v-for="entry in flatTree"
            :key="entry.node.key"
            class="bms-permission-config__node"
            :data-test="`node-${entry.node.key}`"
            :data-type="entry.node.type"
            :style="{ paddingLeft: `${entry.depth * 16}px` }"
          >
            <label>
              <input
                type="checkbox"
                :data-test="`node-check-${entry.node.key}`"
                :checked="entry.node.checked"
                @change="toggleNode(entry.node)"
              />
              {{ entry.node.label }}
              <em v-if="entry.node.type === 'business'" data-test="derived">推导</em>
            </label>
          </div>
          <div class="bms-permission-config__actions">
            <button type="button" data-test="save" :disabled="placeholder.disabled.value" @click="emit('save')">
              保存
            </button>
            <button type="button" data-test="reset" :disabled="placeholder.disabled.value" @click="emit('reset')">
              撤销
            </button>
            <span v-if="dirty" data-test="dirty">未保存</span>
          </div>
        </div>

        <div v-else-if="tab === 'field'" data-test="panel-field">
          <p v-if="fieldPerms.length === 0" data-test="empty">暂无字段权限数据</p>
          <div v-for="form in fieldPerms" :key="form.formKey" :data-test="`form-${form.formKey}`">
            <strong>{{ form.formLabel }}</strong>
            <div
              v-for="field in form.fields"
              :key="field.key"
              class="bms-permission-config__field"
              :data-test="`field-${form.formKey}-${field.key}`"
            >
              <span>{{ field.label }}</span>
              <label>
                可见
                <input
                  type="checkbox"
                  :checked="field.visible"
                  @change="toggleField(form.formKey, field.key, 'visible', !field.visible)"
                />
              </label>
              <label>
                可编辑
                <input
                  type="checkbox"
                  :checked="field.editable"
                  @change="toggleField(form.formKey, field.key, 'editable', !field.editable)"
                />
              </label>
            </div>
          </div>
        </div>

        <div v-else-if="tab === 'scope'" data-test="panel-scope">
          <p v-if="dataScopes.length === 0" data-test="empty">暂无数据范围配置</p>
          <div
            v-for="row in dataScopes"
            :key="row.actionKey"
            class="bms-permission-config__scope"
            :data-test="`scope-${row.actionKey}`"
          >
            <span>{{ row.actionLabel }}</span>
            <code>{{ row.expression }}</code>
          </div>
        </div>

        <div v-else data-test="panel-subject">
          <p v-if="subjects.length === 0" data-test="empty">暂无主体绑定</p>
          <div
            v-for="subject in subjects"
            :key="subject.id"
            class="bms-permission-config__subject"
            :data-test="`subject-${subject.id}`"
            :data-type="subject.type"
          >
            {{ subject.name }}
          </div>
        </div>
      </div>
      </slot>
    </template>
  </div>
</template>
