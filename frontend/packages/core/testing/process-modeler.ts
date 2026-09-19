/**
 * 流程建模器编排契约（`@bms/core/testing`）。
 *
 * 建模器为「同一契约多实现」（PC `ui-ep` 为首个实现；移动端不提供建模，但仍保留端中立口径），
 * 各自在本套件中传入适配器跑同一套断言。契约面为**结构化接口**（非具体基类）。
 */

import { describe, expect, it } from 'vitest'

/** 契约目标：定义（最小面）。 */
export interface ModelerContractDefinition {
  /** 定义标识。 */
  definitionKey?: string
  /** 定义名称。 */
  name?: string
  /** 版本号。 */
  version?: number
  /** BPMN XML。 */
  xml?: string
  /** 定义状态。 */
  status?: 'draft' | 'published'
}

/** 校验结果（最小面）。 */
export interface ModelerContractValidation {
  /** 是否合法。 */
  valid: boolean
  /** 结论来源。 */
  source: string
  /** 错误清单。 */
  errors: { elementId?: string; message: string }[]
}

/** 契约处理函数集（结构化最小面；未注入的项按占位）。 */
export interface ModelerContractHandlers {
  /** 取定义。 */
  loadDefinition?: (input: { definitionKey: string; version?: number }) => Promise<ModelerContractDefinition | undefined>
  /** 保存草稿。 */
  saveDraft?: (input: { definitionKey: string; version: number; idempotencyKey: string }) => Promise<{ version?: number } | undefined>
  /** 发布版本。 */
  deploy?: (input: { definitionKey: string; version: number; idempotencyKey: string }) => Promise<{ version?: number } | undefined>
  /** 引擎预解析。 */
  validate?: (input: { xml: string }) => Promise<ModelerContractValidation | undefined>
}

/** 契约面：流程建模器编排。 */
export interface ProcessModelerContractTarget {
  /** 数据通路是否就绪。 */
  readonly ready: boolean
  /** 是否降级（占位）态。 */
  readonly degraded: boolean
  /** 是否禁用（占位态强制禁用）。 */
  readonly disabled: boolean
  /** 是否只读。 */
  readonly readOnlyState: boolean
  /** 请求计数（占位期恒 0）。 */
  readonly requestCount: number
  /** 当前阶段。 */
  readonly phase: string
  /** 定义标识。 */
  readonly definitionKey: string
  /** 版本号。 */
  readonly version: number
  /** 是否有未保存变更。 */
  readonly dirty: boolean
  /** 是否可编辑。 */
  readonly canEdit: boolean
  /** 当前 XML。 */
  xml(): string
  /** 当前结构（元素 / 顺序流标识）。 */
  structure(): { elements: string[]; flows: string[] }
  /** 选中元素标识。 */
  selectedId(): string
  /** 校验结论来源。 */
  validateSource(): string | undefined
  /** 校验错误元素标识清单。 */
  errorElementIds(): string[]
  /** 错误码定位元素标识。 */
  errorTargetElement(): string | undefined
  /** 切换就绪态。 */
  setReady(value: boolean): void
  /** 切换只读。 */
  setReadOnly(value: boolean): void
  /** 注入权限码集合（`undefined` 表示不注入权限上下文）。 */
  setAccess(codes: readonly string[] | undefined): void
  /** 注入处理函数集。 */
  setHandlers(handlers: ModelerContractHandlers): void
  /** 装载定义。 */
  applyDefinition(input?: ModelerContractDefinition): void
  /** 取定义。 */
  load(definitionKey?: string, version?: number): Promise<boolean>
  /** 更新 XML。 */
  updateXml(xml: string): void
  /** 导入 XML（结构校验通过才生效）。 */
  importXml(xml: string): boolean
  /** 请求导入（待确认）。 */
  requestImport(xml: string): boolean
  /** 确认导入。 */
  confirmImport(): boolean
  /** 取消导入。 */
  cancelImport(): void
  /** 导出 XML。 */
  exportXml(): string
  /** 选中元素。 */
  select(elementId?: string): { id: string; type: string } | undefined
  /** 校验。 */
  validate(options?: { engine?: boolean }): Promise<ModelerContractValidation>
  /** 保存草稿。 */
  saveDraft(): Promise<unknown>
  /** 发布版本。 */
  deploy(): Promise<unknown>
  /** 重试失败提交。 */
  retry(): Promise<unknown>
  /** 幂等键。 */
  idempotencyKey(kind: 'draft' | 'deploy'): string
  /** 撤销未保存变更。 */
  discard(): void
}

/** 契约目标约定：最小合法流程（开始 → 用户任务 → 结束）。 */
const VALID_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" name="发起" />',
  '    <bpmn:userTask id="t1" name="审批" />',
  '    <bpmn:endEvent id="e1" name="结束" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="t1" />',
  '    <bpmn:sequenceFlow id="f2" sourceRef="t1" targetRef="e1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/** 契约目标约定：缺结束事件的非法流程。 */
const INVALID_XML = [
  '<bpmn:definitions xmlns:bpmn="http://www.omg.org/spec/BPMN/20100524/MODEL">',
  '  <bpmn:process id="Process_1">',
  '    <bpmn:startEvent id="s1" />',
  '    <bpmn:userTask id="t1" />',
  '    <bpmn:sequenceFlow id="f1" sourceRef="s1" targetRef="t1" />',
  '  </bpmn:process>',
  '</bpmn:definitions>',
].join('\n')

/**
 * 流程建模器契约（`BaseProcessModeler` / `useBaseProcessModeler` 投影；`08-8-2` 首次落地）。
 *
 * 目标约定：定义 `leave`（`version = 2`，合法最小流程）；引擎预解析处理函数初始未注入；
 * 权限上下文含 `wf:define`。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeProcessModelerContract(name: string, create: () => ProcessModelerContractTarget): void {
  /** 构造「已就绪且已装载」的目标。 */
  const readyTarget = (handlers: ModelerContractHandlers = {}): ProcessModelerContractTarget => {
    const target = create()
    target.setHandlers(handlers)
    target.setReady(true)
    target.applyDefinition({ definitionKey: 'leave', name: '请假流程', version: 2, xml: VALID_XML })
    return target
  }

  describe(name, () => {
    it('未就绪时降级且禁用，不产生请求', async () => {
      const target = create()
      target.setHandlers({ loadDefinition: async () => ({ definitionKey: 'leave', xml: VALID_XML }) })
      expect(target.ready).toBe(false)
      expect(target.degraded).toBe(true)
      expect(target.disabled).toBe(true)
      await target.load('leave')
      expect(target.requestCount).toBe(0)
    })

    it('就绪但未注入处理函数时不产生请求、不再降级', async () => {
      const target = create()
      target.setReady(true)
      await target.load('leave')
      expect(target.requestCount).toBe(0)
      expect(target.degraded).toBe(false)
    })

    it('装载定义：XML 为空回落模板、初始不脏', () => {
      const target = create()
      target.setReady(true)
      target.applyDefinition({ definitionKey: 'x' })
      expect(target.xml()).not.toBe('')
      expect(target.dirty).toBe(false)
      expect(target.version).toBe(0)
    })

    it('取定义并装载（结构可读、基线不脏）', async () => {
      const target = create()
      target.setHandlers({ loadDefinition: async () => ({ definitionKey: 'leave', name: '请假流程', version: 2, xml: VALID_XML }) })
      target.setReady(true)
      await expect(target.load('leave')).resolves.toBe(true)
      expect(target.requestCount).toBe(1)
      expect(target.definitionKey).toBe('leave')
      expect(target.version).toBe(2)
      expect(target.dirty).toBe(false)
      expect(target.structure().elements).toEqual(['e1', 's1', 't1'])
      expect(target.structure().flows).toEqual(['f1', 'f2'])
    })

    it('updateXml 置脏，discard 回滚清脏', () => {
      const target = readyTarget()
      expect(target.dirty).toBe(false)
      target.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
      expect(target.dirty).toBe(true)
      target.discard()
      expect(target.dirty).toBe(false)
    })

    it('结构校验：缺结束事件等错误可定位', () => {
      const target = readyTarget()
      expect(target.importXml(INVALID_XML)).toBe(false)
      expect(target.xml()).toBe(VALID_XML)
      expect(target.errorElementIds()).toContain('t1')
    })

    it('导入覆盖两段式：请求后待确认，确认生效、取消保持原画布', () => {
      const target = readyTarget()
      target.setAccess(['wf:define'])
      const next = VALID_XML.replace('name="审批"', 'name="复核"')
      expect(target.requestImport(next)).toBe(true)
      target.cancelImport()
      expect(target.confirmImport()).toBe(false)
      expect(target.xml()).toBe(VALID_XML)

      expect(target.requestImport(next)).toBe(true)
      expect(target.confirmImport()).toBe(true)
      expect(target.xml()).toContain('复核')
    })

    it('XML 往返语义等价（导入后导出结构等价）', () => {
      const target = readyTarget()
      const reformatted = VALID_XML.replace(/\n\s*/g, '\n    ')
      expect(target.importXml(reformatted)).toBe(true)
      expect(target.structure()).toEqual({ elements: ['e1', 's1', 't1'], flows: ['f1', 'f2'] })
    })

    it('校验合并：引擎段未注入时来源为 structure，注入后为 engine', async () => {
      const structureOnly = readyTarget()
      await structureOnly.validate()
      expect(structureOnly.validateSource()).toBe('structure')

      const withEngine = readyTarget({
        validate: async () => ({ valid: true, source: 'engine', errors: [] }),
      })
      await withEngine.validate()
      expect(withEngine.validateSource()).toBe('engine')
      expect(withEngine.errorElementIds()).toEqual([])

      const engineFail = readyTarget({
        validate: async () => ({ valid: false, source: 'engine', errors: [{ elementId: 't1', message: '引擎不可解析' }] }),
      })
      await engineFail.validate()
      expect(engineFail.validateSource()).toBe('engine')
      expect(engineFail.errorElementIds()).toContain('t1')
    })

    it('select 命中与清空', () => {
      const target = readyTarget()
      expect(target.select('t1')).toEqual({ id: 't1', type: 'userTask' })
      expect(target.selectedId()).toBe('t1')
      expect(target.select(undefined)).toBeUndefined()
      expect(target.selectedId()).toBe('')
    })

    it('保存草稿与发布：幂等键同内容同键、内容变更换键', async () => {
      const keys: string[] = []
      const target = readyTarget({
        saveDraft: async (input) => {
          keys.push(input.idempotencyKey)
          return { version: input.version }
        },
      })
      target.setAccess(['wf:define'])
      await target.saveDraft()
      await target.saveDraft()
      expect(keys).toHaveLength(2)
      expect(keys[0]).toBe(keys[1])

      target.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
      expect(target.idempotencyKey('draft')).not.toBe(keys[1])
    })

    it('发布成功推进版本并清脏', async () => {
      const target = readyTarget({ deploy: async () => ({ version: 3 }) })
      target.setAccess(['wf:define'])
      target.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
      expect(target.dirty).toBe(true)
      await target.deploy()
      expect(target.version).toBe(3)
      expect(target.dirty).toBe(false)
      expect(target.phase).toBe('done')
    })

    it('未注入保存处理时不请求且保留本地变更', async () => {
      const target = readyTarget({})
      target.setAccess(['wf:define'])
      target.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
      const before = target.requestCount
      await expect(target.saveDraft()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)
      expect(target.dirty).toBe(true)
    })

    it('校验不通过时保存与发布被阻断且不请求', async () => {
      const target = readyTarget({ saveDraft: async () => ({ version: 1 }), deploy: async () => ({ version: 3 }) })
      target.setAccess(['wf:define'])
      target.updateXml(INVALID_XML)
      const before = target.requestCount
      await expect(target.saveDraft()).resolves.toBeUndefined()
      await expect(target.deploy()).resolves.toBeUndefined()
      expect(target.requestCount).toBe(before)
    })

    it('只读态不可编辑 / 保存 / 发布，导出仍可用', async () => {
      const target = readyTarget({ saveDraft: async () => ({ version: 1 }) })
      target.setAccess(['wf:define'])
      target.setReadOnly(true)
      expect(target.canEdit).toBe(false)
      await expect(target.saveDraft()).resolves.toBeUndefined()
      expect(target.exportXml()).toBe(VALID_XML)
      expect(target.requestImport(VALID_XML)).toBe(false)
    })

    it('无权（缺 wf:define）不可编辑', () => {
      const target = readyTarget()
      target.setAccess([])
      expect(target.canEdit).toBe(false)
      target.setAccess(['wf:define'])
      expect(target.canEdit).toBe(true)
    })

    it('错误码 60006 定位元素 / 60007 定义级提示与重试', async () => {
      let attempt = 0
      const target = readyTarget({
        deploy: async () => {
          attempt += 1
          if (attempt === 1) {
            throw Object.assign(new Error('BPMN 非法'), { code: 60006, elementId: 't1' })
          }
          return { version: 3 }
        },
      })
      target.setAccess(['wf:define'])
      await target.deploy()
      expect(target.phase).toBe('failed')
      expect(target.errorTargetElement()).toBe('t1')
      await expect(target.retry()).resolves.toEqual({ version: 3 })
      expect(target.phase).toBe('done')
    })

    it('进行中重复提交不动作', async () => {
      let release: () => void = () => {}
      const gate = new Promise<void>((resolve) => {
        release = resolve
      })
      let calls = 0
      const target = readyTarget({
        saveDraft: async () => {
          calls += 1
          await gate
          return { version: 2 }
        },
      })
      target.setAccess(['wf:define'])
      const pending = target.saveDraft()
      await expect(target.saveDraft()).resolves.toBeUndefined()
      release()
      await pending
      expect(calls).toBe(1)
    })
  })
}
