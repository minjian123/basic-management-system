// kiwi_id: 772
/** 表单渲染器用例（08_06_02）：投影薄适配 + 分发映射 + 两件真实实现 + 分包边界。 */

import type { FieldRendererRegistry, FormField, LayoutEffective, RenderPlan } from '@bms/core'
import { buildRenderPlan } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { FormRenderer, getFieldWidget, resolveFieldComponent, useBaseFormRenderer } from '../src'
import FormRendererBody from '../src/components/form-render/FormRendererBody.vue'

/** 字段清单样例。 */
const fields: FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active', required: true },
  { key: 'remark', label: '备注', type: 'longtext', group: 'platform', status: 'active' },
  { key: 'amount', label: '金额', type: 'amount', group: 'platform', status: 'active' },
  {
    key: 'level',
    label: '等级',
    type: 'select',
    group: 'platform',
    status: 'active',
    options: [{ value: 'a', label: '甲' }],
  },
  { key: 'mystery', label: '未知', type: 'wild_type', group: 'platform', status: 'active' },
  { key: 'broken', label: '失效', type: 'text', group: 'tenant', status: 'failed' },
]

/** 布局样例（两分区 + 分组 + 明细列 + 失效引用）。 */
const layout = {
  main: {
    labelPosition: 'top' as const,
    sections: [
      {
        key: 's1',
        title: '基本信息',
        columns: 2 as const,
        fields: [{ key: 'name' }, { key: 'remark', colSpan: true }, { key: 'absent' }],
      },
      {
        key: 's2',
        title: '扩展',
        columns: 3 as const,
        fields: [{ key: 'amount' }, { key: 'mystery' }],
        groups: [{ key: 'g1', title: '组织', fields: [{ key: 'broken' }] }],
      },
    ],
  },
  detail: { columns: [{ key: 'name', width: 200 }, { key: 'remark' }] },
}

/** 生效元数据样例。 */
const meta: LayoutEffective = {
  layout,
  fields,
  level: 'tenant',
  source: 'tenant',
  readonly: false,
  fallback: false,
  permissions: { remark: { visible: false } },
}

/**
 * 渲染计划样例（核心纯函数派生，避免用例手写字面量漂移）。
 *
 * @param permissions 字段权限标记（缺省无权限叠加）。
 */
function buildPlan(permissions?: Record<string, { visible?: boolean; editable?: boolean }>): RenderPlan {
  return buildRenderPlan({ ...meta, permissions }, { mode: 'edit' })
}

/** 处理函数集样例（取布局 / 取详情 / 提交）。 */
function makeJobs(): {
  jobs: Parameters<ReturnType<typeof useBaseFormRenderer>['setJobs']>[0]
  calls: string[]
} {
  const calls: string[] = []
  return {
    calls,
    jobs: {
      loadLayout: async (input) => {
        calls.push(`layout:${input.formCode}:${input.mode}`)
        return { layout, fields, permissions: { remark: { visible: false } } }
      },
      loadRecord: async (input) => {
        calls.push(`record:${input.recordId}`)
        return { data: { name: '甲' }, details: { lines: [{ name: 'P1' }] }, recordVersion: 3 }
      },
      submit: async () => {
        calls.push('submit')
        return { recordVersion: 5 }
      },
    },
  }
}

describe('useBaseFormRenderer 投影', () => {
  it('占位态零请求；就绪后取数装载元数据与详情', async () => {
    const renderer = useBaseFormRenderer({ formCode: 'leave', mode: 'edit', recordId: 7 })
    const { jobs, calls } = makeJobs()
    renderer.setJobs(jobs)
    await renderer.load()
    expect(calls).toEqual([])
    expect(renderer.degraded.value).toBe(true)

    renderer.setReady(true)
    await renderer.load()
    expect(calls).toEqual(['layout:leave:edit', 'record:7'])
    expect(renderer.plan.value.sections).toHaveLength(2)
    expect(renderer.data.value.name).toBe('甲')
    expect(renderer.details.value.lines).toHaveLength(1)
  })

  it('三态与权限叠加经投影同步（查看态只读、权限双向）', () => {
    const renderer = useBaseFormRenderer({
      ready: true,
      formCode: 'leave',
      mode: 'view',
      meta,
      permissions: { name: { editable: true }, remark: { visible: false } },
    })
    expect(renderer.readonly.value).toBe(true)
    expect(renderer.fields.value.find((field) => field.key === 'amount')?.editable).toBe(false)
    // 权限显式放开查看态（拍板口径）。
    expect(renderer.fields.value.find((field) => field.key === 'name')?.editable).toBe(true)
    expect(renderer.fields.value.find((field) => field.key === 'remark')?.visible).toBe(false)
  })

  it('即时校验与提交链路经投影同步', async () => {
    const renderer = useBaseFormRenderer({ ready: true, formCode: 'leave', mode: 'edit', meta })
    const { jobs, calls } = makeJobs()
    renderer.setJobs(jobs)

    expect(renderer.setFieldValue('name', '甲')).toBe(true)
    expect(renderer.validation.value.valid).toBe(true)

    await expect(renderer.submit()).resolves.toEqual({ recordVersion: 5 })
    expect(calls).toContain('submit')
    expect(renderer.phase.value).toBe('done')
  })
})

describe('utils/formWidgets 分发映射', () => {
  it('基础语义键映射到内建控件', () => {
    expect(getFieldWidget('text')).toBeDefined()
    expect(getFieldWidget('textarea')).toBeDefined()
    expect(getFieldWidget('datetime')).toBeDefined()
    expect(getFieldWidget('select')).toBeDefined()
    expect(getFieldWidget('plain')).toBeUndefined()
  })

  it('金额 / 枚举类型走专用件，未知类型回落纯文本', () => {
    expect(resolveFieldComponent({ widget: 'number', fieldType: 'amount' })).toBeDefined()
    expect(resolveFieldComponent({ widget: 'radio', fieldType: 'radio' })).toBeDefined()
    expect(resolveFieldComponent({ widget: 'plain', fieldType: 'wild_type' })).toBeUndefined()
  })

  it('注册表自定义类型优先命中', () => {
    const custom = { name: 'CustomField' }
    const registry = {
      resolveByType: (type: string) => (type === 'biz_field' ? { component: custom } : undefined),
    } as unknown as FieldRendererRegistry
    expect(resolveFieldComponent({ widget: 'plain', fieldType: 'biz_field', registry })).toBe(custom)
    expect(resolveFieldComponent({ widget: 'text', fieldType: 'name', registry })).toBeDefined()
  })

  it('重控件按语义键解析到对应组件（富文本 / 文件 / 组织 / 穿梭 / 级联）', () => {
    expect(getFieldWidget('richtext')).toBeDefined()
    expect(getFieldWidget('file')).toBeDefined()
    expect(getFieldWidget('org-select')).toBeDefined()
    expect(getFieldWidget('transfer')).toBeDefined()
    expect(getFieldWidget('cascader')).toBeDefined()
    // 同键稳定返回同一组件对象（映射表为常量）。
    expect(getFieldWidget('richtext')).toBe(getFieldWidget('richtext'))
  })
})

describe('FormRendererBody 渲染主体', () => {
  it('按计划渲染分区 / 分组 / 跨列 / 明细与计数', () => {
    const wrapper = mount(FormRendererBody, {
      props: {
        mode: 'edit',
        plan: buildPlan(),
        modelValue: { name: '甲' },
        details: { lines: [{ name: 'P1' }] },
        permissions: {},
      },
      global: { stubs: { DataTable: true } },
    })
    const body = wrapper.find('[data-test="renderer-body"]')
    expect(body.attributes('data-subpackage')).toBe('renderer')
    expect(body.attributes('data-mode')).toBe('edit')
    expect(wrapper.find('[data-test="renderer-section-s1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="renderer-section-s1"]').attributes('data-columns')).toBe('2')
    expect(wrapper.find('[data-test="renderer-field-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="renderer-field-remark"]').attributes('data-colspan')).toBe('true')
    // 停用字段只读保留渲染；失效引用（`absent`）跳过不渲染。
    expect(wrapper.find('[data-test="renderer-field-broken"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="renderer-field-absent"]').exists()).toBe(false)
    expect(wrapper.find('[data-test="renderer-group-g1"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="renderer-detail"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="renderer-counters"]').attributes('data-unknown')).toBe('1')
  })

  it('权限不可见字段不渲染', () => {
    const plan = buildPlan({ remark: { visible: false } })
    expect(plan.sections[0]?.fields.find((field) => field.key === 'remark')?.visible).toBe(false)
    expect(plan.hiddenFields).toContain('remark')

    const wrapper = mount(FormRendererBody, {
      props: { mode: 'edit', plan },
      global: { stubs: { DataTable: true } },
    })
    expect(wrapper.find('[data-test="renderer-field-name"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="renderer-field-remark"]').exists()).toBe(false)
  })

  it('未知类型回退纯文本并打标', () => {
    const plan: RenderPlan = buildRenderPlan(
      {
        layout: {
          main: {
            labelPosition: 'top',
            sections: [{ key: 's1', title: '', columns: 1, fields: [{ key: 'mystery' }] }],
          },
        },
        fields,
        level: 'tenant',
        source: 'tenant',
        readonly: false,
        fallback: false,
      },
      { mode: 'edit' },
    )
    const wrapper = mount(FormRendererBody, { props: { mode: 'edit', plan } })
    expect(wrapper.find('[data-test="renderer-field-plain-mystery"]').exists()).toBe(true)
  })

  it('字段变更与明细变更上抛事件', async () => {
    const wrapper = mount(FormRendererBody, {
      props: {
        mode: 'edit',
        plan: buildPlan(),
        modelValue: {},
        details: { lines: [] },
        permissions: { remark: { visible: false } },
      },
      global: { stubs: { DataTable: true } },
    })
    const input = wrapper.find('[data-test="renderer-field-name"] input')
    await input.setValue('乙')
    expect(wrapper.emitted('field-change')?.at(-1)).toEqual([{ field: 'name', value: '乙' }])

    await wrapper.find('[data-test="renderer-detail-add-lines"]').trigger('click')
    expect(wrapper.emitted('detail-change')?.at(-1)?.[0]).toMatchObject({ detailKey: 'lines' })
  })

  it('查看态字段只读回显（不渲染输入控件）', () => {
    const wrapper = mount(FormRendererBody, {
      props: {
        mode: 'view',
        plan: { ...buildPlan(), readonly: true },
        modelValue: { name: '甲' },
        permissions: {},
      },
      global: { stubs: { DataTable: true } },
    })
    expect(wrapper.find('[data-test="renderer-field-display"]').exists()).toBe(true)
  })
})

describe('FormRenderer 渲染器件', () => {
  it('占位态降级', () => {
    const wrapper = mount(FormRenderer, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('表单渲染器未就绪')
  })

  it('就绪态渲染主体、暴露能力并透传数据变更', async () => {
    const wrapper = mount(FormRenderer, {
      props: { ready: true, mode: 'edit', modelValue: { name: '甲' }, meta },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    const body = wrapper.find('[data-test="renderer-body"]')
    expect(body.attributes('data-subpackage')).toBe('renderer')
    expect(body.attributes('data-mode')).toBe('edit')

    const vm = wrapper.vm as unknown as {
      validate: () => { valid: boolean }
      getData: () => Record<string, unknown>
      setData: (value: Record<string, unknown>) => void
      getPlan: () => { sections: unknown[] }
    }
    expect(vm.getData()).toEqual({ name: '甲' })
    expect(vm.getPlan().sections).toHaveLength(2)
    vm.setData({ name: '乙' })
    await flushPromises()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([{ name: '乙' }])
  })

  it('注入 jobs 后取数装载并驱动提交', async () => {
    const { jobs, calls } = makeJobs()
    const wrapper = mount(FormRenderer, {
      props: { ready: true, formCode: 'leave', mode: 'edit', recordId: 7, jobs },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(calls).toContain('layout:leave:edit')
    expect(calls).toContain('record:7')

    const vm = wrapper.vm as unknown as { submit: () => Promise<void> }
    await vm.submit()
    expect(calls).toContain('submit')
    expect(wrapper.emitted('submitted')).toBeTruthy()
  })

  it('校验未通过时不请求提交并上抛 field-error', async () => {
    const wrapper = mount(FormRenderer, {
      props: { ready: true, formCode: 'leave', mode: 'edit', meta },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    const vm = wrapper.vm as unknown as { submit: () => Promise<void> }
    await vm.submit()
    expect(wrapper.emitted('submit')).toBeFalsy()
    expect(wrapper.emitted('field-error')).toBeTruthy()
    expect(wrapper.emitted('failed')).toBeTruthy()
  })

  it('未注入 jobs 时提交仅上抛既有 submit 事件（占位口径）', async () => {
    const wrapper = mount(FormRenderer, {
      props: { ready: true, mode: 'create', meta: { ...meta, fields: [] } },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    const vm = wrapper.vm as unknown as { submit: () => Promise<void> }
    await vm.submit()
    expect(wrapper.emitted('submit')).toBeTruthy()
  })

  it('空布局回退提示与只读提示', async () => {
    const wrapper = mount(FormRenderer, {
      props: {
        ready: true,
        mode: 'edit',
        meta: { ...meta, layout: { main: { labelPosition: 'top', sections: [] } }, fallback: true },
      },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="renderer-fallback-hint"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="renderer-empty"]').exists()).toBe(true)
  })

  it('强制只读时提交禁用', async () => {
    const wrapper = mount(FormRenderer, {
      props: { ready: true, mode: 'edit', forceReadOnly: true, meta },
    })
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="renderer-readonly-hint"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="submit"]').attributes('disabled')).toBeDefined()
  })

  it('查看态提交禁用（08_01_02 冻结断言保持）', async () => {
    const wrapper = mount(FormRenderer, { props: { ready: true, mode: 'view' } })
    await vi.dynamicImportSettled()
    expect(wrapper.find('[data-test="submit"]').attributes('disabled')).toBeDefined()
  })
})
