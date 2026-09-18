/** 容器件投影：把核心容器组件基类 `BaseContainer` 投影为组合式（可折叠 / 折叠态 / 分栏）。 */

import { BaseContainer } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体容器件（可实例化）。 */
class ContainerState extends BaseContainer {}

/** 选项。 */
export interface UseBaseContainerOptions {
  /** 是否可折叠。 */
  collapsible?: boolean
  /** 初始折叠态。 */
  collapsed?: boolean
  /** 是否分栏。 */
  split?: boolean
}

/** `useBaseContainer` 返回面。 */
export interface UseBaseContainerResult {
  /** 容器基类实例。 */
  container: BaseContainer
  /** 是否可折叠（响应式）。 */
  collapsible: Ref<boolean>
  /** 是否已折叠（响应式）。 */
  collapsed: Ref<boolean>
  /** 是否分栏（响应式）。 */
  split: Ref<boolean>
  /** 尺寸语义值（响应式）。 */
  sizeToken: Ref<string>
  /** 是否紧凑密度（响应式）。 */
  isCompact: Ref<boolean>
  /** 设置可折叠。 */
  setCollapsible: (value: boolean) => void
  /** 设置折叠态（可折叠时生效）。 */
  setCollapsed: (value: boolean) => void
  /** 切换折叠。 */
  toggle: () => void
}

/**
 * 使用容器件投影。
 *
 * @param options 选项。
 * @returns 容器基类实例与响应式面。
 */
export function useBaseContainer(options: UseBaseContainerOptions = {}): UseBaseContainerResult {
  const container = new ContainerState()
  if (options.collapsible !== undefined) {
    container.collapsible = options.collapsible
  }
  if (options.collapsed !== undefined) {
    container.collapsed = options.collapsed
  }
  if (options.split !== undefined) {
    container.split = options.split
  }

  const collapsible = ref(container.collapsible)
  const collapsed = ref(container.collapsed)
  const split = ref(container.split)
  const sizeToken = ref<string>(container.sizeToken)
  const isCompact = ref(container.isCompact)
  const off = container.onLifecycle((event) => {
    if (event === 'update') {
      collapsible.value = container.collapsible
      collapsed.value = container.collapsed
      split.value = container.split
      sizeToken.value = container.sizeToken
      isCompact.value = container.isCompact
    }
  })
  onScopeDispose(off)

  return {
    container,
    collapsible,
    collapsed,
    split,
    sizeToken,
    isCompact,
    setCollapsible: (value) => {
      container.collapsible = value
      container.notifyLifecycle('update')
    },
    setCollapsed: (value) => {
      container.collapsed = value
      container.notifyLifecycle('update')
    },
    toggle: () => container.toggleCollapse(),
  }
}
