/** 流程建模编排用例（`08-8-2`）：占位零请求 / 装载与脏基线 / 导入两段确认 / 校验合并 / 保存发布幂等与版本推进 / 只读与权限 / 错误码定位。 */

import { describe, expect, it } from 'vitest'

import { BaseAccess, BaseProcessModeler, MODELER_PLACEHOLDER_TEXT, type ModelerJobs } from '../src'

/** 具体流程建模编排件（可实例化）。 */
class ProcessModelerState extends BaseProcessModeler {}

/** 权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 合法最小流程。 */
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

/** 缺结束事件的非法流程。 */
const INVALID_XML = VALID_XML.replace('<bpmn:endEvent id="e1" name="结束" />', '').replace(
  '<bpmn:sequenceFlow id="f2" sourceRef="t1" targetRef="e1" />',
  '',
)

/** 构造「已就绪且已装载」的编排实例。 */
function readyModeler(jobs: ModelerJobs = {}): BaseProcessModeler {
  const modeler = new ProcessModelerState()
  modeler.setJobs(jobs)
  modeler.setReady(true)
  modeler.applyDefinition({ definitionKey: 'leave', name: '请假流程', version: 2, xml: VALID_XML })
  modeler.setAccess(new DemoAccess())
  modeler.access?.setCodes(['wf:define'])
  return modeler
}

describe('占位语义', () => {
  it('未就绪：降级且禁用，取数与提交零请求', async () => {
    const modeler = new ProcessModelerState()
    modeler.setJobs({
      loadDefinition: async () => ({ definitionKey: 'leave', xml: VALID_XML }),
      saveDraft: async () => ({ version: 1 }),
    })
    expect(modeler.degraded).toBe(true)
    expect(modeler.disabled).toBe(true)
    await modeler.load('leave')
    await modeler.saveDraft()
    expect(modeler.requestCount).toBe(0)
  })

  it('就绪但未注入处理函数：不请求、不再降级', async () => {
    const modeler = new ProcessModelerState()
    modeler.setReady(true)
    expect(modeler.degraded).toBe(false)
    modeler.applyDefinition({ definitionKey: 'leave', xml: VALID_XML })
    await modeler.load('leave')
    expect(modeler.requestCount).toBe(0)
    await expect(modeler.saveDraft()).resolves.toBeUndefined()
    expect(modeler.errorMessage).toBe(MODELER_PLACEHOLDER_TEXT)
  })
})

describe('装载与脏基线', () => {
  it('XML 为空回落空流程模板，初始不脏', () => {
    const modeler = new ProcessModelerState()
    modeler.setReady(true)
    modeler.applyDefinition({ definitionKey: 'x' })
    expect(modeler.xml).not.toBe('')
    expect(modeler.dirty).toBe(false)
    expect(modeler.structure.elements.length).toBeGreaterThan(0)
  })

  it('取定义装载并记基线', async () => {
    const modeler = new ProcessModelerState()
    modeler.setJobs({
      loadDefinition: async () => ({ definitionKey: 'leave', name: '请假流程', version: 2, xml: VALID_XML }),
    })
    modeler.setReady(true)
    await expect(modeler.load('leave')).resolves.toBe(true)
    expect(modeler.requestCount).toBe(1)
    expect(modeler.definition.version).toBe(2)
    expect(modeler.dirty).toBe(false)
  })

  it('updateXml 置脏，discard 回滚清脏', () => {
    const modeler = readyModeler()
    modeler.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
    expect(modeler.dirty).toBe(true)
    modeler.discard()
    expect(modeler.dirty).toBe(false)
    expect(modeler.xml).toBe(VALID_XML)
  })

  it('select 命中与清空', () => {
    const modeler = readyModeler()
    expect(modeler.select('t1')).toMatchObject({ id: 't1', type: 'userTask' })
    expect(modeler.selected?.id).toBe('t1')
    expect(modeler.select(undefined)).toBeUndefined()
    expect(modeler.selectedId).toBe('')
  })
})

describe('导入与校验', () => {
  it('导入非法 XML 不生效且可定位', () => {
    const modeler = readyModeler()
    expect(modeler.importXml(INVALID_XML)).toBe(false)
    expect(modeler.xml).toBe(VALID_XML)
    expect(modeler.phase).toBe('failed')
  })

  it('导入两段确认：请求待确认、取消保持原画布、确认生效', () => {
    const modeler = readyModeler()
    const next = VALID_XML.replace('name="审批"', 'name="复核"')
    expect(modeler.requestImport(next)).toBe(true)
    expect(modeler.importPending).toBe(next)
    modeler.cancelImport()
    expect(modeler.confirmImport()).toBe(false)
    expect(modeler.xml).toBe(VALID_XML)

    modeler.requestImport(next)
    expect(modeler.confirmImport()).toBe(true)
    expect(modeler.xml).toContain('复核')
  })

  it('校验：未注入引擎来源为 structure，注入后为 engine 并合并错误', async () => {
    const structureOnly = readyModeler()
    await structureOnly.validate()
    expect(structureOnly.validateResult?.source).toBe('structure')
    expect(structureOnly.requestCount).toBe(0)

    const withEngine = readyModeler({
      validate: async () => ({ valid: false, errors: [{ elementId: 't1', message: '引擎不可解析' }], source: 'engine' }),
    })
    await withEngine.validate()
    expect(withEngine.validateResult?.source).toBe('engine')
    expect(withEngine.validateResult?.valid).toBe(false)
    expect(withEngine.requestCount).toBe(1)
    expect(withEngine.errorTarget?.elementId).toBe('t1')
  })
})

describe('保存草稿与发布', () => {
  it('保存草稿：载荷携带幂等键，成功后清脏', async () => {
    const keys: string[] = []
    const modeler = readyModeler({
      saveDraft: async (input) => {
        keys.push(input.idempotencyKey)
        return { version: input.version }
      },
    })
    modeler.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
    await modeler.saveDraft()
    expect(keys).toHaveLength(1)
    expect(keys[0]).toMatch(/^wfd:[0-9a-f]{8}$/)
    expect(modeler.dirty).toBe(false)
    expect(modeler.phase).toBe('done')
  })

  it('发布推进版本并清脏；内容变更换键', async () => {
    const modeler = readyModeler({ deploy: async () => ({ version: 3 }) })
    const before = modeler.idempotencyKey('deploy')
    await modeler.deploy()
    expect(modeler.definition.version).toBe(3)
    expect(modeler.definition.status).toBe('published')
    expect(modeler.dirty).toBe(false)

    modeler.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
    expect(modeler.idempotencyKey('deploy')).not.toBe(before)
  })

  it('校验不通过时保存与发布阻断且不请求', async () => {
    const modeler = readyModeler({
      saveDraft: async () => ({ version: 1 }),
      deploy: async () => ({ version: 3 }),
    })
    modeler.updateXml(INVALID_XML)
    const before = modeler.requestCount
    await expect(modeler.saveDraft()).resolves.toBeUndefined()
    await expect(modeler.deploy()).resolves.toBeUndefined()
    expect(modeler.requestCount).toBe(before)
  })

  it('未注入保存处理时不请求且保留本地变更', async () => {
    const modeler = readyModeler({})
    modeler.updateXml(VALID_XML.replace('name="审批"', 'name="复核"'))
    const before = modeler.requestCount
    await expect(modeler.saveDraft()).resolves.toBeUndefined()
    expect(modeler.requestCount).toBe(before)
    expect(modeler.dirty).toBe(true)
  })

  it('进行中重复提交不动作', async () => {
    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    let calls = 0
    const modeler = readyModeler({
      saveDraft: async () => {
        calls += 1
        await gate
        return { version: 2 }
      },
    })
    const pending = modeler.saveDraft()
    // 提交前先做结构校验（异步），让出一拍后进入提交阶段。
    await Promise.resolve()
    await Promise.resolve()
    expect(modeler.busy).toBe(true)
    await expect(modeler.saveDraft()).resolves.toBeUndefined()
    release()
    await pending
    expect(calls).toBe(1)
  })
})

describe('只读与权限', () => {
  it('只读态不可编辑 / 保存 / 发布，导出与校验仍可用', async () => {
    const modeler = readyModeler({ saveDraft: async () => ({ version: 1 }) })
    modeler.setReadOnly(true)
    expect(modeler.canEdit).toBe(false)
    expect(modeler.canDeploy).toBe(false)
    await expect(modeler.saveDraft()).resolves.toBeUndefined()
    expect(modeler.exportXml()).toBe(VALID_XML)
    expect(modeler.requestImport(VALID_XML)).toBe(false)
  })

  it('无权（缺 wf:define）不可编辑', () => {
    const modeler = readyModeler()
    modeler.access?.setCodes([])
    expect(modeler.canEdit).toBe(false)
    modeler.access?.setCodes(['wf:define'])
    expect(modeler.canEdit).toBe(true)
  })
})

describe('错误码与重试', () => {
  it('60006 定位元素并重试恢复', async () => {
    let attempt = 0
    const modeler = readyModeler({
      deploy: async () => {
        attempt += 1
        if (attempt === 1) {
          throw Object.assign(new Error('BPMN 非法'), { code: 60006, elementId: 't1' })
        }
        return { version: 3 }
      },
    })
    await modeler.deploy()
    expect(modeler.phase).toBe('failed')
    expect(modeler.errorTarget).toMatchObject({ code: 60006, elementId: 't1' })
    await expect(modeler.retry()).resolves.toEqual({ version: 3 })
    expect(modeler.phase).toBe('done')
  })

  it('60007 定义级提示（刷新标记）', async () => {
    const modeler = readyModeler({
      deploy: async () => {
        throw Object.assign(new Error('定义被引用不可删除'), { code: 60007 })
      },
    })
    await modeler.deploy()
    expect(modeler.errorTarget).toMatchObject({ code: 60007, refresh: true })
    expect(modeler.errorTarget?.elementId).toBeUndefined()
  })

  it('重置清错误与重试入参', async () => {
    const modeler = readyModeler({
      deploy: async () => {
        throw Object.assign(new Error('BPMN 非法'), { code: 60006 })
      },
    })
    await modeler.deploy()
    expect(modeler.phase).toBe('failed')
    modeler.reset()
    expect(modeler.phase).toBe('idle')
    expect(await modeler.retry()).toBeUndefined()
  })
})
