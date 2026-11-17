<script setup lang="ts">
// 表单工具栏具体件（09_02）：只读 / 编辑分态（修改与保存互斥）、左组业务动作、帮助入口（基类内建）。
// 只做渲染与动作回传；分态 / 权限 / 溢出 / 帮助显隐由核心基类维护，业务动作由页面处理。
import { ElButton, ElDropdown, ElDropdownItem, ElDropdownMenu } from 'element-plus'
import { watch } from 'vue'

import type {
  HelpContextFetcher,
  HelpDescriptor,
  ToolbarAction,
  ToolbarActionOverride,
  ToolbarPermChecker,
} from '@bms/core'

import { useBaseToolbar } from '../../composables/useBaseToolbar'
import HelpEntry from '../display/HelpEntry.vue'

interface Props {
  /** 页面覆盖（按 `key`）。 */
  overrides?: ToolbarActionOverride[]
  /** 页面新增动作。 */
  actions?: ToolbarAction[]
  /** 权限判定（未提供不过滤）。 */
  permChecker?: ToolbarPermChecker
  /** 右侧直显数（其余进「更多」）。 */
  maxRight?: number
  /** 工具栏级加载。 */
  loading?: boolean
  /** 是否编辑态（只读 / 编辑分态）。 */
  editing?: boolean
  /** 帮助描述符（未提供时页内不显示帮助入口）。 */
  help?: HelpDescriptor
  /** 帮助取数器。 */
  helpFetcher?: HelpContextFetcher
  /** 帮助按钮文案。 */
  helpLabel?: string
}

const props = withDefaults(defineProps<Props>(), {
  overrides: () => [],
  actions: () => [],
  permChecker: undefined,
  maxRight: 3,
  loading: false,
  editing: false,
  help: undefined,
  helpFetcher: undefined,
  helpLabel: '帮助',
})

const emit = defineEmits<{
  action: [key: string]
  'help-open': []
  'help-close': []
  'help-category': [categoryId: string]
  'help-error': [message: string]
}>()

const { left, right, overflow, helpVisible, setOverrides, setActions, setPermChecker, setMaxRight, setEditing, setLoading, setHelpAvailable, canRun } =
  useBaseToolbar({
    kind: 'form',
    overrides: props.overrides,
    actions: props.actions,
    permChecker: props.permChecker,
    maxRight: props.maxRight,
    loading: props.loading,
    editing: props.editing,
    helpAvailable: props.help?.anchorAvailable ?? false,
  })

watch(
  () => props.overrides,
  (value) => setOverrides(value),
  { deep: true },
)
watch(
  () => props.actions,
  (value) => setActions(value),
  { deep: true },
)
watch(
  () => props.permChecker,
  (value) => setPermChecker(value),
)
watch(
  () => props.maxRight,
  (value) => setMaxRight(value),
)
watch(
  () => props.loading,
  (value) => setLoading(value),
)
watch(
  () => props.editing,
  (value) => setEditing(value),
)
watch(
  () => props.help?.anchorAvailable,
  (value) => setHelpAvailable(value === true),
  { immediate: true },
)

/**
 * 按钮形态（危险优先；`default` 不传类型）。
 *
 * @param action 动作。
 * @returns 形态。
 */
function buttonType(action: ToolbarAction): 'primary' | 'success' | 'warning' | 'danger' | 'info' | undefined {
  if (action.danger === true) {
    return 'danger'
  }
  return action.type === undefined || action.type === 'default' ? undefined : action.type
}

/**
 * 动作触发（不可触发时忽略）。
 *
 * @param key 动作键。
 */
function onAction(key: string): void {
  if (!canRun(key)) {
    return
  }
  emit('action', key)
}
</script>

<template>
  <div class="bms-form-toolbar" role="toolbar" data-test="form-toolbar">
    <div class="bms-form-toolbar__group">
      <el-button
        v-for="action in left"
        :key="action.key"
        :type="buttonType(action)"
        :plain="action.plain === true"
        :disabled="!canRun(action.key)"
        :loading="action.loading === true"
        :title="action.reason"
        :data-test="action.testId"
        @click="onAction(action.key)"
      >
        {{ action.label }}
      </el-button>
    </div>

    <div class="bms-form-toolbar__spacer" />

    <div class="bms-form-toolbar__group">
      <el-button
        v-for="action in right"
        :key="action.key"
        :type="buttonType(action)"
        :plain="action.plain === true"
        :disabled="!canRun(action.key)"
        :loading="action.loading === true"
        :title="action.reason"
        :data-test="action.testId"
        @click="onAction(action.key)"
      >
        {{ action.label }}
      </el-button>

      <el-dropdown v-if="overflow.length > 0" trigger="click" @command="onAction">
        <el-button data-test="toolbar-more">更多</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item
              v-for="action in overflow"
              :key="action.key"
              :command="action.key"
              :disabled="!canRun(action.key)"
              :data-test="action.testId"
            >
              {{ action.label }}
            </el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <help-entry
        v-if="helpVisible"
        mode="toolbar"
        :descriptor="help"
        :fetcher="helpFetcher"
        :label="helpLabel"
        @open="emit('help-open')"
        @close="emit('help-close')"
        @category="(categoryId) => emit('help-category', categoryId)"
        @error="(message) => emit('help-error', message)"
      />
    </div>

    <slot name="side" />
  </div>
</template>

<style scoped>
.bms-form-toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  padding: var(--bms-space-3) 0;
}

.bms-form-toolbar__group {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
}

.bms-form-toolbar__spacer {
  flex: 1;
}
</style>
