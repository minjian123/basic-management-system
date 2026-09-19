// kiwi_id: 771
/** 表单设计器用例（08_06_01）：投影薄适配 + 四件真实编排 + 拖拽适配 + 分包边界。 */

import type { FormField } from '@bms/core'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import { FormDesigner, toDesignerDrop, toDragPayload, useBaseFormDesigner } from '../src'
import ExtFieldDialog from '../src/components/form-design/ExtFieldDialog.vue'
import FieldPropertyPanel from '../src/components/form-design/FieldPropertyPanel.vue'

/** 字段清单样例。 */
const fields: FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active' },
  { key: 'remark', label: '备注', type: 'longtext', group: 'platform', status: 'active' },
  { key: 'project_no', label: '项目编号', type: 'text', group: 'tenant', status: 'active' },
  { key: 'ext_broken', label: '建列失败', type: 'text', group: 'tenant', status: 'failed' },
]

/** 布局样例。 */
const layout = {
  main: {
    labelPosition: 'top' as const,
    sections: [{ key: 's1', title: '基本信息', columns: 2 as const, fields: [{ key: 'name' }, { key: 'remark' }] }],
  },
}

/** 两级层布局样例。 */
const levels = { tenant: layout, platform: { main: { labelPosition: 'top' as const, sections: [] } } }

/** 处理函数集样例（取数 / 保存 / 发布 / 恢复 / 自建字段 / 重试）。 */
function makeJobs(): {
  jobs: Parameters<ReturnType<typeof useBaseFormDesigner>['setJobs']>[0]
  calls: string[]
} {
  const calls: string[] = []
  return {
    calls,
    jobs: {
      load: async () => {
        calls.push('load')
        return { levels, fields }
      },
      save: async (input) => {
        calls.push(`save:${input.level}`)
        return { recordVersion: 3 }
      },
      publish: async (input) => {
        calls.push(`publish:${input.level}`)
      },
      restore: async (input) => {
        calls.push(`restore:${input.level}`)
      },
      createField: async (input) => {
        calls.push(`create:${input.draft.name}`)
        return { fieldKey: input.draft.name, columnName: `ext_${input.draft.name}`, ddlStatus: 'pending' }
      },
      retryField: async (input) => {
        calls.push(`retry:${input.fieldKey}`)
        return { fieldKey: input.fieldKey, columnName: 'ext_ext_broken', ddlStatus: 'active' }
      },
    },
  }
}

describe('useBaseFormDesigner 投影', () => {
  it('占位态零请求，就绪后经取数装载层级与字段并记基线', async () => {
    const designer = useBaseFormDesigner({ formCode: 'leave', bizName: undefined } as never)
    const { jobs, calls } = makeJobs()
    designer.setJobs(jobs)
    await designer.load()
    expect(calls).toEqual([])
    expect(designer.degraded.value).toBe(true)

    designer.setReady(true)
    await designer.load()
    expect(calls).toEqual(['load'])
    expect(designer.layout.value.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
    expect(designer.dirty.value).toBe(false)
    expect(designer.renderMetadata.value.fields.map((field) => field.key)).toEqual(['name', 'remark', 'project_no', 'ext_broken'])
  })

  it('结构操作与脏判定经投影同步（撤销回不脏）', async () => {
    const designer = useBaseFormDesigner({ ready: true, formCode: 'leave', level: 'tenant', registeredTypes: ['text', 'longtext'] })
    const { jobs } = makeJobs()
    designer.setJobs(jobs)
    await designer.load()

    expect(designer.addField('project_no')).toBe(true)
    expect(designer.dirty.value).toBe(true)
    expect(designer.selected.value).toEqual({ kind: 'field', key: 'project_no' })

    expect(designer.discard()).toBe(true)
    expect(designer.dirty.value).toBe(false)
    expect(designer.layout.value.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
  })

  it('平台默认层级只读（结构操作不动作）', async () => {
    const designer = useBaseFormDesigner({ ready: true, formCode: 'leave', level: 'tenant', registeredTypes: ['text'] })
    const { jobs } = makeJobs()
    designer.setJobs(jobs)
    await designer.load()

    expect(designer.readonly.value).toBe(false)
    expect(designer.setLevel('platform')).toBe(true)
    expect(designer.readonly.value).toBe(true)
    expect(designer.addField('name')).toBe(false)
  })

  it('保存发布恢复默认与自建字段 DDL 重试', async () => {
    const designer = useBaseFormDesigner({ ready: true, formCode: 'leave', level: 'tenant', registeredTypes: ['text', 'longtext'] })
    const { jobs, calls } = makeJobs()
    designer.setJobs(jobs)
    await designer.load()
    designer.addField('project_no')

    await expect(designer.save()).resolves.toEqual({ recordVersion: 3 })
    expect(designer.dirty.value).toBe(false)
    await expect(designer.publish()).resolves.toBe(true)
    await expect(designer.restoreDefault()).resolves.toBe(true)
    expect(calls).toContain('save:tenant')
    expect(calls).toContain('publish:tenant')
    expect(calls).toContain('restore:tenant')

    await expect(designer.createField({ name: '', type: 'text' })).resolves.toBeUndefined()
    await expect(designer.createField({ name: 'no', type: 'text' })).resolves.toMatchObject({ ddlStatus: 'pending' })
    await expect(designer.retryField('ext_broken')).resolves.toMatchObject({ ddlStatus: 'active' })
    expect(calls).toContain('create:no')
    expect(calls).toContain('retry:ext_broken')
  })
})

describe('拖拽适配工具', () => {
  it('同区下移索引减一，跨区不修正', () => {
    expect(toDesignerDrop({ fieldKey: 'a', fromSectionKey: 's1', toSectionKey: 's1', oldIndex: 0, newIndex: 2 })).toEqual({
      fieldKey: 'a',
      fromSectionKey: 's1',
      toSectionKey: 's1',
      index: 1,
      crossZone: false,
    })
    expect(toDesignerDrop({ fieldKey: 'a', fromSectionKey: 's1', toSectionKey: 's2', oldIndex: 0, newIndex: 3 })).toMatchObject({
      index: 3,
      crossZone: true,
    })
    expect(toDesignerDrop({ fieldKey: 'a', fromSectionKey: 's1', toSectionKey: 's1', oldIndex: 2, newIndex: 0 })).toMatchObject({ index: 0 })
  })

  it('阶段载荷映射', () => {
    expect(toDragPayload({ phase: 'start', fieldKey: 'a', sectionKey: 's1' })).toEqual({
      phase: 'start',
      source: 's1',
      target: 's1',
      crossZone: false,
    })
  })
})

describe('FormDesigner 表单设计器', () => {
  it('占位态降级', () => {
    const wrapper = mount(FormDesigner, { props: {} })
    expect(wrapper.find('[data-test="placeholder"]').text()).toContain('表单设计器未就绪')
  })

  it('就绪态渲染三区、字段拖入事件与画布分包', async () => {
    const wrapper = mount(FormDesigner, {
      props: { ready: true, formCode: 'leave', fields, layout, dirty: true },
    })
    expect(wrapper.find('[data-test="form-code"]').text()).toBe('leave')
    expect(wrapper.find('[data-test="dirty"]').exists()).toBe(true)

    await wrapper.find('[data-test="field-name"]').trigger('click')
    expect(wrapper.emitted('add-field')?.[0]).toEqual([{ fieldKey: 'name', sectionKey: 's1' }])
    expect(wrapper.attributes('data-dragging')).toBe('true')

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="designer-canvas"]').attributes('data-subpackage')).toBe('designer')

    await wrapper.find('[data-test="designer-field-name"]').trigger('click')
    expect(wrapper.find('[data-test="properties-selected"]').text()).toContain('name')
    expect(wrapper.emitted('select')?.at(-1)).toEqual([{ kind: 'field', key: 'name' }])
  })

  it('平台默认层级只读禁用编辑', () => {
    const wrapper = mount(FormDesigner, { props: { ready: true, level: 'platform' } })
    expect(wrapper.find('[data-test="save"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="publish"]').attributes('disabled')).toBeDefined()
  })

  it('注入 jobs 后驱动真实编排：拖入 / 跨列 / 列数 / 保存发布 / 自建字段', async () => {
    const { jobs, calls } = makeJobs()
    const wrapper = mount(FormDesigner, {
      props: { ready: true, formCode: 'leave', level: 'tenant', fields, levels, jobs, registeredTypes: ['text', 'longtext'] },
    })
    await flushPromises()
    expect(wrapper.find('[data-test="canvas"]').exists()).toBe(true)

    await wrapper.find('[data-test="field-project_no"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('change')).toBeTruthy()
    expect(wrapper.find('[data-test="field-used-project_no"]').exists()).toBe(true)

    await wrapper.find('[data-test="save"]').trigger('click')
    await flushPromises()
    expect(calls).toContain('save:tenant')
    expect(wrapper.emitted('saved')?.[0]).toEqual([{ recordVersion: 3 }])

    await wrapper.find('[data-test="publish"]').trigger('click')
    await flushPromises()
    expect(calls).toContain('publish:tenant')

    await wrapper.find('[data-test="reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.emitted('reset')).toHaveLength(1)
    expect(calls).toContain('restore:tenant')

    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="ext-submit"]').exists()).toBe(false)
    await wrapper.find('[data-test="create-field"]').trigger('click')
    await vi.dynamicImportSettled()
    await flushPromises()
    expect(wrapper.find('[data-test="ext-dialog"]').exists()).toBe(true)
  })

  it('未注册类型 / 停用字段置灰不可拖入', async () => {
    const wrapper = mount(FormDesigner, {
      props: { ready: true, fields, layout, registeredTypes: ['text'] },
    })
    expect(wrapper.find('[data-test="field-remark"]').attributes('data-draggable')).toBe('false')
    expect(wrapper.find('[data-test="field-ext_broken"]').attributes('disabled')).toBeDefined()
  })

  it('脏数据切换表单 / 层级时上抛拦截', async () => {
    const { jobs } = makeJobs()
    const wrapper = mount(FormDesigner, { props: { ready: true, formCode: 'leave', level: 'tenant', fields, levels, jobs } })
    await flushPromises()
    await wrapper.find('[data-test="field-project_no"]').trigger('click')
    await flushPromises()

    await wrapper.setProps({ formCode: 'user' })
    await flushPromises()
    expect(wrapper.emitted('dirty-block')?.[0]?.[0]).toMatchObject({ action: 'switch-form' })

    await wrapper.setProps({ level: 'role' })
    await flushPromises()
    expect(wrapper.emitted('dirty-block')?.[1]?.[0]).toMatchObject({ action: 'switch-level' })
  })
})

describe('FieldPropertyPanel 字段属性面板', () => {
  it('未选中显示画布全局配置，选中字段显示字段属性', async () => {
    const panel = mount(FieldPropertyPanel, { props: { layout } })
    expect(panel.find('[data-test="property-empty"]').exists()).toBe(true)
    expect(panel.find('[data-test="prop-label-position"]').exists()).toBe(true)

    await panel.find('[data-test="prop-label-position"]').setValue('left')
    expect(panel.emitted('canvas-change')?.[0]).toEqual([{ labelPosition: 'left' }])

    await panel.setProps({ selection: { kind: 'field', key: 'project_no' }, fields })
    expect(panel.find('[data-test="property-field"]').exists()).toBe(true)
    await panel.find('[data-test="prop-required"]').setValue(true)
    expect(panel.emitted('field-change')?.[0]).toEqual([{ fieldKey: 'project_no', patch: { required: true } }])
  })

  it('选中分区显示分区属性，只读时禁用', async () => {
    const panel = mount(FieldPropertyPanel, { props: { selection: { kind: 'section', key: 's1' }, layout } })
    await panel.find('[data-test="prop-section-title"]').setValue('扩展信息')
    expect(panel.emitted('section-change')?.[0]).toEqual([{ sectionKey: 's1', patch: { title: '扩展信息' } }])

    const readonlyPanel = mount(FieldPropertyPanel, {
      props: { selection: { kind: 'field', key: 'name' }, fields, layout, readOnly: true },
    })
    expect(readonlyPanel.find('[data-test="property-readonly"]').exists()).toBe(true)
    await readonlyPanel.find('[data-test="prop-required"]').setValue(true)
    expect(readonlyPanel.emitted('field-change')).toBeUndefined()
  })
})

describe('ExtFieldDialog 自建字段对话框', () => {
  it('列名预览只读、名称与类型校验不通过不可提交', async () => {
    const dialog = mount(ExtFieldDialog, { props: { visible: true, existingKeys: ['name'] } })
    await dialog.find('[data-test="ext-name"]').setValue('projectNo')
    expect(dialog.find('[data-test="ext-column-preview"]').text()).toContain('ext_project_no')

    await dialog.find('[data-test="ext-name"]').setValue('name')
    expect(dialog.find('[data-test="ext-error"]').text()).toContain('已存在')
    expect(dialog.find('[data-test="ext-submit"]').attributes('disabled')).toBeDefined()

    await dialog.find('[data-test="ext-name"]').setValue('')
    expect(dialog.find('[data-test="ext-error"]').text()).toContain('不能为空')
  })

  it('下拉类必填选项集，提交后上抛草稿', async () => {
    const dialog = mount(ExtFieldDialog, { props: { visible: true } })
    await dialog.find('[data-test="ext-name"]').setValue('status')
    await dialog.find('[data-test="ext-type"]').setValue('select')
    await flushPromises()
    expect(dialog.find('[data-test="ext-options"]').exists()).toBe(true)
    expect(dialog.find('[data-test="ext-error"]').text()).toContain('选项集')

    await dialog.find('[data-test="ext-options"]').setValue('a|启用\nb|停用')
    await flushPromises()
    await dialog.find('[data-test="ext-submit"]').trigger('click')
    expect(dialog.emitted('submit')?.[0]?.[0]).toMatchObject({
      name: 'status',
      type: 'select',
      options: [
        { value: 'a', label: '启用' },
        { value: 'b', label: '停用' },
      ],
    })
  })

  it('DDL 状态与重试入口', async () => {
    const dialog = mount(ExtFieldDialog, { props: { visible: true, ddlStatus: 'failed', failedFieldKey: 'ext_broken' } })
    expect(dialog.find('[data-test="ext-ddl-status"]').text()).toBe('建列失败')
    await dialog.find('[data-test="ext-retry"]').trigger('click')
    expect(dialog.emitted('retry')?.[0]).toEqual([{ fieldKey: 'ext_broken' }])
  })
})
