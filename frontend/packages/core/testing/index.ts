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

export * from './form-layout'
export * from './form-render'
export * from './message-catalog'
export * from './approval-flow'
export * from './process-modeler'
export * from './chart'
export * from './report-designer'
export * from './screen-designer'
export * from './screen-player'
export * from './table'
export * from './query-scheme'
export * from './status'
export * from './metric'
export * from './notification'
export * from './ai-assistant'
export * from './search'
export * from './org-select'

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

/** 占位交互契约面（依赖后端的交互件：权限配置 / 审批流展示 / 流程建模器）。 */
export interface PlaceholderInteractionContractTarget {
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
 * 占位交互契约（`08_01_01` 冻结；真实实现 `08_04` / `08_08` 继续跑同一套件）。
 *
 * 断言：占位态降级且禁用、不产生后端请求；就绪态不再降级、不再禁用。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePlaceholderInteractionContract(
  name: string,
  create: () => PlaceholderInteractionContractTarget,
): void {
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

    it('就绪后不再降级、不再禁用', () => {
      const target = create()
      target.setReady(true)
      expect(target.ready).toBe(true)
      expect(target.degraded).toBe(false)
      expect(target.disabled).toBe(false)
    })
  })
}

/** 向导契约面（步骤编排：可见步骤 / 分步与整体校验 / 跳转 / 分支 / 结果态）。 */
export interface WizardContractTarget {
  /** 可见步骤键（顺序）。 */
  readonly visibleKeys: readonly string[]
  /** 当前步骤键。 */
  readonly currentKey: string | undefined
  /** 已到达步骤键（保序）。 */
  readonly visited: readonly string[]
  /** 当前步校验失败文案。 */
  readonly stepError: string
  /** 是否处于结果态。 */
  readonly isResult: boolean
  /** 设置步骤集（含校验器）。 */
  setSteps(steps: readonly WizardContractStep[]): void
  /** 设置某步可见性（分支步骤）。 */
  setVisible(key: string, visible: boolean): void
  /** 下一步（含当前步校验）。 */
  next(): Promise<boolean>
  /** 上一步。 */
  prev(): boolean
  /** 跳转到指定步骤。 */
  goTo(key: string): boolean
  /** 整体校验。 */
  validateAll(): Promise<WizardContractValidation>
  /** 完成（进入结果态）。 */
  complete(result: { status: 'success' | 'error'; title?: string; message?: string }): void
  /** 重置。 */
  reset(): void
}

/** 向导契约步骤（最小面）。 */
export interface WizardContractStep {
  /** 步骤键。 */
  key: string
  /** 可见条件（分支步骤）。 */
  visible?: boolean
  /** 当前步校验器。 */
  validate?: () => boolean | string | Promise<boolean | string>
}

/** 向导契约校验结果。 */
export interface WizardContractValidation {
  /** 是否通过。 */
  valid: boolean
  /** 首个出错步骤键。 */
  stepKey?: string
  /** 错误文案。 */
  message?: string
}

/**
 * 向导契约（`BaseWizard` / `useBaseWizard` 投影；`08_03_01` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：`setSteps` 传入三步 `base` / `plan`（分支，`visible: false`）/ `admin`，
 * `base` 校验器为 `() => false`（可通过 `setVisible` 驱动分支）之外的行为以本套件断言为准。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeWizardContract(name: string, create: () => WizardContractTarget): void {
  describeContract(name, () => {
    it('初始定位首个可见步（分支步不可见时跳过）', () => {
      const target = create()
      target.setSteps([
        { key: 'base', validate: () => true },
        { key: 'plan', visible: false, validate: () => true },
        { key: 'admin', validate: () => true },
      ])
      expect(target.visibleKeys).toEqual(['base', 'admin'])
      expect(target.currentKey).toBe('base')
      expect(target.visited).toEqual(['base'])
    })

    it('分步校验：失败停本步并写错误文案，通过后前进并记已到达', async () => {
      const target = create()
      target.setSteps([
        { key: 'base', validate: () => '请填写名称' },
        { key: 'admin', validate: () => true },
      ])

      await expect(target.next()).resolves.toBe(false)
      expect(target.currentKey).toBe('base')
      expect(target.stepError).toBe('请填写名称')

      target.setSteps([
        { key: 'base', validate: () => true },
        { key: 'admin', validate: () => true },
      ])
      await expect(target.next()).resolves.toBe(true)
      expect(target.currentKey).toBe('admin')
      expect(target.stepError).toBe('')
      expect(target.visited).toEqual(['base', 'admin'])
      expect(target.prev()).toBe(true)
      expect(target.currentKey).toBe('base')
    })

    it('仅可跳「已到达」步骤', async () => {
      const target = create()
      target.setSteps([
        { key: 'base', validate: () => true },
        { key: 'plan', validate: () => true },
        { key: 'admin', validate: () => true },
      ])
      expect(target.goTo('admin')).toBe(false)
      expect(target.currentKey).toBe('base')

      await target.next()
      expect(target.currentKey).toBe('plan')
      expect(target.goTo('base')).toBe(true)
      expect(target.currentKey).toBe('base')
    })

    it('分支隐藏当前步后回退到最近有效可见步', async () => {
      const target = create()
      target.setSteps([
        { key: 'base', validate: () => true },
        { key: 'plan', validate: () => true },
        { key: 'admin', validate: () => true },
      ])
      await target.next()
      expect(target.currentKey).toBe('plan')

      target.setVisible('plan', false)
      expect(target.visibleKeys).toEqual(['base', 'admin'])
      expect(target.currentKey).toBe('base')
      expect(target.visited).not.toContain('plan')
    })

    it('整体校验停于首个出错步并定位', async () => {
      const target = create()
      target.setSteps([
        { key: 'base', validate: () => true },
        { key: 'admin', validate: () => '请填写账号' },
        { key: 'confirm', validate: () => false },
      ])
      const result = await target.validateAll()
      expect(result.valid).toBe(false)
      expect(result.stepKey).toBe('admin')
      expect(target.currentKey).toBe('admin')
      expect(target.stepError).toBe('请填写账号')
    })

    it('结果态后导航不动作，重置归零', async () => {
      const target = create()
      target.setSteps([
        { key: 'base', validate: () => true },
        { key: 'admin', validate: () => true },
      ])
      await target.next()
      target.complete({ status: 'success', title: '提交成功' })
      expect(target.isResult).toBe(true)
      await expect(target.next()).resolves.toBe(false)
      expect(target.prev()).toBe(false)
      expect(target.goTo('base')).toBe(false)

      target.reset()
      expect(target.isResult).toBe(false)
      expect(target.currentKey).toBe('base')
      expect(target.visited).toEqual(['base'])
    })
  })
}

/** 偏好契约面（偏好状态编排：写入 / 脏判定 / 保存与待同步 / 取消回滚 / 恢复默认）。 */
export interface PreferencesContractTarget {
  /** 全量偏好值（扁平键：`themeMode` / `notify.inbox` …）。 */
  read(): Record<string, unknown>
  /** 当前默认值（平台默认 ∩ 租户默认）。 */
  defaults(): Record<string, unknown>
  /** 是否有未保存变更。 */
  readonly dirty: boolean
  /** 远端待同步标记。 */
  readonly pendingSync: boolean
  /** 写入单项（不可选项不生效）。 */
  setValue(key: string, value: unknown): void
  /** 保存（返回是否全部成功，含远端）。 */
  save(): Promise<boolean>
  /** 取消（回滚到打开前快照）。 */
  cancel(): void
  /** 恢复默认（跳过不可选项）。 */
  reset(): Promise<boolean>
}

/**
 * 偏好契约（`usePreferences` 投影 / 偏好状态编排）。
 *
 * 目标约定：默认值 `themeMode = 'light'`，租户策略将 `accent` 置为不可选（`enabled: false`）；
 * `create()` 返回「面板已打开（快照已记录）」的状态。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePreferencesContract(name: string, create: () => PreferencesContractTarget): void {
  describeContract(name, () => {
    it('写入后置脏标记，取消回滚到打开前快照', () => {
      const target = create()
      expect(target.dirty).toBe(false)
      expect(target.read().themeMode).toBe('light')

      target.setValue('themeMode', 'dark')
      expect(target.read().themeMode).toBe('dark')
      expect(target.dirty).toBe(true)

      target.cancel()
      expect(target.read().themeMode).toBe('light')
      expect(target.dirty).toBe(false)
    })

    it('保存写本地；无远端注入时置待同步标记且不发请求', async () => {
      const target = create()
      target.setValue('listDensity', 'compact')
      await expect(target.save()).resolves.toBe(false)
      expect(target.pendingSync).toBe(true)
      expect(target.read().listDensity).toBe('compact')
    })

    it('不可选项写入不生效，恢复默认跳过不可选项', async () => {
      const target = create()
      target.setValue('accent', true)
      expect(target.read().accent).toBe(false)
      expect(target.dirty).toBe(false)

      target.setValue('themeMode', 'dark')
      await target.reset()
      expect(target.read().themeMode).toBe(target.defaults().themeMode)
      expect(target.read().accent).toBe(false)
    })
  })
}

/** 批量契约动作结果。 */
export interface BulkActionContractResult {
  /** 成功数量。 */
  success: number
  /** 失败数量。 */
  failed: number
}

/** 批量契约动作定义（最小面）。 */
export interface BulkActionContractAction {
  /** 动作键。 */
  key: string
  /** 权限码（权限能力未注入或无此码时不可见）。 */
  perm?: string
  /** 危险动作（默认二次确认）。 */
  danger?: boolean
  /** 执行逻辑。 */
  run(context: {
    keys: (string | number)[]
    allAcrossPages: boolean
  }): BulkActionContractResult | Promise<BulkActionContractResult>
}

/** 批量操作契约面（选中集合 + 动作编排）。 */
export interface BulkActionContractTarget {
  /** 选择模式（`page` / `cross-page`）。 */
  readonly mode: string
  /** 已选数量。 */
  readonly count: number
  /** 是否按条件全选（跨页）。 */
  readonly allAcrossPages: boolean
  /** 选中键（字符串序）。 */
  selectedKeys(): string[]
  /** 设置总记录数。 */
  setTotal(total: number): void
  /** 设置当前页键。 */
  setPageKeys(keys: (string | number)[]): void
  /** 设置选中态。 */
  select(key: string | number, selected?: boolean): void
  /** 当前页全选。 */
  selectPage(): void
  /** 当前页反选。 */
  invertPage(): void
  /** 跨页全选。 */
  selectAllAcrossPages(): void
  /** 清空选中集合。 */
  clear(): void
  /** 注册动作集合。 */
  setActions(actions: BulkActionContractAction[]): void
  /** 可见动作键（权限过滤后）。 */
  visibleActionKeys(): string[]
  /** 是否需要二次确认。 */
  needsConfirm(key: string): boolean
  /** 请求执行（需确认时返回 `undefined` 并进入确认阶段）。 */
  request(key: string): Promise<BulkActionContractResult | undefined>
  /** 确认执行。 */
  confirm(): Promise<BulkActionContractResult | undefined>
  /** 执行阶段（`idle` / `confirming` / `running` / `done`）。 */
  readonly phase: string
}

/**
 * 批量操作契约（`BaseBulkAction` / `useBaseBulkAction` 投影；`08_03_02` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：选择模式为 `cross-page`；权限上下文含 `user.enable`、不含 `user.delete`；
 * `clearAfterDone` 为真（动作完成后清空选择）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeBulkActionContract(name: string, create: () => BulkActionContractTarget): void {
  describeContract(name, () => {
    it('选中集合去重保序；page 模式翻页剔除不在当前页的键', () => {
      const target = create()
      target.setPageKeys(['1', '2'])
      target.select('2')
      target.select('1')
      target.select('1')
      expect(target.selectedKeys()).toEqual(['2', '1'])
      expect(target.count).toBe(2)
      expect(target.mode).toBe('cross-page')
    })

    it('跨页全选取总记录数，切换页后清条件全选标记', () => {
      const target = create()
      target.setTotal(120)
      target.setPageKeys(['1', '2'])
      target.select('1')
      target.selectAllAcrossPages()
      expect(target.allAcrossPages).toBe(true)
      expect(target.count).toBe(120)

      target.setPageKeys(['3', '4'])
      expect(target.allAcrossPages).toBe(false)
      expect(target.count).toBe(0)
    })

    it('权限过滤：无权动作不可见', () => {
      const target = create()
      target.setActions([
        { key: 'enable', perm: 'user.enable', run: () => ({ success: 1, failed: 0 }) },
        { key: 'delete', perm: 'user.delete', danger: true, run: () => ({ success: 1, failed: 0 }) },
      ])
      expect(target.visibleActionKeys()).toEqual(['enable'])
    })

    it('危险动作进入确认阶段，确认后执行并按需清空', async () => {
      const target = create()
      target.setActions([{ key: 'delete', danger: true, run: () => ({ success: 1, failed: 0 }) }])
      target.setPageKeys(['1'])
      target.select('1')
      expect(target.needsConfirm('delete')).toBe(true)

      await expect(target.request('delete')).resolves.toBeUndefined()
      expect(target.phase).toBe('confirming')

      await expect(target.confirm()).resolves.toEqual({ success: 1, failed: 0 })
      expect(target.phase).toBe('done')
      expect(target.count).toBe(0)
    })

    it('执行中重复请求不动作（防重复提交）', async () => {
      const target = create()
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      target.setActions([
        {
          key: 'export',
          run: async () => {
            await gate
            return { success: 1, failed: 0 }
          },
        },
      ])
      target.setPageKeys(['1'])
      target.select('1')
      const pending = target.request('export')
      expect(target.phase).toBe('running')
      await expect(target.request('export')).resolves.toBeUndefined()
      release()
      await expect(pending).resolves.toEqual({ success: 1, failed: 0 })
    })

    it('部分成功汇总成功与失败数', async () => {
      const target = create()
      target.setActions([{ key: 'disable', run: () => ({ success: 2, failed: 1 }) }])
      target.setPageKeys(['1', '2', '3'])
      target.selectPage()
      await expect(target.request('disable')).resolves.toEqual({ success: 2, failed: 1 })
    })
  })
}

/** 主题契约品牌配置（最小面）。 */
export interface ThemeContractBrand {
  /** 品牌主色。 */
  primaryColor?: string
  /** 租户默认模式。 */
  defaultMode?: 'light' | 'dark' | 'system'
  /** 是否允许用户强调色。 */
  allowUserAccent?: boolean
  /** 是否禁用暗色。 */
  disableDark?: boolean
}

/** 主题契约面。 */
export interface ThemeContractTarget {
  /** 用户模式（`light` / `dark` / `system`）。 */
  readonly mode: string
  /** 有效主题（`light` / `dark`）。 */
  readonly resolved: string
  /** 有效主色。 */
  readonly primary: string
  /** 品牌派生令牌。 */
  brandTokens(): Record<string, string>
  /** 设置用户模式。 */
  setMode(mode: 'light' | 'dark' | 'system'): void
  /** 设置品牌。 */
  setBrand(brand?: ThemeContractBrand): void
  /** 设置用户强调色。 */
  setAccent(color?: string): void
  /** 写入系统偏好。 */
  setSystemPrefersDark(value: boolean): void
  /** 亮暗互切。 */
  toggle(): void
}

/**
 * 主题契约（`BaseTheme` / `useBaseTheme` 投影；`08_03_02` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：初始模式 `light`、系统偏好为亮色、无品牌配置。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeThemeContract(name: string, create: () => ThemeContractTarget): void {
  describeContract(name, () => {
    it('解析优先级：用户模式 > 品牌默认 > 平台默认', () => {
      const target = create()
      expect(target.resolved).toBe('light')

      target.setBrand({ defaultMode: 'dark' })
      expect(target.resolved).toBe('dark')

      target.setMode('light')
      expect(target.resolved).toBe('light')

      target.setMode('system')
      expect(target.resolved).toBe('light')
    })

    it('system 随系统偏好；disableDark 强制亮色', () => {
      const target = create()
      target.setMode('system')
      target.setSystemPrefersDark(true)
      expect(target.resolved).toBe('dark')

      target.setBrand({ defaultMode: 'dark', disableDark: true })
      expect(target.resolved).toBe('light')

      target.setSystemPrefersDark(false)
      expect(target.resolved).toBe('light')
    })

    it('强调色仅在品牌允许时生效；主色派生六项令牌', () => {
      const target = create()
      target.setBrand({ primaryColor: '#1677ff' })
      target.setAccent('#ff0000')
      expect(target.primary).toBe('#1677ff')
      expect(Object.keys(target.brandTokens()).length).toBe(6)

      target.setBrand({ primaryColor: '#1677ff', allowUserAccent: true })
      expect(target.primary).toBe('#ff0000')
      expect(target.brandTokens()['--bms-color-primary']).toBe('#ff0000')
      expect(target.brandTokens()['--bms-color-primary-hover']).not.toBe('#ff0000')
    })

    it('亮暗互切', () => {
      const target = create()
      target.toggle()
      expect(target.mode).toBe('dark')
      expect(target.resolved).toBe('dark')

      target.toggle()
      expect(target.mode).toBe('light')
      expect(target.resolved).toBe('light')
    })
  })
}

/** 租户契约摘要。 */
export interface TenantContractSummary {
  /** 租户标识。 */
  id: string
  /** 租户名称。 */
  name: string
  /** 租户编码。 */
  code?: string
  /** 角色名。 */
  roleName?: string
}

/** 租户契约切换步骤（最小面）。 */
export interface TenantContractSteps {
  /** 换取会话。 */
  switchSession?(): Promise<void>
  /** 重取用户 / 权限 / 菜单。 */
  reloadContext?(): Promise<void>
  /** 重取品牌。 */
  reloadBrand?(): Promise<void>
  /** 清缓存与标签。 */
  clearCache?(): Promise<void>
  /** 跳默认主页。 */
  navigateHome?(): Promise<void>
}

/** 打印契约结果。 */
export interface PrintContractResult {
  /** 文件标识。 */
  fileId?: string
}

/** 打印契约进度上报（已完成量 / 总量）。 */
export type PrintContractReport = (current: number, total: number) => void

/** 打印契约处理函数（宿主注入的导出处理）。 */
export type PrintContractHandler = (report: PrintContractReport) => Promise<PrintContractResult>

/** 打印契约字段（最小面）。 */
export interface PrintContractField {
  /** 字段键。 */
  key: string
  /** 字段名。 */
  label: string
}

/** 打印契约模板（最小面）。 */
export interface PrintContractTemplate {
  /** 模板键。 */
  key: string
  /** 标题。 */
  title: string
  /** 每页明细行容量。 */
  rowsPerPage?: number
  /** 字段区。 */
  fields?: PrintContractField[]
  /** 明细列。 */
  columns?: PrintContractField[]
}

/** 打印契约面（模板 + 编排）。 */
export interface PrintContractTarget {
  /** 当前模板键。 */
  readonly templateKey: string | undefined
  /** 纸张尺寸（毫米，已按方向换算）。 */
  readonly paperSize: { width: number; height: number }
  /** 每页明细行容量。 */
  readonly rowsPerPage: number
  /** 总页数。 */
  readonly pageCount: number
  /** 是否黑白。 */
  readonly mono: boolean
  /** 水印文案。 */
  readonly watermarkText: string
  /** 缩放值。 */
  readonly zoom: number
  /** 预览显隐。 */
  readonly previewVisible: boolean
  /** 编排阶段。 */
  readonly phase: string
  /** 批量模式。 */
  readonly batchMode: string
  /** 是否可导出。 */
  readonly canExport: boolean
  /** 设置模板集。 */
  setTemplates(templates: PrintContractTemplate[]): void
  /** 选择模板。 */
  selectTemplate(key: string): void
  /** 设置单据数据。 */
  setData(data: { fields?: Record<string, unknown>; rows?: Record<string, unknown>[] }): void
  /** 设置纸张与方向。 */
  setPaper(paper: string, orientation: string): void
  /** 设置色调。 */
  setTone(tone: string): void
  /** 设置单据级水印标签。 */
  setWatermarkLabel(label: string): void
  /** 设置缩放（返回夹取后的值）。 */
  setZoom(value: number): number
  /** 设置批量模式。 */
  setBatchMode(mode: string): void
  /** 设置导出许可。 */
  setAllowExport(value: boolean): void
  /** 注入导出处理（`undefined` 为占位）。 */
  setExportHandler(handler: PrintContractHandler | undefined): void
  /** 打开预览。 */
  open(): void
  /** 关闭预览。 */
  close(): void
  /** 每页明细行数（按页序）。 */
  pageRows(): number[]
  /** 页码序列（1 起，连续）。 */
  pageIndexes(): number[]
  /** 字段渲染文本（含缺失占位）。 */
  fieldText(key: string): string
  /** 导出 PDF。 */
  exportPdf(): Promise<PrintContractResult | undefined>
  /** 重试上次失败任务。 */
  retry(): Promise<PrintContractResult | undefined>
}

/**
 * 打印契约（`BasePrint` / `useBasePrint` 投影；`08_03_03` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：模板两个——`order`（三列明细 + 每页 2 行，字段 `customer` / `remark`）与 `label`（单列）；
 * 数据五行明细、`fields.customer` 有值而 `fields.remark` 缺失；
 * 水印信息注入为用户「张三」与租户「租户一」；初始未注入导出处理（占位）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePrintContract(name: string, create: () => PrintContractTarget): void {
  describeContract(name, () => {
    it('模板选择与纸张方向（横向交换宽高）', () => {
      const target = create()
      expect(target.templateKey).toBe('order')

      target.selectTemplate('label')
      expect(target.templateKey).toBe('label')

      target.setPaper('A5', 'landscape')
      expect(target.paperSize).toEqual({ width: 210, height: 148 })

      target.selectTemplate('absent')
      expect(target.templateKey).toBe('label')
    })

    it('预分页：每页行容量、页码连续、末页余量', () => {
      const target = create()
      expect(target.rowsPerPage).toBe(2)
      expect(target.pageRows()).toEqual([2, 2, 1])
      expect(target.pageIndexes()).toEqual([1, 2, 3])
      expect(target.pageCount).toBe(3)
    })

    it('字段渲染与缺失占位', () => {
      const target = create()
      expect(target.fieldText('customer')).toBe('华东制造有限公司')
      expect(target.fieldText('remark')).toBe('—')
    })

    it('水印（单据级标签 + 用户信息）与黑白', () => {
      const target = create()
      expect(target.mono).toBe(false)

      target.setWatermarkLabel('作废')
      expect(target.watermarkText).toContain('作废')
      expect(target.watermarkText).toContain('张三')

      target.setTone('mono')
      expect(target.mono).toBe(true)
    })

    it('预览显隐与缩放夹取', () => {
      const target = create()
      expect(target.previewVisible).toBe(false)

      target.open()
      expect(target.previewVisible).toBe(true)

      expect(target.setZoom(2)).toBe(1.2)
      expect(target.setZoom(0.1)).toBe(0.6)

      target.close()
      expect(target.previewVisible).toBe(false)
    })

    it('批量模式切换', () => {
      const target = create()
      expect(target.batchMode).toBe('separate')
      target.setBatchMode('merged')
      expect(target.batchMode).toBe('merged')
    })

    it('导出占位：未注入处理不动作', async () => {
      const target = create()
      await expect(target.exportPdf()).resolves.toBeUndefined()
      expect(target.phase).toBe('idle')
    })

    it('注入后导出阶段推进并保留结果', async () => {
      const target = create()
      const progress: number[] = []
      target.setExportHandler(async (report) => {
        report(1, 3)
        progress.push(1)
        return { fileId: 'f1' }
      })

      await expect(target.exportPdf()).resolves.toEqual({ fileId: 'f1' })
      expect(target.phase).toBe('done')
      expect(progress).toEqual([1])
    })

    it('导出失败置 failed，retry 恢复', async () => {
      const target = create()
      let fail = true
      target.setExportHandler(async () => {
        if (fail) {
          throw new Error('导出失败')
        }
        return { fileId: 'f2' }
      })

      await expect(target.exportPdf()).resolves.toBeUndefined()
      expect(target.phase).toBe('failed')

      fail = false
      await expect(target.retry()).resolves.toEqual({ fileId: 'f2' })
      expect(target.phase).toBe('done')
    })

    it('导出中重复请求不动作（防重复提交）', async () => {
      const target = create()
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      target.setExportHandler(async () => {
        await gate
        return { fileId: 'f3' }
      })

      const pending = target.exportPdf()
      expect(target.phase).toBe('exporting')
      await expect(target.exportPdf()).resolves.toBeUndefined()

      release()
      await expect(pending).resolves.toEqual({ fileId: 'f3' })
    })

    it('导出许可关闭时不可导出', async () => {
      const target = create()
      target.setExportHandler(async () => ({ fileId: 'f4' }))

      target.setAllowExport(false)
      expect(target.canExport).toBe(false)
      await expect(target.exportPdf()).resolves.toBeUndefined()
    })
  })
}

/** 租户切换契约面。 */
export interface TenantContractTarget {
  /** 切换阶段。 */
  readonly phase: string
  /** 当前租户标识。 */
  readonly currentId: string | undefined
  /** 是否多租户（可切换租户数 > 1）。 */
  readonly multiTenant: boolean
  /** 设置租户列表。 */
  setTenants(list: TenantContractSummary[]): void
  /** 设置当前租户。 */
  setCurrent(tenant: TenantContractSummary | undefined): void
  /** 注入切换步骤。 */
  setSteps(steps: TenantContractSteps): void
  /** 搜索（返回租户标识）。 */
  search(keyword: string): string[]
  /** 请求切换（需确认时返回 `false`）。 */
  request(targetId: string): Promise<boolean>
  /** 确认切换。 */
  confirm(targetId: string): Promise<boolean>
  /** 直接切换。 */
  switchTo(targetId: string): Promise<boolean>
  /** 重试失败切换。 */
  retry(): Promise<boolean>
  /** 重置阶段。 */
  reset(): void
}

/**
 * 租户切换契约（`BaseTenant` / `useBaseTenant` 投影；`08_03_02` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：初始租户列表含 `t1`（当前，名称「租户一」，编码 `A1`，角色「管理员」）
 * 与 `t2`（名称「租户二」，编码 `B2`，角色「操作员」）；`confirmRequired` 为真。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeTenantContract(name: string, create: () => TenantContractTarget): void {
  describeContract(name, () => {
    it('单租户不显示入口；搜索按名称 / 编码 / 角色匹配', () => {
      const target = create()
      expect(target.multiTenant).toBe(true)
      expect(target.search('租户二')).toEqual(['t2'])
      expect(target.search('B2')).toEqual(['t2'])
      expect(target.search('操作员')).toEqual(['t2'])

      target.setTenants([{ id: 't1', name: '租户一' }])
      expect(target.multiTenant).toBe(false)
    })

    it('确认后切换阶段依序推进并提交当前租户', async () => {
      const target = create()
      const phases: string[] = []
      target.setSteps({
        switchSession: async () => {
          phases.push('switching')
        },
        reloadContext: async () => {
          phases.push('reloading')
        },
        clearCache: async () => {
          phases.push('clearing')
        },
        navigateHome: async () => {
          phases.push('navigating')
        },
      })

      await expect(target.request('t2')).resolves.toBe(false)
      expect(target.currentId).toBe('t1')

      await expect(target.confirm('t2')).resolves.toBe(true)
      expect(phases).toEqual(['switching', 'reloading', 'clearing', 'navigating'])
      expect(target.currentId).toBe('t2')
      expect(target.phase).toBe('done')
    })

    it('中段失败置 failed 且保留原租户；retry 从失败目标重试', async () => {
      const target = create()
      let fail = true
      target.setSteps({
        switchSession: async () => {
          if (fail) {
            throw new Error('会话失效')
          }
        },
      })

      await expect(target.switchTo('t2')).resolves.toBe(false)
      expect(target.phase).toBe('failed')
      expect(target.currentId).toBe('t1')

      fail = false
      await expect(target.retry()).resolves.toBe(true)
      expect(target.currentId).toBe('t2')
      expect(target.phase).toBe('done')
    })

    it('切换中重复请求不动作；reset 归 idle', async () => {
      const target = create()
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      target.setSteps({
        switchSession: async () => {
          await gate
        },
      })

      const pending = target.switchTo('t2')
      await expect(target.switchTo('t2')).resolves.toBe(false)
      release()
      await expect(pending).resolves.toBe(true)

      target.reset()
      expect(target.phase).toBe('idle')
      expect(target.currentId).toBe('t2')
    })
  })
}

/** 权限配置契约节点（最小面）。 */
export interface PermissionContractNode {
  /** 节点键。 */
  key: string
  /** 节点名称。 */
  label: string
  /** 节点类型（`menu` / `form` / `business` / `action`）。 */
  type: string
  /** 挂接缺失（不可授予）。 */
  detached?: boolean
  /** 是否已勾选。 */
  checked?: boolean
  /** 子节点。 */
  children?: PermissionContractNode[]
}

/** 权限配置契约字段权限行（最小面）。 */
export interface PermissionContractFieldRow {
  /** 表单键。 */
  formKey: string
  /** 表单名称。 */
  formLabel: string
  /** 字段（缺省可见可编辑）。 */
  fields: { key: string; label: string; visible?: boolean; editable?: boolean }[]
}

/** 权限配置契约数据范围行（最小面）。 */
export interface PermissionContractScopeRow {
  /** 动作键。 */
  actionKey: string
  /** 动作名称。 */
  actionLabel: string
  /** 规则表达式（空 = 无数据权限）。 */
  expression?: string
  /** 是否预置模板行。 */
  builtin?: boolean
}

/** 权限配置契约主体项（最小面）。 */
export interface PermissionContractSubject {
  /** 主体标识。 */
  id: string
  /** 主体类型（`user` / `position` / `dept`）。 */
  type: string
  /** 主体名称。 */
  name: string
}

/** 权限配置契约快照（最小面）。 */
export interface PermissionContractSnapshot {
  /** 角色标识。 */
  roleId?: string | number
  /** 权限树。 */
  nodes: PermissionContractNode[]
  /** 字段权限矩阵。 */
  fieldPerms?: PermissionContractFieldRow[]
  /** 动作数据范围。 */
  dataScopes?: PermissionContractScopeRow[]
  /** 主体绑定。 */
  subjects?: PermissionContractSubject[]
}

/** 权限配置契约处理函数集（未注入即占位）。 */
export interface PermissionContractHandlers {
  /** 取数。 */
  load?: (input: { roleId?: string | number }) => Promise<PermissionContractSnapshot>
  /** 全量覆盖提交。 */
  submit?: (input: { payload: unknown; idempotencyKey: string }) => Promise<{ recordVersion?: number }>
  /** 权限码取数。 */
  loadPermissionCodes?: () => Promise<readonly string[]>
}

/** 权限配置契约载荷（断言用最小面）。 */
export interface PermissionContractPayload {
  /** 菜单键集合。 */
  menus: string[]
  /** 表单键集合。 */
  forms: string[]
  /** 动作键集合。 */
  actions: string[]
  /** 字段收窄项集合。 */
  fields: { formKey: string; fieldKey: string; visible: boolean; editable: boolean }[]
  /** 数据范围项集合。 */
  dataScopes: { actionKey: string; expression: string }[]
  /** 主体绑定集合。 */
  subjects: { id: string; type: string; name: string }[]
}

/** 权限配置契约面（授权编排）。 */
export interface PermissionConfigContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 是否禁用（占位态强制禁用）。 */
  readonly disabled: boolean
  /** 实际发起的请求计数。 */
  readonly requestCount: number
  /** 是否存在未保存变更。 */
  readonly dirty: boolean
  /** 编排阶段。 */
  readonly phase: string
  /** 是否可保存。 */
  readonly canSave: boolean
  /** 权限上下文待刷新标记。 */
  readonly pendingAccessRefresh: boolean
  /** 当前权限码集合（权限上下文）。 */
  readonly accessCodes: readonly string[]
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 注入权限上下文并设置权限码集合。 */
  setAccess(codes: readonly string[]): void
  /** 注入处理函数集（整体替换；未注入的项按占位）。 */
  setHandlers(handlers: PermissionContractHandlers): void
  /** 取数（未就绪 / 未注入不请求）。 */
  load(): Promise<unknown>
  /** 勾选 / 取消勾选节点。 */
  toggleNode(key: string, checked?: boolean): boolean
  /** 查询勾选三态。 */
  checkState(key: string): string | undefined
  /** 勾选集合。 */
  granted(): { menus: string[]; forms: string[]; actions: string[]; implied: string[] }
  /** 字段权限项。 */
  fieldPerm(formKey: string, fieldKey: string): { visible: boolean; editable: boolean } | undefined
  /** 设置字段权限。 */
  setFieldPerm(formKey: string, fieldKey: string, patch: { visible?: boolean; editable?: boolean }): boolean
  /** 动作数据范围表达式。 */
  scopeExpression(actionKey: string): string
  /** 设置动作数据范围。 */
  setDataScope(actionKey: string, expression: string): boolean
  /** 已绑主体标识。 */
  subjectIds(): string[]
  /** 绑定主体。 */
  bindSubject(subject: { id: string; type: string; name: string }): boolean
  /** 全量覆盖提交载荷。 */
  payload(): PermissionContractPayload
  /** 幂等键。 */
  idempotencyKey(): string
  /** 全量覆盖提交。 */
  save(): Promise<unknown>
  /** 重试上次失败提交。 */
  retry(): Promise<unknown>
  /** 撤销未保存变更。 */
  discard(): void
  /** 刷新权限上下文。 */
  refreshAccess(): Promise<boolean>
  /** 失败定位页签。 */
  errorTargetTab(): string | undefined
}

/** 契约目标约定快照（角色 `r1`；含挂接缺失菜单）。 */
const PERMISSION_CONTRACT_SNAPSHOT: PermissionContractSnapshot = {
  roleId: 'r1',
  nodes: [
    {
      key: 'menu:user',
      label: '用户管理',
      type: 'menu',
      children: [
        {
          key: 'form:user',
          label: '用户表单',
          type: 'form',
          children: [
            { key: 'biz:user', label: '用户业务', type: 'business' },
            { key: 'act:user:create', label: '新增用户', type: 'action' },
          ],
        },
      ],
    },
    { key: 'menu:orphan', label: '未挂接菜单', type: 'menu', detached: true },
  ],
  fieldPerms: [
    {
      formKey: 'form:user',
      formLabel: '用户表单',
      fields: [
        { key: 'name', label: '姓名' },
        { key: 'salary', label: '薪资' },
      ],
    },
  ],
  dataScopes: [{ actionKey: 'act:user:list', actionLabel: '查询' }],
  subjects: [],
}

/**
 * 授权编排契约（`BasePermissionConfig` / `useBasePermissionConfig` 投影；`08-4-1` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：角色 `r1`；权限树含菜单 `menu:user`（表单 `form:user` → 业务 `biz:user`，动作 `act:user:create` 默认无）
 * 与挂接缺失菜单 `menu:orphan`；字段矩阵含表单 `form:user` 的字段 `name` / `salary`；
 * 数据范围含动作 `act:user:list`（表达式初始为空）；主体初始为空、单主体上限取缺省 20；初始未注入处理函数。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describePermissionConfigContract(name: string, create: () => PermissionConfigContractTarget): void {
  /** 构造「已就绪且已装载」的目标。 */
  const readyTarget = async (
    snapshot: PermissionContractSnapshot = PERMISSION_CONTRACT_SNAPSHOT,
  ): Promise<PermissionConfigContractTarget> => {
    const target = create()
    target.setHandlers({ load: async () => snapshot })
    target.setReady(true)
    await target.load()
    return target
  }

  describeContract(name, () => {
    it('未就绪时降级且禁用，不产生请求', async () => {
      const target = create()
      target.setHandlers({ load: async () => PERMISSION_CONTRACT_SNAPSHOT })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.disabled).toBe(true)
      await target.load()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入处理函数时仍不产生请求、不再降级', async () => {
      const target = create()
      target.setReady(true)
      expect(target.degraded).toBe(false)
      expect(target.disabled).toBe(false)
      await target.load()
      expect(target.requestCount).toBe(0)
    })

    it('就绪且注入取数后装载快照（初始不脏）', async () => {
      const target = await readyTarget()
      expect(target.requestCount).toBe(1)
      expect(target.dirty).toBe(false)
      expect(target.granted()).toEqual({ menus: [], forms: [], actions: [], implied: [] })
    })

    it('隐含推导：勾选菜单隐含表单与业务，业务只读', async () => {
      const target = await readyTarget()
      expect(target.toggleNode('menu:user')).toBe(true)
      expect(target.granted()).toEqual({
        menus: ['menu:user'],
        forms: ['form:user'],
        actions: [],
        implied: ['biz:user'],
      })
      expect(target.toggleNode('biz:user')).toBe(false)
      expect(target.granted().implied).toEqual(['biz:user'])
    })

    it('动作默认全无：菜单勾选不联动动作，动作须显式勾选', async () => {
      const target = await readyTarget()
      target.toggleNode('menu:user')
      expect(target.granted().actions).toEqual([])
      expect(target.toggleNode('act:user:create')).toBe(true)
      expect(target.granted().actions).toEqual(['act:user:create'])
    })

    it('取消菜单连带取消表单与动作；挂接缺失不可授予', async () => {
      const target = await readyTarget()
      target.toggleNode('menu:user')
      target.toggleNode('act:user:create')
      expect(target.toggleNode('menu:orphan')).toBe(false)
      expect(target.checkState('menu:orphan')).toBe('unchecked')

      expect(target.toggleNode('menu:user', false)).toBe(true)
      expect(target.granted()).toEqual({ menus: [], forms: [], actions: [], implied: [] })
      expect(target.checkState('form:user')).toBe('unchecked')
    })

    it('三态：直接勾选子级时父级半选，全勾则已选', async () => {
      const target = await readyTarget()
      target.toggleNode('form:user')
      expect(target.checkState('form:user')).toBe('checked')
      expect(target.checkState('menu:user')).toBe('indeterminate')

      target.toggleNode('menu:user')
      expect(target.checkState('menu:user')).toBe('checked')
    })

    it('字段权限：默认全开、只提交收窄项、字段不存在不动作', async () => {
      const target = await readyTarget()
      expect(target.fieldPerm('form:user', 'name')).toEqual({ visible: true, editable: true })
      expect(target.payload().fields).toEqual([])

      expect(target.setFieldPerm('form:user', 'name', { visible: false })).toBe(true)
      expect(target.fieldPerm('form:user', 'name')).toEqual({ visible: false, editable: true })
      expect(target.payload().fields).toEqual([
        { formKey: 'form:user', fieldKey: 'name', visible: false, editable: true },
      ])
      expect(target.setFieldPerm('form:user', 'absent', { visible: false })).toBe(false)
    })

    it('数据范围：默认无、仅非空表达式入载荷', async () => {
      const target = await readyTarget()
      expect(target.scopeExpression('act:user:list')).toBe('')
      expect(target.payload().dataScopes).toEqual([])

      expect(target.setDataScope('act:user:list', 'dept_id = @current_dept')).toBe(true)
      expect(target.payload().dataScopes).toEqual([
        { actionKey: 'act:user:list', expression: 'dept_id = @current_dept' },
      ])
      expect(target.setDataScope('act:absent', 'x = 1')).toBe(false)

      target.setDataScope('act:user:list', '   ')
      expect(target.payload().dataScopes).toEqual([])
    })

    it('主体绑定：重复绑定幂等、超上限不写入', async () => {
      const target = await readyTarget()
      expect(target.bindSubject({ id: 'u1', type: 'user', name: '张三' })).toBe(true)
      expect(target.bindSubject({ id: 'u1', type: 'user', name: '张三' })).toBe(false)
      expect(target.subjectIds()).toEqual(['u1'])

      for (let index = 2; index <= 20; index += 1) {
        expect(target.bindSubject({ id: `u${index}`, type: 'user', name: `用户${index}` })).toBe(true)
      }
      expect(target.subjectIds()).toHaveLength(20)
      expect(target.bindSubject({ id: 'u21', type: 'user', name: '用户21' })).toBe(false)
      expect(target.subjectIds()).toHaveLength(20)
    })

    it('脏基线与撤销：变更置脏，撤销回滚且不再脏', async () => {
      const target = await readyTarget()
      expect(target.dirty).toBe(false)

      target.toggleNode('menu:user')
      expect(target.dirty).toBe(true)
      target.discard()
      expect(target.dirty).toBe(false)
      expect(target.granted().menus).toEqual([])
    })

    it('幂等键：同内容同键、重复提交结果一致、内容变更换键', async () => {
      const target = await readyTarget()
      const keys: string[] = []
      target.setHandlers({
        submit: async (input) => {
          keys.push(input.idempotencyKey)
          return { recordVersion: keys.length }
        },
      })
      target.toggleNode('menu:user')

      await expect(target.save()).resolves.toEqual({ recordVersion: 1 })
      await expect(target.save()).resolves.toEqual({ recordVersion: 2 })
      expect(keys).toHaveLength(2)
      expect(keys[0]).toBe(keys[1])

      target.toggleNode('act:user:create')
      expect(target.idempotencyKey()).not.toBe(keys[1])
    })

    it('提交阶段推进与权限上下文刷新（注入取码）', async () => {
      const target = await readyTarget()
      target.setAccess(['role:grant'])
      target.setHandlers({
        submit: async () => ({ recordVersion: 7 }),
        loadPermissionCodes: async () => ['role:grant', 'user:create'],
      })
      target.toggleNode('menu:user')
      expect(target.canSave).toBe(true)

      await expect(target.save()).resolves.toEqual({ recordVersion: 7 })
      expect(target.phase).toBe('done')
      expect(target.pendingAccessRefresh).toBe(false)
      expect([...target.accessCodes]).toContain('user:create')
    })

    it('未注入取码处理时不发请求，仅置待刷新标记', async () => {
      const target = await readyTarget()
      target.setAccess(['role:grant'])
      target.setHandlers({ submit: async () => ({ recordVersion: 1 }) })
      const before = target.requestCount
      target.toggleNode('menu:user')

      await target.save()
      expect(target.phase).toBe('done')
      expect(target.pendingAccessRefresh).toBe(true)
      expect(target.requestCount).toBe(before + 1)
    })

    it('未注入提交处理时不请求，且保留本地变更', async () => {
      const target = await readyTarget()
      const before = target.requestCount
      target.toggleNode('menu:user')

      await expect(target.save()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)
      expect(target.dirty).toBe(true)
    })

    it('提交失败保留本地并按错误码定位页签，重试恢复', async () => {
      const target = await readyTarget()
      let fail = true
      target.setHandlers({
        submit: async () => {
          if (fail) {
            throw Object.assign(new Error('规则表达式非法'), { code: 30047 })
          }
          return { recordVersion: 2 }
        },
      })
      target.toggleNode('menu:user')

      await expect(target.save()).resolves.toBeUndefined()
      expect(target.phase).toBe('failed')
      expect(target.errorTargetTab()).toBe('scope')
      expect(target.dirty).toBe(true)

      fail = false
      await expect(target.retry()).resolves.toEqual({ recordVersion: 2 })
      expect(target.phase).toBe('done')
      expect(target.dirty).toBe(false)
    })

    it('进行中重复提交不动作（防重复提交）', async () => {
      const target = await readyTarget()
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      let calls = 0
      target.setHandlers({
        submit: async () => {
          calls += 1
          await gate
          return { recordVersion: 3 }
        },
      })
      target.toggleNode('menu:user')

      const pending = target.save()
      expect(target.phase).toBe('saving')
      await expect(target.save()).resolves.toBeUndefined()
      release()
      await expect(pending).resolves.toEqual({ recordVersion: 3 })
      expect(calls).toBe(1)
    })

    it('无权（缺写权限码）不可保存且不可编辑', async () => {
      const target = await readyTarget()
      target.setAccess([])
      expect(target.canSave).toBe(false)
      expect(target.toggleNode('menu:user')).toBe(false)
      expect(target.setFieldPerm('form:user', 'name', { visible: false })).toBe(false)

      target.setAccess(['role:grant'])
      expect(target.canSave).toBe(true)
      expect(target.toggleNode('menu:user')).toBe(true)
    })
  })
}

/** 导入流契约结果装载输入（后端可省略字段）。 */
export interface ImportContractResultInput {
  /** 总行数。 */
  total?: number
  /** 成功行数。 */
  successCount?: number
  /** 失败行数。 */
  failCount?: number
  /** 错误行。 */
  errors?: readonly { row?: number; column?: string; message?: string }[]
}

/** 导入流契约结果（归一后）。 */
export interface ImportContractResult {
  /** 总行数。 */
  total: number
  /** 成功行数。 */
  successCount: number
  /** 失败行数。 */
  failCount: number
  /** 错误行。 */
  errors: readonly { row: number; column?: string; message: string }[]
}

/** 导入流契约执行处理函数。 */
export type ImportContractExecute = (input: {
  /** 业务标识。 */
  biz: string
  /** 文件对象。 */
  file: unknown
  /** 幂等键。 */
  idempotencyKey: string
  /** 上传进度回传。 */
  report: (percent: number) => void
  /** 中断信号。 */
  signal: { readonly aborted: boolean }
}) => Promise<ImportContractResultInput | undefined>

/** 导入流契约下载处理函数（取址）。 */
export type ImportContractDownload = (input: {
  /** 业务标识。 */
  biz: string
  /** 用途。 */
  kind: 'template' | 'errors'
  /** 请求文件名。 */
  filename: string
  /** 幂等键（错误明细用）。 */
  idempotencyKey?: string
}) => Promise<{ url?: string; filename?: string } | undefined>

/** 导入流契约注入面。 */
export interface ImportContractJobs {
  /** 执行导入。 */
  execute?: ImportContractExecute
  /** 模板下载取址。 */
  downloadTemplate?: ImportContractDownload
  /** 错误明细下载取址。 */
  downloadErrors?: ImportContractDownload
}

/** 导入流契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface ImportFlowContractTarget {
  /** 是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 是否进行中。 */
  readonly busy: boolean
  /** 请求计数（占位期恒 0）。 */
  readonly requestCount: number
  /** 阶段。 */
  readonly phase: string
  /** 步骤。 */
  readonly step: string
  /** 进度（0 ~ 100）。 */
  readonly progress: number
  /** 幂等键。 */
  readonly idempotencyKey: string
  /** 文件校验失败文案。 */
  readonly fileError: string
  /** 结果汇总态。 */
  readonly summary: string
  /** 错误行总页数。 */
  readonly errorPageCount: number
  /** 当前页错误行。 */
  readonly errorRows: readonly { row: number; column?: string; message: string }[]
  /** 是否触发展示上限截断。 */
  readonly errorTruncated: boolean
  /** 设置就绪态。 */
  setReady(value: boolean): void
  /** 设置业务标识与中文名。 */
  setBiz(biz: string, bizName?: string): void
  /** 注入处理函数集。 */
  setJobs(jobs: ImportContractJobs): void
  /** 注入下载触发（实现侧可传下载基类实例；套件不解释其内部）。 */
  setDownload(download: unknown): void
  /** 选择文件并校验。 */
  selectFile(file: unknown, meta: { name: string; size: number; lastModified?: number }): boolean
  /** 清空文件与幂等键。 */
  clearFile(): void
  /** 切换错误行页码。 */
  setErrorPage(page: number): void
  /** 提交导入。 */
  submit(): Promise<unknown>
  /** 重试失败导入。 */
  retry(): Promise<unknown>
  /** 重新导入（整体重置）。 */
  reset(): void
  /** 取消导入。 */
  cancel(): void
  /** 下载模板。 */
  downloadTemplate(): Promise<unknown>
  /** 下载错误明细。 */
  downloadErrors(): Promise<unknown>
  /** 当前结果。 */
  result(): ImportContractResult | undefined
}

/**
 * 导入流契约（`BaseImportFlow` / `useBaseImportFlow` 投影；`08-5-1` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：业务 `users` / 中文名「用户」；文件 `users.xlsx`（1KB）；执行处理函数返回部分失败结果；
 * 「未注入执行处理」与「未就绪」两条占位路径均要求零请求。实现侧不得改动对外形状。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeImportFlowContract(name: string, create: () => ImportFlowContractTarget): void {
  /** 契约文件元信息。 */
  const meta = { name: 'users.xlsx', size: 1024, lastModified: 1_700_000_000_000 }
  /** 契约文件对象（透传用）。 */
  const file = { kind: 'file', name: 'users.xlsx' }
  /** 部分失败结果。 */
  const partial: ImportContractResultInput = {
    total: 100,
    successCount: 98,
    failCount: 2,
    errors: [
      { row: 3, column: 'email', message: '邮箱格式非法' },
      { row: 7, message: '唯一性冲突' },
    ],
  }

  /** 构造已就绪且已选文件的目标。 */
  const readyTarget = (jobs: ImportContractJobs): ImportFlowContractTarget => {
    const target = create()
    target.setBiz('users', '用户')
    target.setJobs(jobs)
    target.setReady(true)
    target.selectFile(file, meta)
    return target
  }

  describeContract(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      target.setBiz('users', '用户')
      target.setJobs({ execute: async () => partial })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      target.selectFile(file, meta)
      await expect(target.submit()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入执行处理时不产生请求（占位）', async () => {
      const target = readyTarget({})
      await expect(target.submit()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('文件校验：类型 / 大小 / 空文件不通过且不生成幂等键', () => {
      const target = create()
      target.setBiz('users', '用户')
      target.setReady(true)
      expect(target.selectFile(file, { name: 'users.txt', size: 10 })).toBe(false)
      expect(target.fileError).toContain('.xlsx')
      expect(target.selectFile(file, { name: 'users.xlsx', size: 30 * 1024 * 1024 })).toBe(false)
      expect(target.fileError).toContain('MB')
      expect(target.selectFile(file, { name: 'users.xlsx', size: 0 })).toBe(false)
      expect(target.fileError).toContain('空')
      expect(target.idempotencyKey).toBe('')
    })

    it('幂等键为内容派生：同文件同键、换文件换键、清空重置', () => {
      const target = create()
      target.setBiz('users', '用户')
      target.setReady(true)
      expect(target.selectFile(file, meta)).toBe(true)
      const first = target.idempotencyKey
      expect(first).not.toBe('')
      expect(target.selectFile(file, meta)).toBe(true)
      expect(target.idempotencyKey).toBe(first)
      target.selectFile(file, { ...meta, size: meta.size + 1 })
      expect(target.idempotencyKey).not.toBe(first)
      target.clearFile()
      expect(target.idempotencyKey).toBe('')
    })

    it('提交：阶段推进、进度透出、结果归一与汇总态', async () => {
      const target = readyTarget({
        execute: async ({ idempotencyKey, report }) => {
          expect(idempotencyKey).toBe(target.idempotencyKey)
          report(30)
          report(100)
          return partial
        },
      })
      await expect(target.submit()).resolves.toEqual(partial)
      expect(target.requestCount).toBe(1)
      expect(target.phase).toBe('done')
      expect(target.step).toBe('result')
      expect(target.progress).toBe(100)
      expect(target.summary).toBe('warning')
      expect(target.result()).toEqual(partial)
      expect(target.errorRows).toHaveLength(2)
      expect(target.errorPageCount).toBe(1)
    })

    it('汇总态：全部成功与无数据', async () => {
      const ok = readyTarget({ execute: async () => ({ total: 3, successCount: 3, failCount: 0 }) })
      await ok.submit()
      expect(ok.summary).toBe('success')

      const empty = readyTarget({ execute: async () => undefined })
      await empty.submit()
      expect(empty.summary).toBe('empty')
      expect(empty.result()).toEqual({ total: 0, successCount: 0, failCount: 0, errors: [] })
    })

    it('错误行分页与展示上限截断标记', async () => {
      const target = readyTarget({
        execute: async () => ({
          total: 1500,
          successCount: 400,
          failCount: 1100,
          errors: Array.from({ length: 1100 }, (_, index) => ({ row: index + 2, message: '格式非法' })),
        }),
      })
      await target.submit()
      expect(target.errorTruncated).toBe(true)
      expect(target.errorPageCount).toBe(50)
      expect(target.errorRows).toHaveLength(20)
      target.setErrorPage(2)
      expect(target.errorRows[0]?.row).toBe(22)
    })

    it('执行失败：阶段置失败、不展示错误行、重试复用同一幂等键', async () => {
      const keys: string[] = []
      let attempt = 0
      const target = readyTarget({
        execute: async ({ idempotencyKey }) => {
          keys.push(idempotencyKey)
          attempt += 1
          if (attempt === 1) {
            throw new Error('文件解析失败')
          }
          return { total: 1, successCount: 1, failCount: 0 }
        },
      })
      await expect(target.submit()).resolves.toBeUndefined()
      expect(target.phase).toBe('failed')
      expect(target.errorRows).toHaveLength(0)
      await expect(target.retry()).resolves.toEqual({ total: 1, successCount: 1, failCount: 0, errors: [] })
      expect(keys).toHaveLength(2)
      expect(keys[0]).toBe(keys[1])
      expect(target.phase).toBe('done')
    })

    it('进行中重复提交不动作', async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const target = readyTarget({
        execute: async () => {
          await gate
          return { total: 1, successCount: 1, failCount: 0 }
        },
      })
      const pending = target.submit()
      expect(target.busy).toBe(true)
      await expect(target.submit()).resolves.toBeUndefined()
      release()
      await expect(pending).resolves.toEqual({ total: 1, successCount: 1, failCount: 0, errors: [] })
      expect(target.requestCount).toBe(1)
    })

    it('取消：中断在途执行并复位阶段与进度', async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const target = readyTarget({
        execute: async () => {
          await gate
          return { total: 1, successCount: 1, failCount: 0 }
        },
      })
      const pending = target.submit()
      target.cancel()
      release()
      await expect(pending).resolves.toBeUndefined()
      expect(target.phase).toBe('idle')
      expect(target.progress).toBe(0)
      expect(target.result()).toBeUndefined()
    })

    it('模板与错误明细下载：注入取址后返回结果，未注入则不动作', async () => {
      const target = readyTarget({})
      await expect(target.downloadTemplate()).resolves.toBeUndefined()

      const calls: string[] = []
      target.setJobs({
        downloadTemplate: async ({ kind, filename }) => {
          calls.push(`${kind}:${filename}`)
          return { url: 'https://example.test/template.xlsx' }
        },
        downloadErrors: async ({ kind, filename, idempotencyKey }) => {
          calls.push(`${kind}:${filename}:${idempotencyKey}`)
          return { url: 'https://example.test/errors.xlsx' }
        },
      })
      await expect(target.downloadTemplate()).resolves.toEqual({
        url: 'https://example.test/template.xlsx',
        filename: '用户-导入模板.xlsx',
      })
      await expect(target.downloadErrors()).resolves.toBeDefined()
      expect(calls[0]).toBe('template:用户-导入模板.xlsx')
      expect(calls[1]?.startsWith('errors:用户-导入错误明细-')).toBe(true)
      expect(calls[1]?.endsWith(`:${target.idempotencyKey}`)).toBe(true)
    })
  })
}

/** 导出流契约结果。 */
export interface ExportContractResult {
  /** 文件标识。 */
  fileId?: string
  /** 文件名。 */
  fileName?: string
  /** 下载地址。 */
  url?: string
  /** 一次性令牌。 */
  token?: string
  /** 是否转后台任务。 */
  async?: boolean
  /** 提示文案。 */
  message?: string
}

/** 导出流契约导出处理函数。 */
export type ExportContractHandler = (input: {
  /** 业务标识。 */
  biz: string
  /** 导出范围。 */
  scope: string
  /** 取数参数。 */
  params?: Record<string, unknown>
  /** 选中行标识。 */
  selectedIds?: readonly string[]
  /** 是否明文导出。 */
  plain: boolean
  /** 文件名。 */
  filename: string
  /** 中断信号。 */
  signal: { readonly aborted: boolean }
  /** 进度回传。 */
  report: (progress: { value: number; total?: number }) => void
}) => Promise<ExportContractResult | undefined>

/** 导出流契约轮询处理函数。 */
export type ExportContractPoll = (
  handle: unknown,
  attempt: number,
) => Promise<{ done: boolean; progress?: { value: number; total?: number }; result?: ExportContractResult }>

/** 导出流契约注入面。 */
export interface ExportContractJobs {
  /** 导出执行。 */
  export?: ExportContractHandler
  /** 后台任务轮询。 */
  poll?: ExportContractPoll
}

/** 导出流契约面（结构化；实现侧可用基类实例或投影适配器接入）。 */
export interface ExportFlowContractTarget {
  /** 是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 是否进行中。 */
  readonly busy: boolean
  /** 请求计数（占位期恒 0）。 */
  readonly requestCount: number
  /** 阶段。 */
  readonly phase: string
  /** 进度。 */
  readonly progress: { value: number; total?: number }
  /** 是否可导出。 */
  readonly canExport: boolean
  /** 是否走后台异步通路。 */
  readonly asyncMode: boolean
  /** 当前筛选是否无数据。 */
  readonly empty: boolean
  /** 导出处理函数是否已注入。 */
  readonly exportReady: boolean
  /** 导出载荷。 */
  plan(): {
    biz: string
    scope: string
    params?: Record<string, unknown>
    selectedIds?: string[]
    plain: boolean
    filename: string
  }
  /** 设置就绪态。 */
  setReady(value: boolean): void
  /** 设置业务标识与中文名。 */
  setBiz(biz: string, bizName?: string): void
  /** 设置取数参数。 */
  setParams(params?: Record<string, unknown>): void
  /** 设置导出范围与选中行。 */
  setScope(scope: string, selectedIds?: readonly (string | number)[]): void
  /** 设置当前筛选总条数。 */
  setTotal(total: number): void
  /** 设置是否申请明文导出。 */
  setPlain(plain: boolean): void
  /** 设置异步阈值。 */
  setThreshold(threshold: number): void
  /** 设置外部禁用。 */
  setDisabled(disabled: boolean): void
  /** 注入权限码集合（`undefined` 表示不注入权限上下文）。 */
  setAccess(codes?: readonly string[]): void
  /** 注入处理函数集。 */
  setJobs(jobs: ExportContractJobs): void
  /** 注入异步任务（实现侧应提供 `pollInterval` 尽可能小的实例以免测试等待）。 */
  newTask(): unknown
  /** 注入异步任务实例。 */
  setTask(task: unknown): void
  /** 注入下载触发（实现侧可传下载基类实例；套件不解释其内部）。 */
  setDownload(download: unknown): void
  /** 最近一次结果。 */
  lastResult(): ExportContractResult | undefined
  /** 触发导出。 */
  export(): Promise<unknown>
  /** 重试失败导出。 */
  retry(): Promise<unknown>
  /** 取消导出。 */
  cancel(): void
  /** 复位编排状态。 */
  reset(): void
}

/**
 * 导出流契约（`BaseExportFlow` / `useBaseExportFlow` 投影；`08-5-1` 首次落地，后续移动端复用同一套断言）。
 *
 * 目标约定：业务 `users` / 中文名「用户」；默认取数参数 `{ keyword: 'a' }`、总条数 10、阈值 0（同步）；
 * 异步目标总条数 1000 / 阈值 500（经 `newTask()` 提供任务实例、`poll` 两轮完成）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeExportFlowContract(name: string, create: () => ExportFlowContractTarget): void {
  /** 构造已就绪目标。 */
  const readyTarget = (
    jobs: ExportContractJobs,
    input: { total?: number; threshold?: number } = {},
  ): ExportFlowContractTarget => {
    const target = create()
    target.setBiz('users', '用户')
    target.setTotal(input.total ?? 10)
    target.setThreshold(input.threshold ?? 0)
    target.setParams({ keyword: 'a' })
    target.setJobs(jobs)
    target.setReady(true)
    return target
  }

  describeContract(name, () => {
    it('未就绪时降级且不产生请求', async () => {
      const target = create()
      target.setBiz('users', '用户')
      target.setTotal(10)
      target.setJobs({ export: async () => ({ url: 'https://example.test/1.xlsx' }) })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      await expect(target.export()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入导出处理时不产生请求（占位）', async () => {
      const target = readyTarget({})
      expect(target.exportReady).toBe(false)
      await expect(target.export()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(0)
    })

    it('决策：无数据 / 选中未选 / 无权 / 外部禁用 各自不动作', async () => {
      const jobs: ExportContractJobs = { export: async () => ({ url: 'https://example.test/1.xlsx' }) }

      const empty = readyTarget(jobs, { total: 0 })
      expect(empty.empty).toBe(true)
      expect(empty.canExport).toBe(false)
      await expect(empty.export()).resolves.toBeUndefined()

      const selected = readyTarget(jobs)
      selected.setScope('selected', [])
      expect(selected.canExport).toBe(false)
      await expect(selected.export()).resolves.toBeUndefined()

      const denied = readyTarget(jobs)
      denied.setAccess([])
      expect(denied.canExport).toBe(false)
      await expect(denied.export()).resolves.toBeUndefined()

      const disabled = readyTarget(jobs)
      disabled.setDisabled(true)
      expect(disabled.canExport).toBe(false)
      await expect(disabled.export()).resolves.toBeUndefined()

      expect(empty.requestCount + selected.requestCount + denied.requestCount + disabled.requestCount).toBe(0)
    })

    it('载荷：取数参数归一、选中去重排序、明文按权限收窄', () => {
      const target = readyTarget({})
      target.setParams({ keyword: 'a', empty: '', list: [], keep: 1 })
      target.setScope('selected', ['2', 1, '2'])
      target.setPlain(true)
      expect(target.plan().params).toEqual({ keyword: 'a', keep: 1 })
      expect(target.plan().selectedIds).toEqual(['1', '2'])
      expect(target.plan().plain).toBe(false)
      expect(target.plan().filename.endsWith('.xlsx')).toBe(true)
      expect(target.asyncMode).toBe(false)

      target.setAccess(['data:plain'])
      expect(target.plan().plain).toBe(true)
    })

    it('同步导出：阶段推进、结果与下载触发', async () => {
      const downloads: string[] = []
      const target = readyTarget({
        export: async ({ report }) => {
          report({ value: 1, total: 10 })
          return { url: 'https://example.test/export.xlsx', fileName: 'users.xlsx' }
        },
      })
      target.setDownload({
        download: async (input: { url?: string; filename?: string }) => {
          downloads.push(input.filename ?? '')
          return { url: input.url ?? '', filename: input.filename ?? '' }
        },
      })
      await expect(target.export()).resolves.toMatchObject({ url: 'https://example.test/export.xlsx' })
      expect(target.phase).toBe('done')
      expect(target.requestCount).toBe(1)
      expect(target.lastResult()?.url).toBe('https://example.test/export.xlsx')
      expect(downloads).toEqual(['users.xlsx'])
    })

    it('超阈值异步：经两段轮询推进进度并结算结果', async () => {
      const attempts: number[] = []
      const target = readyTarget(
        {
          export: async () => ({ fileId: 'task-1' }),
          poll: async (_handle, attempt) => {
            attempts.push(attempt)
            return attempt < 2
              ? { done: false, progress: { value: attempt, total: 2 } }
              : {
                  done: true,
                  progress: { value: 2, total: 2 },
                  result: { fileId: 'file-1', fileName: 'users.xlsx', url: 'https://example.test/1.xlsx' },
                }
          },
        },
        { total: 1000, threshold: 500 },
      )
      target.setTask(target.newTask())
      expect(target.asyncMode).toBe(true)
      await expect(target.export()).resolves.toMatchObject({ fileId: 'file-1' })
      expect(attempts).toEqual([1, 2])
      expect(target.phase).toBe('done')
      expect(target.progress).toMatchObject({ value: 2, total: 2 })
    })

    it('异步阈值但轮询未注入：回落单次调用并按已转后台标记', async () => {
      const target = readyTarget({ export: async () => ({ fileId: 'task-1' }) }, { total: 1000, threshold: 500 })
      target.setTask(target.newTask())
      await expect(target.export()).resolves.toMatchObject({ async: true, fileId: 'task-1' })
      expect(target.phase).toBe('done')
    })

    it('失败可重试（同参数重放）', async () => {
      let attempt = 0
      const target = readyTarget({
        export: async () => {
          attempt += 1
          if (attempt === 1) {
            throw new Error('导出失败')
          }
          return { url: 'https://example.test/1.xlsx' }
        },
      })
      await expect(target.export()).resolves.toBeUndefined()
      expect(target.phase).toBe('failed')
      await expect(target.retry()).resolves.toMatchObject({ url: 'https://example.test/1.xlsx' })
      expect(target.phase).toBe('done')
      expect(target.requestCount).toBe(2)
    })

    it('进行中重复提交不动作', async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const target = readyTarget({
        export: async () => {
          await gate
          return { url: 'https://example.test/1.xlsx' }
        },
      })
      const pending = target.export()
      expect(target.busy).toBe(true)
      await expect(target.export()).resolves.toBeUndefined()
      release()
      await pending
      expect(target.requestCount).toBe(1)
    })

    it('取消：中断在途导出并复位阶段', async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      const target = readyTarget({
        export: async () => {
          await gate
          return { url: 'https://example.test/1.xlsx' }
        },
      })
      const pending = target.export()
      target.cancel()
      release()
      await expect(pending).resolves.toBeUndefined()
      expect(target.phase).toBe('idle')
      expect(target.requestCount).toBe(1)
    })
  })
}
