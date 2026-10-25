/**
 * 模块区域插槽投影：承接布局与容器组件基类投影，并按区域标识解析已登记区域项（只读消费）；
 * 并承载**具名插槽显式上下文通道**（宿主页提供 → 区域项只读取得，需求 `05-11`）。
 */

import type { FrontendRegistries, ModuleSlotContext } from '@bms/core'
import {
  computed,
  defineAsyncComponent,
  inject,
  provide,
  readonly,
  ref,
  toValue,
  watch,
  type AsyncComponentLoader,
  type ComputedRef,
  type InjectionKey,
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
  /** 展示名（`tabs` 形态页签标题；缺省取键）。 */
  title: string | undefined
  /** 图标键（`tabs` 形态页签图标；未登记不渲染）。 */
  icon: string | undefined
}

/** 选项。 */
export interface UseModuleAreaOptions {
  /** 区域 / 具名插槽标识（点分，如 `sys.user.detail.tabs`）。 */
  area: MaybeRefOrGetter<string>
  /** 宿主注册表集合。 */
  registries: FrontendRegistries
  /** 装配版本号（装配 / 释放后自增，用于重算；注册表实例本身非响应式）。 */
  revision?: MaybeRefOrGetter<number>
  /** 已持有权限码（按权限显隐；缺省空集合＝带权限约束的项不渲染）。 */
  permissionCodes?: MaybeRefOrGetter<readonly string[]>
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
  const permissionCodes = computed(() => toValue(options.permissionCodes ?? []))
  /** 已解析挂接组件（按函数标识复用，避免重复创建异步组件）。 */
  const resolved = new WeakMap<object, unknown>()

  /** 读取当前区域项（按显示条件与权限过滤后保序）。 */
  function readItems(): ModuleAreaItem[] {
    const area = toValue(options.area)
    return options.registries.pageArea
      .resolveByArea(area, { permissionCodes: permissionCodes.value })
      .map((record) => ({
        key: record.key,
        order: record.order,
        component: record.component,
        title: record.title,
        icon: record.icon,
      }))
      .sort(compareItems)
  }

  const items = ref<ModuleAreaItem[]>(readItems())

  watch([() => toValue(options.area), revision, permissionCodes], () => {
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

/** 分配段载荷（宿主收草稿：段名 + 全量值；宿主按段名装配进编排请求）。 */
export interface HostSubmitterSegment {
  /** 段名（与宿主编排端点字段一致，如 `role_ids` / `user_posts` / `user_depts`）。 */
  key: string
  /** 段值（全量覆盖语义：集合 + 主要项）。 */
  value: Record<string, unknown>
}

/** 宿主提交器登记入参（区域项挂载时登记；宿主工具栏「保存」时收集草稿并统一提交）。 */
export interface HostSubmitterEntry {
  /** 是否含未提交改动（宿主脏标记 / 离开拦截）。 */
  isDirty: () => boolean
  /** 构建本区域项的分配段（**无改动返回 `null`**）。 */
  buildSegment: () => HostSubmitterSegment | null
  /** 提交成功后刷新（宿主在编排成功后调用）。 */
  reload: () => Promise<void>
}

/** 宿主提交器注册通道（插槽上下文字段 `registerSubmitter` 的**值即该函数本身**）。 */
export type HostSubmitterRegistrar = (entry: HostSubmitterEntry) => void

/** 具名插槽上下文注入键（宿主页与插件均不直接使用）。 */
export const MODULE_SLOT_CONTEXT_KEY: InjectionKey<Readonly<Ref<ModuleSlotContext | undefined>>> = Symbol(
  'bms.module-slot-context',
)

/**
 * 提供具名插槽上下文（**区域插槽件内部使用**）。
 *
 * 上下文以**冻结浅拷贝**提供：区域项（插件）侧改动不生效；未声明即为 `undefined`（插件自行降级）。
 *
 * @param context 上下文来源（响应式；宿主页声明的作用实体标识等）。
 */
export function provideModuleSlotContext(
  context: MaybeRefOrGetter<Record<string, unknown> | undefined>,
): void {
  const source = computed<ModuleSlotContext | undefined>(() => {
    const value = toValue(context)
    return value === undefined ? undefined : Object.freeze({ ...value })
  })
  provide(MODULE_SLOT_CONTEXT_KEY, readonly(source))
}

/**
 * 读取具名插槽上下文（**区域项组件消费**）。
 *
 * 非路由承载宿主页（表单框架记录页签等）的作用实体标识经此取得；未注入时为 `undefined`。
 *
 * @returns 只读上下文（调用方自行降级：不假定存在、不发起请求）。
 */
export function useModuleSlotContext(): ComputedRef<ModuleSlotContext | undefined> {
  const source = inject(MODULE_SLOT_CONTEXT_KEY, undefined)
  return computed(() => source?.value)
}

/**
 * 读取具名插槽上下文的单个字段（**区域项组件消费**）。
 *
 * @param key 字段名。
 * @returns 字段值（未注入或键缺失时为 `undefined`）。
 */
export function useModuleSlotField<T = unknown>(key: string): ComputedRef<T | undefined> {
  const context = useModuleSlotContext()
  return computed(() => context.value?.[key] as T | undefined)
}
