// kiwi_id: 771
/** 表单设计器能力基类用例（08-6-1）：契约套件 + 拖拽广播 + 层级与权限 + 保存发布恢复 + 自建字段。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseDragDrop,
  BaseFormDesigner,
  BaseFormMeta,
  BaseNotice,
  FORMDESIGN_PERM,
  validateCapabilityGraph,
  type FormField,
  type FormLayoutLevels,
} from '../src'
import {
  FORM_CONTRACT_FIELDS,
  contractLayout,
  describeFormDesignerContract,
  describeFormLayoutContract,
  type FormDesignerContractTarget,
  type FormDesignerJobs,
  type FormDesignerLevel,
  type FormLayoutContractTarget,
} from '../testing'

/** 具体设计器（可实例化）。 */
class DemoDesigner extends BaseFormDesigner {}

/** 具体拖拽能力（可实例化）。 */
class DemoDragDrop extends BaseDragDrop {}

/** 具体权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 具体提示（可实例化）。 */
class DemoNotice extends BaseNotice {}

/** 具体表单元数据（可实例化）。 */
class DemoFormMeta extends BaseFormMeta {}

/** 契约取数快照。 */
const SNAPSHOT: { levels: FormLayoutLevels; fields: readonly FormField[] } = {
  levels: { tenant: contractLayout(['name']), platform: contractLayout(['name', 'remark']) },
  fields: FORM_CONTRACT_FIELDS,
}

/** 构造持维护权限的权限上下文（未持权限时设计器只读）。 */
function granted(): DemoAccess {
  const access = new DemoAccess()
  access.setCodes([FORMDESIGN_PERM])
  return access
}

/** 元数据契约目标工厂（适配器接核心基类）。 */
function makeLayoutTarget(): FormLayoutContractTarget {
  const designer = new DemoDesigner()
  designer.setAccess(granted())
  designer.setRegisteredTypes(['text', 'longtext'])
  designer.setReady(true)
  designer.setFields(FORM_CONTRACT_FIELDS)
  designer.setLayouts({ tenant: contractLayout(['name']) })
  designer.markBaseline()
  return {
    get layout() {
      return designer.layout
    },
    get levels() {
      return designer.levels
    },
    get fields() {
      return designer.fields
    },
    get level() {
      return designer.level
    },
    get readonly() {
      return designer.readonly
    },
    get dirty() {
      return designer.dirty
    },
    effective: () => designer.effective,
    renderMetadata: () => designer.renderMetadata,
    validation: () => designer.validation,
    unknownFields: () => designer.unknownFields,
    duplicateFields: () => designer.duplicateFields,
    setLayouts: (levels) => designer.setLayouts(levels),
    setFields: (fields) => designer.setFields(fields),
    setLevel: (level) => void designer.setLevel(level as FormDesignerLevel),
    addField: (fieldKey, sectionKey) => designer.addField(fieldKey, sectionKey),
    moveField: (input) => designer.moveField(input),
    removeField: (fieldKey) => designer.removeField(fieldKey),
    toggleColSpan: (fieldKey) => designer.toggleColSpan(fieldKey),
    setColumns: (sectionKey, columns) => designer.setColumns(sectionKey, columns),
    addSection: () => designer.addSection(),
    removeSection: (sectionKey) => designer.removeSection(sectionKey),
    renameSection: (sectionKey, title) => designer.renameSection(sectionKey, title),
    setLabelPosition: (position) => designer.setLabelPosition(position),
    setLabelWidth: (width) => designer.setLabelWidth(width),
    setQueryFields: (keys) => designer.setQueryFields(keys),
    setDetailColumns: (columns) => designer.setDetailColumns(columns),
    markBaseline: () => designer.markBaseline(),
    discard: () => designer.discard(),
  }
}

/** 设计器编排契约目标工厂。 */
function makeDesignerTarget(): FormDesignerContractTarget {
  const designer = new DemoDesigner()
  designer.setFormCode('leave')
  designer.setLevel('tenant')
  return {
    get ready() {
      return designer.ready
    },
    get degraded() {
      return designer.degraded
    },
    get readonly() {
      return designer.readonly
    },
    get canEdit() {
      return designer.canEdit
    },
    get canSave() {
      return designer.canSave
    },
    get busy() {
      return designer.busy
    },
    get requestCount() {
      return designer.requestCount
    },
    get phase() {
      return designer.phase
    },
    layout: () => designer.layout,
    fields: () => designer.fields,
    selected: () => designer.selected,
    dirty: () => designer.dirty,
    validation: () => designer.validation,
    setReady: (value) => designer.setReady(value),
    setJobs: (jobs) => designer.setJobs(jobs as FormDesignerJobs),
    setOperators: (input) => {
      const access = new DemoAccess()
      access.setCodes(input.codes ?? [])
      designer.setAccess(input.codes === undefined ? undefined : access)
      designer.setRegisteredTypes(input.registeredTypes ?? [])
    },
    load: () => designer.load(),
    select: (target) => designer.select(target),
    addField: (fieldKey, sectionKey) => designer.addField(fieldKey, sectionKey),
    moveField: (input) => designer.moveField(input),
    setColumns: (sectionKey, columns) => designer.setColumns(sectionKey, columns),
    addSection: () => designer.addSection(),
    discard: () => designer.discard(),
    needsBlock: (action) => designer.needsBlock(action),
    setFormCode: (formCode) => designer.setFormCode(formCode),
    setLevel: (level) => designer.setLevel(level as FormDesignerLevel),
    save: () => designer.save(),
    publish: () => designer.publish(),
    restoreDefault: () => designer.restoreDefault(),
    createField: (draft) => designer.createField(draft),
    retryField: (fieldKey) => designer.retryField(fieldKey),
  }
}

describeFormLayoutContract('布局元数据契约（BaseFormDesigner 适配）', makeLayoutTarget)
describeFormDesignerContract('表单设计器编排契约（BaseFormDesigner）', makeDesignerTarget)

describe('能力身份与依赖', () => {
  it('能力键与依赖登记', () => {
    const designer = new DemoDesigner()
    expect(designer.identifier).toBe('form-designer')
    expect(designer.depends).toEqual(['placeholder-state', 'drag-drop', 'form-meta', 'access', 'notice'])
    expect(designer.pluginKey).toBe('form-designer')
  })

  it('能力依赖图合规（单向、无环、已登记）', () => {
    expect(validateCapabilityGraph()).toEqual([])
  })
})

describe('拖拽协作（经 BaseDragDrop 广播）', () => {
  it('落点后广播 drop 载荷（跨分区标记）', () => {
    const designer = new DemoDesigner()
    const drag = new DemoDragDrop()
    const seen: { phase: string; source: string; target?: string; crossZone?: boolean }[] = []
    drag.onDrag((payload) =>
      seen.push({ phase: payload.phase, source: payload.source, target: payload.target, crossZone: payload.crossZone }),
    )
    designer.setDrag(drag)
    designer.setAccess(granted())
    designer.setRegisteredTypes(['text'])
    designer.setReady(true)
    designer.setFields(FORM_CONTRACT_FIELDS)
    designer.setLayouts({ tenant: contractLayout(['name']) })
    designer.setLevel('tenant')
    designer.markBaseline()

    expect(
      designer.moveField({ fieldKey: 'remark', toSectionKey: 's1', index: 0, fromSectionKey: 's2', crossZone: true }),
    ).toBe(true)
    expect(seen).toEqual([{ phase: 'drop', source: 's2', target: 's1', crossZone: true }])
    expect(designer.drag?.dragging).toBe(false)
  })

  it('拖拽能力未注入仍完成落点', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setRegisteredTypes(['text'])
    designer.setReady(true)
    designer.setFields(FORM_CONTRACT_FIELDS)
    designer.setLayouts({ tenant: contractLayout(['name']) })
    designer.setLevel('tenant')
    designer.markBaseline()

    expect(designer.drag).toBeUndefined()
    expect(designer.moveField({ fieldKey: 'remark', toSectionKey: 's1' })).toBe(true)
    expect(designer.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
  })
})

describe('取数与组合能力', () => {
  it('注入表单元数据时先取元数据再取快照', async () => {
    const designer = new DemoDesigner()
    const meta = new DemoFormMeta()
    const calls: string[] = []
    meta.loader = async () => {
      calls.push('meta')
      return { code: 'leave' }
    }
    designer.setFormMeta(meta)
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setJobs({
      load: async () => {
        calls.push('load')
        return SNAPSHOT
      },
    })
    await designer.load()
    expect(calls).toEqual(['meta', 'load'])
    expect(designer.phase).toBe('done')
    expect(designer.dirty).toBe(false)
  })

  it('取数失败置失败态并写文案', async () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setJobs({
      load: async () => {
        throw new Error('布局取数失败')
      },
    })
    await expect(designer.load()).resolves.toBeUndefined()
    expect(designer.phase).toBe('failed')
    expect(designer.errorMessage).toContain('布局取数失败')
  })
})

describe('保存发布与恢复默认', () => {
  it('保存成功后写回层级并清脏；发布依赖载荷', async () => {
    const designer = new DemoDesigner()
    const saved: FormLayoutLevels[] = []
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setJobs({
      load: async () => SNAPSHOT,
      save: async (input) => {
        saved.push({ [input.level]: input.layout })
        return { recordVersion: 5 }
      },
      publish: async () => undefined,
    })
    await designer.load()
    designer.addField('remark')
    await expect(designer.save()).resolves.toEqual({ recordVersion: 5 })
    expect(saved).toHaveLength(1)
    expect(designer.levels.tenant?.main.sections[0]?.fields).toHaveLength(2)
    expect(designer.dirty).toBe(false)

    await expect(designer.publish()).resolves.toBe(true)
    expect(designer.requestCount).toBe(3)
  })

  it('校验不通过时不可保存', () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setFields(FORM_CONTRACT_FIELDS)
    designer.setLayouts({ tenant: contractLayout(['absent']) })
    designer.setLevel('tenant')
    designer.markBaseline()
    expect(designer.validation.valid).toBe(false)
    expect(designer.canSave).toBe(false)
  })

  it('恢复默认失败保留本地', async () => {
    const designer = new DemoDesigner()
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setJobs({
      load: async () => SNAPSHOT,
      restore: async () => {
        throw new Error('恢复失败')
      },
    })
    await designer.load()
    await expect(designer.restoreDefault()).resolves.toBe(false)
    expect(designer.phase).toBe('failed')
    expect(designer.errorMessage).toContain('恢复失败')
  })
})

describe('权限与提示协作', () => {
  it('有权（未注入权限上下文）可编辑；注入无权限码则只读', () => {
    const designer = new DemoDesigner()
    designer.setReady(true)
    expect(designer.access).toBeUndefined()
    expect(designer.canEdit).toBe(true)

    const access = new DemoAccess()
    designer.setAccess(access)
    expect(designer.canEdit).toBe(false)
    access.setCodes([FORMDESIGN_PERM])
    expect(designer.canEdit).toBe(true)
  })

  it('提示通知可注入（保存成功不改对外形状）', async () => {
    const designer = new DemoDesigner()
    const notice = new DemoNotice()
    designer.setNotice(notice)
    designer.setAccess(granted())
    designer.setReady(true)
    designer.setJobs({
      load: async () => SNAPSHOT,
      save: async () => ({ recordVersion: 1 }),
    })
    await designer.load()
    designer.addField('remark')
    await designer.save()
    expect(designer.notice).toBe(notice)
    expect(designer.dirty).toBe(false)
  })
})
