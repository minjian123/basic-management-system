/**
 * 工具栏投影：把核心 `BaseListToolbar` / `BaseFormToolbar` 投影为响应式面。
 *
 * 具体件（`ListToolbar` / `FormToolbar`）只消费本投影做渲染与动作回传；页面只传覆盖与新增动作。
 */

import {
  BaseFormToolbar,
  BaseListToolbar,
  type ToolbarAction,
  type ToolbarActionOverride,
  type ToolbarGroups,
  type ToolbarHelpMode,
  type ToolbarPermChecker,
} from '@bms/core'
import { computed, onScopeDispose, ref, type ComputedRef } from 'vue'

/** 具体列表工具栏（可实例化）。 */
class ListToolbarState extends BaseListToolbar {}

/** 具体表单工具栏（可实例化）。 */
class FormToolbarState extends BaseFormToolbar {}

/** `useBaseToolbar` 选项。 */
export interface UseBaseToolbarOptions {
  /** 形态（缺省列表）。 */
  kind?: 'list' | 'form'
  /** 页面覆盖（按 `key`）。 */
  overrides?: ToolbarActionOverride[]
  /** 页面新增动作。 */
  actions?: ToolbarAction[]
  /** 权限判定（未提供不过滤）。 */
  permChecker?: ToolbarPermChecker
  /** 右侧直显数。 */
  maxRight?: number
  /** 表单分态。 */
  editing?: boolean
  /** 当前选中数。 */
  selectedCount?: number
  /** 帮助入口可用（元数据锚点）。 */
  helpAvailable?: boolean
  /** 帮助入口形态。 */
  helpMode?: ToolbarHelpMode
  /** 工具栏级加载。 */
  loading?: boolean
}

/** `useBaseToolbar` 返回面。 */
export interface UseBaseToolbarResult {
  /** 左组动作。 */
  left: ComputedRef<ToolbarAction[]>
  /** 右组直显动作（不含帮助）。 */
  right: ComputedRef<ToolbarAction[]>
  /** 溢出动作。 */
  overflow: ComputedRef<ToolbarAction[]>
  /** 合并后的全部可见动作。 */
  visible: ComputedRef<ToolbarAction[]>
  /** 帮助入口是否可见。 */
  helpVisible: ComputedRef<boolean>
  /** 当前分态。 */
  mode: ComputedRef<string>
  /** 设置覆盖。 */
  setOverrides: (overrides: ToolbarActionOverride[]) => void
  /** 设置新增动作。 */
  setActions: (actions: ToolbarAction[]) => void
  /** 注入权限判定。 */
  setPermChecker: (checker: ToolbarPermChecker | undefined) => void
  /** 设置右侧直显数。 */
  setMaxRight: (value: number) => void
  /** 切换分态。 */
  setEditing: (value: boolean) => void
  /** 设置选中数。 */
  setSelectedCount: (count: number) => void
  /** 设置帮助可用。 */
  setHelpAvailable: (value: boolean) => void
  /** 设置加载态。 */
  setLoading: (value: boolean) => void
  /** 动作是否可触发。 */
  canRun: (key: string) => boolean
}

/**
 * 使用工具栏投影。
 *
 * @param options 选项。
 * @returns 响应式面与命令。
 */
export function useBaseToolbar(options: UseBaseToolbarOptions = {}): UseBaseToolbarResult {
  const toolbar = options.kind === 'form' ? new FormToolbarState() : new ListToolbarState()
  toolbar.setOverrides(options.overrides ?? [])
  toolbar.addActions(options.actions ?? [])
  toolbar.setPermChecker(options.permChecker)
  toolbar.setMaxRight(options.maxRight ?? toolbar.maxRight)
  toolbar.setEditing(options.editing ?? false)
  toolbar.setSelectedCount(options.selectedCount ?? 0)
  toolbar.setHelpAvailable(options.helpAvailable ?? false)
  toolbar.setHelpMode(options.helpMode ?? 'toolbar')
  toolbar.setProps({ loading: options.loading ?? false })

  const version = ref(0)
  const bump = (): void => {
    version.value += 1
  }
  toolbar.onLifecycle(bump)
  onScopeDispose(() => toolbar.dispose())

  /** 读取分组（随版本号重算）。 */
  const groups = computed<ToolbarGroups>(() => {
    void version.value
    return toolbar.groups()
  })
  const visible = computed<ToolbarAction[]>(() => {
    void version.value
    return toolbar.visibleActions()
  })
  const helpVisible = computed<boolean>(() => {
    void version.value
    return toolbar.helpVisible
  })
  const mode = computed<string>(() => {
    void version.value
    return toolbar.mode
  })

  return {
    left: computed(() => groups.value.left),
    right: computed(() => groups.value.right),
    overflow: computed(() => groups.value.overflow),
    visible,
    helpVisible,
    mode,
    setOverrides: (overrides) => toolbar.setOverrides(overrides),
    setActions: (actions) => toolbar.addActions(actions),
    setPermChecker: (checker) => toolbar.setPermChecker(checker),
    setMaxRight: (value) => toolbar.setMaxRight(value),
    setEditing: (value) => toolbar.setEditing(value),
    setSelectedCount: (count) => toolbar.setSelectedCount(count),
    setHelpAvailable: (value) => toolbar.setHelpAvailable(value),
    setLoading: (value) => toolbar.setProps({ loading: value }),
    canRun: (key) => {
      void version.value
      return toolbar.canRun(key)
    },
  }
}
