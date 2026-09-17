/**
 * 容器片段（`container`）：区域 / 面板类容器的公共形态。
 *
 * 契约见《组件设计 · 容器片段》：插槽（header / toolbar / footer / default）、折叠、
 * 分栏、区域令牌。片段只维护「结构状态」（是否折叠、分栏数、区域属性），渲染与视觉由组件承担。
 */

import { computed, ref, toValue, watch, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 容器插槽名（渲染方据此排布） */
export type ContainerSlotName = 'header' | 'toolbar' | 'footer' | 'default'

/** 容器片段参数 */
export interface UseContainerOptions {
  title?: MaybeRefOrGetter<string>
  collapsible?: MaybeRefOrGetter<boolean>
  /** 受控折叠态（传入即受控：内部变更只回调，不自行改值） */
  collapsed?: MaybeRefOrGetter<boolean>
  bordered?: MaybeRefOrGetter<boolean>
  /** 内边距档位（映射令牌 `--bms-density-gap-*`） */
  padding?: MaybeRefOrGetter<'none' | 'compact' | 'default' | 'loose'>
  /** 分栏列数（1 表示单列） */
  columns?: MaybeRefOrGetter<number>
  onCollapseChange?: (collapsed: boolean) => void
}

/** 容器片段返回值 */
export interface UseContainerReturn {
  readonly title: string
  readonly isCollapsible: boolean
  readonly isCollapsed: boolean
  readonly isControlled: boolean
  readonly bordered: boolean
  readonly padding: string
  readonly columns: number
  /** 区域属性（供根元素透传：`data-columns` / `data-padding` / `data-collapsed`） */
  readonly containerAttrs: Record<string, string>
  toggle: () => void
  collapse: () => void
  expand: () => void
  /** 是否渲染某插槽（`header` 有标题或工具栏时） */
  hasSlot: (slot: ContainerSlotName) => boolean
}

/**
 * 获取容器能力。
 *
 * 用法：`const container = useContainer({ title, collapsible: true })`，再把 `containerAttrs` 透传到根元素。
 */
export function useContainer(options: UseContainerOptions = {}): UseContainerReturn {
  declareFragment('container')

  const isControlled = computed(() => options.collapsed !== undefined)
  const innerCollapsed = ref(Boolean(toValue(options.collapsed)))
  watch(
    () => toValue(options.collapsed),
    (next) => {
      if (next !== undefined) {
        innerCollapsed.value = Boolean(next)
      }
    },
    { immediate: true },
  )

  const title = computed(() => String(toValue(options.title) ?? ''))
  const isCollapsible = computed(() => Boolean(toValue(options.collapsible)))
  const isCollapsed = computed(() => isCollapsible.value && innerCollapsed.value)
  const bordered = computed(() => Boolean(toValue(options.bordered)))
  const padding = computed(() => String(toValue(options.padding) ?? 'default'))
  const columns = computed(() => Math.max(1, Number(toValue(options.columns) ?? 1)))

  const setCollapsed = (next: boolean): void => {
    if (!isCollapsible.value) {
      return
    }
    if (!isControlled.value) {
      innerCollapsed.value = next
    }
    options.onCollapseChange?.(next)
  }

  const containerAttrs = computed<Record<string, string>>(() => ({
    'data-columns': String(columns.value),
    'data-padding': padding.value,
    'data-collapsed': isCollapsed.value ? 'true' : 'false',
  }))

  return {
    get title() {
      return title.value
    },
    get isCollapsible() {
      return isCollapsible.value
    },
    get isCollapsed() {
      return isCollapsed.value
    },
    get isControlled() {
      return isControlled.value
    },
    get bordered() {
      return bordered.value
    },
    get padding() {
      return padding.value
    },
    get columns() {
      return columns.value
    },
    get containerAttrs() {
      return containerAttrs.value
    },
    toggle: () => setCollapsed(!isCollapsed.value),
    collapse: () => setCollapsed(true),
    expand: () => setCollapsed(false),
    hasSlot: (slot) => (slot === 'header' ? title.value.length > 0 : true),
  }
}
