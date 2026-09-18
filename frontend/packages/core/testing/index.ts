/**
 * `@bms/core/testing`：契约用例工厂（仅测试消费）。
 *
 * 各渲染插件（`ui-ep` / `ui-vant`）与绑定层在自己的 spec 中调用本工厂并传入本实现，
 * 跑同一套断言——「同接口多实现」的机器保障。运行时入口（`@bms/core`）不含本入口。
 *
 * 契约面为**结构化接口**（非具体基类），实现侧可用基类实例或投影适配器接入。
 */

import { describe, expect, it } from 'vitest'

import type { FeedbackState } from '../src'

/** 契约用例套件定义体。 */
export type ContractDefine = () => void

/**
 * 登记一个契约用例套件（「同一契约、多实现」的统一入口）。
 *
 * @param name 契约名（如「受控值契约」）。
 * @param define 套件定义体（在各实现 spec 中传入本实现后执行同一套断言）。
 */
export function describeContract(name: string, define: ContractDefine): void {
  describe(name, define)
}

/** 值契约面。 */
export interface ValueContractTarget<T> {
  /** 当前值。 */
  readonly value: T | undefined
  /** 是否空态。 */
  readonly isEmpty: boolean
  /** 设置值。 */
  setValue(value: T | undefined): void
  /** 订阅值变更。 */
  onChange(listener: (value: T | undefined) => void): () => void
}

/**
 * 值契约（`BaseValue` / `useValue` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 * @param sample 非空样例值。
 */
export function describeValueContract<T>(name: string, create: () => ValueContractTarget<T>, sample: T): void {
  describeContract(name, () => {
    it('初始为空态', () => {
      const target = create()
      expect(target.value).toBeUndefined()
      expect(target.isEmpty).toBe(true)
    })

    it('设置值并订阅变更（同值不重复通知）', () => {
      const target = create()
      const seen: (T | undefined)[] = []
      target.onChange((value) => seen.push(value))

      target.setValue(sample)
      expect(target.value).toBe(sample)
      expect(target.isEmpty).toBe(false)

      target.setValue(sample)
      expect(seen).toEqual([sample])

      target.setValue(undefined)
      expect(target.isEmpty).toBe(true)
      expect(seen).toEqual([sample, undefined])
    })
  })
}

/** 权限上下文契约面。 */
export interface PermissionContractTarget {
  /** 权限码。 */
  readonly codes: readonly string[]
  /** 整体替换权限码。 */
  setCodes(codes: Iterable<string>): void
  /** 是否具备某权限码。 */
  has(code: string): boolean
  /** 是否具备任一权限码。 */
  hasAny(codes: readonly string[]): boolean
  /** 是否具备全部权限码。 */
  hasAll(codes: readonly string[]): boolean
}

/**
 * 权限契约（`BaseAccess` / `useAccess` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePermissionContract(name: string, create: () => PermissionContractTarget): void {
  describeContract(name, () => {
    it('设置权限码并判定（含空集边界）', () => {
      const target = create()
      target.setCodes(['a', 'b'])
      expect([...target.codes].sort()).toEqual(['a', 'b'])
      expect(target.has('a')).toBe(true)
      expect(target.has('c')).toBe(false)
      expect(target.hasAny(['c', 'b'])).toBe(true)
      expect(target.hasAny(['c'])).toBe(false)
      expect(target.hasAll(['a', 'b'])).toBe(true)
      expect(target.hasAll(['a', 'c'])).toBe(false)

      target.setCodes([])
      expect(target.hasAny(['a'])).toBe(false)
      expect(target.hasAll([])).toBe(true)
    })
  })
}

/** 反馈契约面。 */
export interface FeedbackContractTarget {
  /** 当前状态。 */
  readonly state: FeedbackState
  /** 设置状态。 */
  setState(state: FeedbackState): void
  /** 触发重试（仅错误态且注入回调时）。 */
  doRetry(): boolean
  /** 重试回调。 */
  retry?: (() => void) | undefined
}

/**
 * 反馈契约（`BaseFeedback` / `useFeedback` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeFeedbackContract(name: string, create: () => FeedbackContractTarget): void {
  describeContract(name, () => {
    it('状态机（loading → ready / empty / error）', () => {
      const target = create()
      expect(target.state).toBe('loading')
      target.setState('ready')
      expect(target.state).toBe('ready')
      target.setState('empty')
      expect(target.state).toBe('empty')
      target.setState('error')
      expect(target.state).toBe('error')
    })

    it('仅错误态且注入回调时重试', () => {
      const target = create()
      let called = 0
      expect(target.doRetry()).toBe(false)

      target.retry = () => {
        called += 1
      }
      target.setState('ready')
      expect(target.doRetry()).toBe(false)

      target.setState('error')
      expect(target.doRetry()).toBe(true)
      expect(called).toBe(1)
    })
  })
}

/** 容器契约面。 */
export interface ContainerContractTarget {
  /** 是否可折叠。 */
  collapsible: boolean
  /** 是否已折叠。 */
  collapsed: boolean
  /** 切换折叠。 */
  toggleCollapse(): void
}

/**
 * 容器契约（`BaseContainer` / `useBaseContainer` 投影）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeContainerContract(name: string, create: () => ContainerContractTarget): void {
  describeContract(name, () => {
    it('不可折叠时切换为空操作，可折叠时来回切换', () => {
      const target = create()
      expect(target.collapsible).toBe(false)
      target.toggleCollapse()
      expect(target.collapsed).toBe(false)

      target.collapsible = true
      target.toggleCollapse()
      expect(target.collapsed).toBe(true)
      target.toggleCollapse()
      expect(target.collapsed).toBe(false)
    })
  })
}

/** 确认契约面。 */
export interface ConfirmContractTarget {
  /** 是否打开。 */
  readonly open: boolean
  /** 打开并返回结算 Promise。 */
  confirm(options?: { title?: string; content?: string }): Promise<boolean>
  /** 结算。 */
  resolve(value: boolean): void
}

/**
 * 确认契约（`useConfirm`）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeConfirmContract(name: string, create: () => ConfirmContractTarget): void {
  describeContract(name, () => {
    it('打开挂起，结算为确认', async () => {
      const target = create()
      expect(target.open).toBe(false)
      const pending = target.confirm({ title: '删除确认' })
      expect(target.open).toBe(true)
      target.resolve(true)
      await expect(pending).resolves.toBe(true)
      expect(target.open).toBe(false)
    })

    it('结算为取消', async () => {
      const target = create()
      const pending = target.confirm()
      target.resolve(false)
      await expect(pending).resolves.toBe(false)
      expect(target.open).toBe(false)
    })
  })
}

/** 占位字段契约面（依赖后端的字段：字典 / 组织 / 文件 / 验证码）。 */
export interface PlaceholderFieldContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否处于降级（占位）态。 */
  readonly degraded: boolean
  /** 是否禁用（占位态必须禁用）。 */
  readonly disabled: boolean
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 已发起的后端请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 触发一次可能的加载（占位态不得产生请求）。 */
  load(): void
}

/**
 * 占位字段契约（`06_01` 冻结；真实实现 `06_04` ~ `06_07` 继续跑同一套件）。
 *
 * 断言：占位态降级且禁用、不产生后端请求；就绪态不再降级。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePlaceholderFieldContract(name: string, create: () => PlaceholderFieldContractTarget): void {
  describeContract(name, () => {
    it('未就绪时降级且禁用，不产生请求', () => {
      const target = create()
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.disabled).toBe(true)
      expect(target.requestCount).toBe(0)

      target.load()
      expect(target.requestCount).toBe(0)
    })

    it('就绪后不再降级', () => {
      const target = create()
      target.setReady(true)
      expect(target.ready).toBe(true)
      expect(target.degraded).toBe(false)
      expect(target.disabled).toBe(false)
    })
  })
}

/** 占位展示契约面（依赖后端的展示件：表格 / 通知 / 预览 / 审计 / 图表 / 搜索）。 */
export interface PlaceholderDisplayContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否处于降级（占位）态。 */
  readonly degraded: boolean
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 已发起的后端请求计数（占位态必须为 0）。 */
  readonly requestCount: number
  /** 触发一次可能的加载（占位态不得产生请求）。 */
  load(): void
}

/**
 * 占位展示契约（`07_01` 冻结；真实实现 `07_03` ~ `07_07` 继续跑同一套件）。
 *
 * 断言：占位态降级、不产生后端请求；就绪态不再降级。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePlaceholderDisplayContract(name: string, create: () => PlaceholderDisplayContractTarget): void {
  describeContract(name, () => {
    it('未就绪时降级，不产生请求', () => {
      const target = create()
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.requestCount).toBe(0)

      target.load()
      expect(target.requestCount).toBe(0)
    })

    it('就绪后不再降级', () => {
      const target = create()
      target.setReady(true)
      expect(target.ready).toBe(true)
      expect(target.degraded).toBe(false)
    })
  })
}
