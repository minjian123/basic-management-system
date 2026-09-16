/**
 * 拖拽基座片段（`drag-drop`）：拖拽、同区排序与跨区移动。
 *
 * 契约见《组件设计 · 拖拽基座片段》：`create` / `destroy` / `move` / `onChange` +
 * `dragging`（表单设计器、报表与大屏设计器、工作台卡片共用）。
 * 片段**不绑定具体拖拽库**：由宿主编排（HTML5 DnD、Sortable 等）后调用 `move()` 反馈结果；
 * 片段负责「顺序模型 + 变更事件 + 跨区判定」。撤销栈不属本片段（由设计器协作维护）。
 */

import { computed, shallowRef, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 拖拽分组 / 区域标识 */
export type DragGroup = string

/** 移动结果 */
export interface DragMoveResult<T = unknown> {
  from: { group: DragGroup; index: number }
  to: { group: DragGroup; index: number }
  item: T
  /** 是否跨区移动 */
  crossed: boolean
}

/** 拖拽基座片段参数 */
export interface UseDragDropOptions<T = unknown> {
  /** 分组标识（跨区移动限同组；不同组互不干扰） */
  group?: MaybeRefOrGetter<DragGroup>
  /** 模式（`sort` 同区排序 / `cross` 跨区 / `both`） */
  mode?: MaybeRefOrGetter<'sort' | 'cross' | 'both'>
  /** 拖拽把手选择器（触控与误触控制由宿主实现） */
  handle?: MaybeRefOrGetter<string>
  disabled?: MaybeRefOrGetter<boolean>
  /** 动画开关（仅供宿主参考） */
  animation?: MaybeRefOrGetter<boolean>
  /** 变更回调（宿主据此更新模型 / 压撤销栈） */
  onChange?: (result: DragMoveResult<T>) => void
  /** 是否受控：受控时 `move()` 只回调不自行改内部模型 */
  controlled?: boolean
}

/** 拖拽基座片段返回值 */
export interface UseDragDropReturn<T = unknown> {
  readonly dragging: boolean
  readonly group: DragGroup
  readonly mode: string
  readonly disabled: boolean
  /** 创建实例（宿主传入容器元素；返回销毁函数） */
  create: (el: HTMLElement, items?: T[]) => () => void
  destroy: () => void
  /** 反馈一次移动（同区排序或跨区）；返回是否发生变更 */
  move: (from: { group: DragGroup; index: number }, to: { group: DragGroup; index: number }) => boolean
  /** 读取当前顺序模型（受控模式下由宿主维护，返回快照） */
  items: () => T[]
  setDragging: (value: boolean) => void
}

/**
 * 获取拖拽基座能力。
 *
 * 用法：`const drag = useDragDrop<CardItem>({ group: 'workbench', onChange })`；
 * 宿主在拖拽结束时调用 `drag.move({ group, index }, { group, index })`，片段负责校验与回调。
 */
export function useDragDrop<T = unknown>(options: UseDragDropOptions<T> = {}): UseDragDropReturn<T> {
  const capability = declareFragment('drag-drop')

  const dragging = ref(false)
  // 泛型顺序模型用 `shallowRef`：避免深度解包破坏业务对象类型
  const model = shallowRef<T[]>([])
  let element: HTMLElement | undefined

  const group = computed(() => String(toValue(options.group) ?? 'default'))
  const mode = computed(() => toValue(options.mode) ?? 'both')
  const disabled = computed(() => Boolean(toValue(options.disabled)))

  /** 模式判定：`sort` 只允许同区排序、`cross` 只允许跨区、`both` 都允许 */
  const isValid = (from: { group: DragGroup; index: number }, to: { group: DragGroup; index: number }): boolean => {
    if (disabled.value) {
      return false
    }
    const crossed = from.group !== to.group
    return crossed ? mode.value !== 'sort' : mode.value !== 'cross'
  }

  const create = (el: HTMLElement, items: T[] = []): (() => void) => {
    element = el
    model.value = [...items]
    el.setAttribute('data-drag-group', group.value)
    capability.log('debug', `drag-drop 就绪：group=${group.value} mode=${mode.value}`)
    return () => destroy()
  }

  const destroy = (): void => {
    if (element) {
      element.removeAttribute('data-drag-group')
      element = undefined
    }
    dragging.value = false
    model.value = []
  }

  const move = (from: { group: DragGroup; index: number }, to: { group: DragGroup; index: number }): boolean => {
    if (!isValid(from, to)) {
      capability.log('warn', `drag-drop 拒绝移动：${from.group}#${from.index} → ${to.group}#${to.index}`)
      return false
    }
    const crossed = from.group !== to.group
    if (!options.controlled) {
      const current = [...model.value]
      const [moved] = current.splice(from.index, 1)
      if (moved !== undefined) {
        current.splice(to.index, 0, moved)
        model.value = current
      }
    }
    const item = model.value[to.index] as T
    options.onChange?.({ from, to, item, crossed })
    return true
  }

  return {
    get dragging() {
      return dragging.value
    },
    get group() {
      return group.value
    },
    get mode() {
      return mode.value
    },
    get disabled() {
      return disabled.value
    },
    create,
    destroy,
    move,
    items: () => [...model.value],
    setDragging: (value) => {
      dragging.value = value
    },
  }
}
