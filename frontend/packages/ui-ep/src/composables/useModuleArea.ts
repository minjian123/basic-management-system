/** 模块区域插槽投影：承接布局与容器组件基类投影，并按区域标识解析已登记区域项（只读消费）。 */

import type { FrontendRegistries } from '@bms/core'
import {
  computed,
  defineAsyncComponent,
  ref,
  toValue,
  watch,
  type AsyncComponentLoader,
  type ComputedRef,
  type MaybeRefOrGetter,
  type Ref,
} from 'vue'

import { useBaseContainer, type UseBaseContainerResult } from './useBaseContainer'
import { useBaseLayout } from './useBaseLayout'

/** 区域项（渲染面）。 */
export interface ModuleAreaItem {
  /** 命名空间键。 */
  key: string
  /** 顺序提示。 */
  order: number
  /** 挂接组件（组件对象或异步加载器）。 */
  component: unknown
}

/** 选项。 */
export interface UseModuleAreaOptions {
  /** 区域标识（点分，如 `layout.header`）。 */
  area: MaybeRefOrGetter<string>
  /** 宿主注册表集合。 */
  registries: FrontendRegistries
  /** 装配版本号（装配 / 释放后自增，用于重算；注册表实例本身非响应式）。 */
  revision?: MaybeRefOrGetter<number>
}

/** `useModuleArea` 返回面。 */
export interface UseModuleAreaResult {
  /** 是否隐藏（响应式；布局语义）。 */
  hidden: Ref<boolean>
  /** 容器语义面（可折叠 / 尺寸档位等）。 */
  container: UseBaseContainerResult
  /** 区域项（按顺序提示稳定排序，同值保持登记序）。 */
  items: Ref<ModuleAreaItem[]>
  /** 是否为空区域。 */
  isEmpty: ComputedRef<boolean>
  /** 解析挂接组件（异步加载器包装为异步组件，并复用解析结果）。 */
  resolve: (component: unknown) => unknown
}

/**
 * 区域项稳定排序（顺序提示升序，同值保持登记序）。
 *
 * @param left 左项。
 * @param right 右项。
 */
function compareItems(left: ModuleAreaItem, right: ModuleAreaItem): number {
  return left.order - right.order
}

/**
 * 使用模块区域插槽投影。
 *
 * @param options 选项。
 * @returns 区域项与解析面。
 */
export function useModuleArea(options: UseModuleAreaOptions): UseModuleAreaResult {
  const layout = useBaseLayout()
  const container = useBaseContainer()
  const revision = computed(() => toValue(options.revision ?? 0))
  /** 已解析挂接组件（按函数标识复用，避免重复创建异步组件）。 */
  const resolved = new WeakMap<object, unknown>()

  /** 读取当前区域项（保序）。 */
  function readItems(): ModuleAreaItem[] {
    const area = toValue(options.area)
    return options.registries.pageArea
      .resolveByArea(area)
      .map((record) => ({ key: record.key, order: record.order, component: record.component }))
      .sort(compareItems)
  }

  const items = ref<ModuleAreaItem[]>(readItems())

  watch([() => toValue(options.area), revision], () => {
    items.value = readItems()
  })

  /**
   * 解析挂接组件（函数视为异步加载器）。
   *
   * @param component 挂接组件。
   */
  function resolve(component: unknown): unknown {
    if (typeof component !== 'function') {
      return component
    }
    const key = component as object
    const hit = resolved.get(key)
    if (hit !== undefined) {
      return hit
    }
    const async = defineAsyncComponent(component as AsyncComponentLoader)
    resolved.set(key, async)
    return async
  }

  return {
    hidden: layout.hidden,
    container,
    items,
    isEmpty: computed(() => items.value.length === 0),
    resolve,
  }
}
