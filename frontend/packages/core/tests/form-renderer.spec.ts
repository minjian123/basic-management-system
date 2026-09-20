// kiwi_id: 772
// 能力基类用例：占位零请求 / 取数装载 / 三态与权限 / 即时与全量校验 / 明细 / 提交与重试 / 防重复 / 契约套件。
import { describe, expect, it } from 'vitest'

import { BaseAccess } from '../src/capabilities/access'
import { BaseFieldPerm } from '../src/capabilities/field-perm'
import { BaseFormRenderer } from '../src/capabilities/form-renderer'
import { BaseFormMeta } from '../src/capabilities/form-meta'
import { BaseNotice } from '../src/capabilities/notice'
import { BaseValidatable } from '../src/capabilities/validatable'
import { CAPABILITY_MANIFEST, validateCapabilityGraph } from '../src/capabilities/manifest'
import {
  RENDER_CONTRACT_FIELDS,
  RENDER_CONTRACT_LAYOUT,
  RENDER_CONTRACT_PERMISSIONS,
  describeFormRendererContract,
  type FormRendererContractTarget,
} from '../testing'

/** 具体渲染器（可实例化）。 */
class RendererState extends BaseFormRenderer {}

/** 具体权限上下文。 */
class AccessState extends BaseAccess {}

/** 具体字段权限。 */
class FieldPermState extends BaseFieldPerm {}

/** 具体表单元数据。 */
class FormMetaState extends BaseFormMeta {}

/** 具体提示通知。 */
class NoticeState extends BaseNotice {}

/** 具体校验能力。 */
class ValidatableState extends BaseValidatable {}

describe('BaseFormRenderer 能力身份与依赖', () => {
  it('能力键与依赖登记一致且图无环', () => {
    const renderer = new RendererState()
    expect(renderer.identifier).toBe('form-renderer')
    expect(renderer.depends).toEqual(['placeholder-state', 'form-meta', 'field-perm', 'access', 'notice', 'validatable'])
    expect(CAPABILITY_MANIFEST['form-renderer']).toEqual(['placeholder-state', 'form-meta', 'field-perm', 'access', 'notice', 'validatable'])
    expect(validateCapabilityGraph()).toEqual([])
  })

  it('初始为占位态：降级、只读、零请求', () => {
    const renderer = new RendererState()
    expect(renderer.degraded).toBe(true)
    expect(renderer.readonly).toBe(true)
    expect(renderer.requestCount).toBe(0)
    expect(renderer.phase).toBe('idle')
    expect(renderer.fields).toEqual([])
    expect(renderer.canSubmit).toBe(false)
  })
})

describe('BaseFormRenderer 协作能力注入', () => {
  it('注入协作能力后只读判定随权限上下文变化', () => {
    const renderer = new RendererState()
    renderer.setReady(true)
    expect(renderer.readonly).toBe(false)

    const access = new AccessState()
    access.setCodes([])
    renderer.setAccess(access)
    expect(renderer.readonly).toBe(true)

    access.setCodes(['formdesign:query'])
    expect(renderer.readonly).toBe(false)

    // 字段权限能力可整体收紧。
    const perm = new FieldPermState()
    perm.applyPerm({ editable: false })
    renderer.setFieldPerm(perm)
    expect(renderer.plan.sections).toEqual([])
    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })
    expect(renderer.fields.every((field) => !field.editable)).toBe(true)

    renderer.setFormMeta(new FormMetaState())
    renderer.setNotice(new NoticeState())
    renderer.setValidatable(new ValidatableState())
    renderer.setAccess(undefined)
    renderer.setFieldPerm(undefined)
    expect(renderer.readonly).toBe(false)
  })
})

describe('BaseFormRenderer 取数与提交', () => {
  it('取数经表单元数据与注入处理函数两段', async () => {
    const calls: string[] = []
    const formMeta = new FormMetaState()
    formMeta.loader = async () => {
      calls.push('meta')
      return { form: 'leave' }
    }
    const renderer = new RendererState()
    renderer.setFormCode('leave')
    renderer.setReady(true)
    renderer.setFormMeta(formMeta)
    renderer.setJobs({
      loadLayout: async (input) => {
        calls.push(`layout:${input.formCode}:${input.mode}`)
        return { layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS }
      },
    })

    await expect(renderer.load()).resolves.toBeDefined()
    expect(calls).toEqual(['meta', 'layout:leave:create'])
    expect(renderer.phase).toBe('done')
    expect(renderer.requestCount).toBe(1)
  })

  it('编辑态取数追加详情并写回记录版本', async () => {
    const renderer = new RendererState()
    renderer.setFormCode('leave')
    renderer.setMode('edit')
    renderer.setRecordId(7)
    renderer.setReady(true)
    renderer.setJobs({
      loadLayout: async () => ({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS }),
      loadRecord: async () => ({ data: { name: '甲' }, details: { lines: [{ name: 'P1' }] }, recordVersion: 3 }),
    })

    await expect(renderer.load()).resolves.toBeDefined()
    expect(renderer.requestCount).toBe(2)
    expect(renderer.getFieldValue('name')).toBe('甲')
    expect(renderer.details.lines).toHaveLength(1)
    expect(renderer.recordVersion).toBe(3)
  })

  it('取数失败置失败态并保留错误文案', async () => {
    const renderer = new RendererState()
    renderer.setReady(true)
    renderer.setJobs({
      loadLayout: async () => {
        throw new Error('布局取数失败')
      },
    })
    await expect(renderer.load()).resolves.toBeUndefined()
    expect(renderer.phase).toBe('failed')
    expect(renderer.errorMessage).toBe('布局取数失败')
  })

  it('校验通过才提交；主从载荷同事务提交', async () => {
    const payloads: unknown[] = []
    const renderer = new RendererState()
    renderer.setFormCode('leave')
    renderer.setMode('edit')
    renderer.setReady(true)
    renderer.setJobs({
      submit: async (input) => {
        payloads.push(input)
        return { recordVersion: 5 }
      },
    })
    renderer.setMeta({
      layout: RENDER_CONTRACT_LAYOUT,
      fields: RENDER_CONTRACT_FIELDS,
      permissions: RENDER_CONTRACT_PERMISSIONS,
    })

    await expect(renderer.submit()).resolves.toBeUndefined()
    expect(renderer.phase).toBe('failed')
    expect(payloads).toHaveLength(0)

    renderer.setData({ name: '甲' })
    await expect(renderer.submit()).resolves.toEqual({ recordVersion: 5 })
    expect(renderer.phase).toBe('done')
    expect(renderer.recordVersion).toBe(5)
    expect(payloads).toHaveLength(1)
  })

  it('提交失败保留本地数据与错误，重试恢复', async () => {
    let fail = true
    const renderer = new RendererState()
    renderer.setReady(true)
    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })
    renderer.setJobs({
      submit: async () => {
        if (fail) {
          throw new Error('提交失败')
        }
        return { recordVersion: 2 }
      },
    })
    renderer.setData({ name: '甲' })
    await expect(renderer.submit()).resolves.toBeUndefined()
    expect(renderer.phase).toBe('failed')
    expect(renderer.getFieldValue('name')).toBe('甲')

    fail = false
    await expect(renderer.retry()).resolves.toEqual({ recordVersion: 2 })
    expect(renderer.phase).toBe('done')
  })

  it('进行中防重复提交', async () => {
    let release: () => void = () => undefined
    const gate = new Promise<void>((resolve) => {
      release = resolve
    })
    const renderer = new RendererState()
    renderer.setReady(true)
    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })
    renderer.setJobs({
      submit: async () => {
        await gate
        return { recordVersion: 1 }
      },
    })
    renderer.setData({ name: '甲' })

    const pending = renderer.submit()
    expect(renderer.busy).toBe(true)
    await expect(renderer.submit()).resolves.toBeUndefined()
    release()
    await expect(pending).resolves.toEqual({ recordVersion: 1 })
    expect(renderer.requestCount).toBe(1)
  })
})

describe('BaseFormRenderer 结构与边界', () => {
  it('切换表单 / 记录清空元数据与数据', () => {
    const renderer = new RendererState()
    renderer.setReady(true)
    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })
    renderer.setData({ name: '甲' })
    expect(renderer.setFormCode('leave')).toBe(true)
    expect(renderer.fields).toEqual([])
    expect(renderer.getFieldValue('name')).toBeUndefined()
    expect(renderer.phase).toBe('idle')

    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })
    renderer.setData({ name: '甲' })
    renderer.setRecordId(3)
    expect(renderer.getFieldValue('name')).toBeUndefined()
  })

  it('明细增删改与只读拦截', () => {
    const renderer = new RendererState()
    renderer.setReady(true)
    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })

    expect(renderer.addDetailRow('lines', { project_no: 'P1' })).toBe(true)
    expect(renderer.setDetailCell('lines', 0, 'project_no', 'P2')).toBe(true)
    expect(renderer.setDetailCell('lines', 0, 'broken', 'x')).toBe(false)
    expect(renderer.removeDetailRow('lines', 0)).toBe(true)
    expect(renderer.removeDetailRow('lines', 0)).toBe(false)

    renderer.setForceReadOnly(true)
    expect(renderer.addDetailRow('lines')).toBe(false)
    expect(renderer.setDetailRows('lines', [])).toBe(false)
  })

  it('未就绪时字段写入不动作', () => {
    const renderer = new RendererState()
    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })
    expect(renderer.setFieldValue('name', '甲')).toBe(false)
  })

  it('reset 清空数据与错误', () => {
    const renderer = new RendererState()
    renderer.setReady(true)
    renderer.setMeta({ layout: RENDER_CONTRACT_LAYOUT, fields: RENDER_CONTRACT_FIELDS })
    renderer.setData({ name: '甲' })
    renderer.setDetails({ lines: [{ name: 'P1' }] })
    renderer.validate()
    renderer.reset()
    expect(renderer.getFieldValue('name')).toBeUndefined()
    expect(renderer.details).toEqual({})
    expect(renderer.validation.valid).toBe(true)
  })
})

/** 契约目标适配（核心实例直连；每次新建，避免用例间状态污染）。 */
function createContractTarget(): FormRendererContractTarget {
  const renderer = new RendererState()
  const access = new AccessState()
  renderer.setFormCode('leave')
  return {
    get ready() {
      return renderer.ready
    },
    get degraded() {
      return renderer.degraded
    },
    get readonly() {
      return renderer.readonly
    },
    get busy() {
      return renderer.busy
    },
    get requestCount() {
      return renderer.requestCount
    },
    get phase() {
      return renderer.phase
    },
    get mode() {
      return renderer.mode
    },
    get canSubmit() {
      return renderer.canSubmit
    },
    plan: () => ({
      sections: renderer.plan.sections.map((section) => ({
        key: section.key,
        columns: section.columns,
        fields: section.fields.map((field) => ({
          key: field.key,
          label: field.label,
          widget: field.widget,
          unknown: field.unknown,
          colSpan: field.colSpan,
          placeholder: field.placeholder,
          options: field.options.map((option) => option.value),
          ruleKinds: field.rules.map((rule) => rule.kind),
          value: field.value,
          visible: field.visible,
          editable: field.editable,
          disabled: field.disabled,
          required: field.required,
          masked: field.masked,
          displayOnly: field.displayOnly,
        })),
        groupKeys: section.groups.map((group) => group.key),
        firstGroupKeys: section.groups[0]?.fields.map((field) => field.key) ?? [],
      })),
      detailColumns: renderer.detailColumns.map((column) => ({
        key: column.key,
        title: column.title,
        editable: column.editable,
      })),
      detailFallback: renderer.plan.detailFallback,
      unknownFields: renderer.plan.unknownFields,
      disabledFields: renderer.plan.disabledFields,
      hiddenFields: renderer.plan.hiddenFields,
      fallback: renderer.plan.fallback,
      readonly: renderer.plan.readonly,
    }),
    fields: () =>
      renderer.fields.map((field) => ({
        key: field.key,
        label: field.label,
        widget: field.widget,
        unknown: field.unknown,
        colSpan: field.colSpan,
        placeholder: field.placeholder,
        options: field.options.map((option) => option.value),
        ruleKinds: field.rules.map((rule) => rule.kind),
        value: field.value,
        visible: field.visible,
        editable: field.editable,
        disabled: field.disabled,
        required: field.required,
        masked: field.masked,
        displayOnly: field.displayOnly,
      })),
    detailColumns: () =>
      renderer.detailColumns.map((column) => ({ key: column.key, title: column.title, editable: column.editable })),
    validation: () => ({
      valid: renderer.validation.valid,
      errorFields: renderer.validation.errors.map((error) => error.field),
      firstField: renderer.validation.firstField,
      message: renderer.validation.message,
    }),
    detailValidation: () => ({
      valid: renderer.detailValidation.valid,
      positions: renderer.detailValidation.errors.map((error) => `${error.detailKey}:${error.index}:${error.field}`),
      message: renderer.detailValidation.message,
    }),
    unknownFields: () => renderer.unknownFields,
    disabledFields: () => renderer.disabledFields,
    setReady: (value) => renderer.setReady(value),
    setJobs: (jobs) => renderer.setJobs(jobs as never),
    setOperators: (input) => {
      access.setCodes(input.codes ?? [])
      renderer.setAccess(access)
      if (input.permissions !== undefined) {
        renderer.setPermissions(input.permissions)
      }
    },
    setMode: (mode) => renderer.setMode(mode),
    setMeta: (input) => renderer.setMeta(input as never),
    setData: (data) => renderer.setData(data),
    setDetails: (details) => renderer.setDetails(details),
    setOverrides: (overrides) => renderer.setOverrides(overrides as never),
    setFieldValue: (fieldKey, value) => renderer.setFieldValue(fieldKey, value),
    getFieldValue: (fieldKey) => renderer.getFieldValue(fieldKey),
    setDetailRows: (detailKey, rows) => renderer.setDetailRows(detailKey, rows),
    addDetailRow: (detailKey, row) => renderer.addDetailRow(detailKey, row),
    removeDetailRow: (detailKey, index) => renderer.removeDetailRow(detailKey, index),
    detailRows: (detailKey) => renderer.details[detailKey] ?? [],
    setDetailCell: (detailKey, index, fieldKey, value) => renderer.setDetailCell(detailKey, index, fieldKey, value),
    validate: () => {
      renderer.validate()
      return {
        valid: renderer.validation.valid,
        errorFields: renderer.validation.errors.map((error) => error.field),
        firstField: renderer.validation.firstField,
        message: renderer.validation.message,
      }
    },
    validateField: (fieldKey) => renderer.validateField(fieldKey),
    load: () => renderer.load(),
    submit: () => renderer.submit(),
    retry: () => renderer.retry(),
    reset: () => renderer.reset(),
  }
}

describe('渲染编排契约（核心实例）', () => {
  describeFormRendererContract('BaseFormRenderer 契约', createContractTarget)
})
