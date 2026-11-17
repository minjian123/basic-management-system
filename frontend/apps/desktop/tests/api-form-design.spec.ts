// kiwi_id: 2527
/** 表单定制端点封装与转换器用例（10_02）：11 端点寻址 / 生效字段展平 / 选项集键转换 / 层级与属性归并。 */

import { configureRequestAdapter, type RequestConfig } from '@bms/core'
import { afterEach, describe, expect, it } from 'vitest'

import { listOptionSetKeys } from '@/api/optionSets'
import {
  createExtField,
  deleteAttrs,
  deleteLayout,
  flattenEffectiveField,
  getEffectiveLayout,
  listExtFields,
  listLayouts,
  retryExtField,
  saveAttrs,
  saveLayout,
  toEffectiveLayout,
  toLayerAttrs,
  toLevels,
  updateExtField,
  validateForm,
  type LayoutEffectiveResponse,
  type LayoutLevelRow,
} from '@/api/formDesign'

/** 记录到的请求。 */
let calls: RequestConfig[] = []

/**
 * 装配请求拦截器（记录调用并返回固定值）。
 *
 * @param data 返回值。
 */
function stub<T>(data: T): void {
  configureRequestAdapter({
    request: async <R,>(config: RequestConfig): Promise<R> => {
      calls.push(config)
      return data as unknown as R
    },
  })
}

afterEach(() => {
  calls = []
  configureRequestAdapter({ request: async () => undefined })
})

describe('端点寻址', () => {
  it('布局与属性端点按方法与路径组装', async () => {
    stub({ id: '1' })
    await listLayouts('user')
    await saveLayout({ form_code: 'user', scope: 'tenant', role_id: 0, layout_config: { main: {} } })
    await deleteLayout('9')
    await saveAttrs({ form_code: 'user', scope: 'tenant', role_id: 0, fields: [] })
    await deleteAttrs('8')

    expect(calls[0]).toMatchObject({ method: 'GET', url: '/api/platform/v1/form-design/layouts', params: { form_code: 'user' } })
    expect(calls[1]).toMatchObject({ method: 'PUT', url: '/api/platform/v1/form-design/layouts' })
    expect(calls[1]?.data).toMatchObject({ form_code: 'user', scope: 'tenant', role_id: 0 })
    expect(calls[2]).toMatchObject({ method: 'DELETE', url: '/api/platform/v1/form-design/layouts/9' })
    expect(calls[3]).toMatchObject({ method: 'PUT', url: '/api/platform/v1/form-design/attrs' })
    expect(calls[4]).toMatchObject({ method: 'DELETE', url: '/api/platform/v1/form-design/attrs/8' })
  })

  it('自建字段端点按方法与路径组装', async () => {
    stub({ id: '1' })
    await listExtFields('user')
    await createExtField({ form_code: 'user', field_key: 'project_no', name: '项目编号', type: 'text', sort: 1 })
    await updateExtField('7', { status: 'disabled' })
    await retryExtField('7')

    expect(calls[0]).toMatchObject({ method: 'GET', url: '/api/platform/v1/form-design/fields', params: { form_code: 'user' } })
    expect(calls[1]).toMatchObject({ method: 'POST', url: '/api/platform/v1/form-design/fields' })
    expect(calls[1]?.data).toMatchObject({ field_key: 'project_no', type: 'text' })
    expect(calls[2]).toMatchObject({ method: 'PUT', url: '/api/platform/v1/form-design/fields/7' })
    expect(calls[3]).toMatchObject({ method: 'POST', url: '/api/platform/v1/form-design/fields/7/retry' })
  })

  it('渲染路径端点登录即可并转义表单标识', async () => {
    stub({ valid: true })
    await getEffectiveLayout('user')
    await validateForm('user', { name: '张三' })

    expect(calls[0]).toMatchObject({ method: 'GET', url: '/api/platform/v1/forms/user/layout-effective' })
    expect(calls[1]).toMatchObject({ method: 'POST', url: '/api/platform/v1/forms/user/validate' })
    expect(calls[1]?.data).toEqual({ values: { name: '张三' } })
  })
})

describe('响应转换', () => {
  const response: LayoutEffectiveResponse = {
    layout: { main: { labelPosition: 'top', sections: [] }, query: { fields: ['name'] } },
    fields: [
      {
        key: 'name',
        label: '姓名',
        type: 'text',
        group: 'platform',
        sort: 1,
        status: 'active',
        disabled: false,
        attrs: { required: true, placeholder: '请输入' },
      },
      {
        key: 'level',
        label: '等级',
        type: 'option',
        group: 'tenant',
        sort: 2,
        status: 'pending',
        disabled: true,
        attrs: { optionSetKey: 'bms.demo.level' },
      },
    ],
    level: 'role',
    source: 'tenant',
    readonly: true,
    fallback: false,
    option_sets: [
      {
        option_set_key: 'bms.demo.level',
        items: [
          { value: 'a', label: '甲', color: '#f00', disabled: true, sort: 2 },
          { value: 'b', label: '乙' },
          { value: 'c', label: '丙', color: '' },
        ],
      },
    ],
    permissions: { name: { visible: true, editable: false } },
  }

  it('生效字段属性展平并保留字段元数据', () => {
    const flat = flattenEffectiveField(response.fields![0]!)
    expect(flat).toMatchObject({ key: 'name', type: 'text', group: 'platform', sort: 1, disabled: false })
    expect(flat.attrs).toEqual({ required: true, placeholder: '请输入' })
  })

  it('生效布局转换：属性上提、选项集键转 camelCase、权限直传', () => {
    const layout = toEffectiveLayout(response)
    expect(layout.fields[0]).toMatchObject({ key: 'name', required: true, placeholder: '请输入', group: 'platform' })
    expect(layout.fields[1]).toMatchObject({ key: 'level', group: 'tenant', disabled: true, status: 'pending' })
    expect(layout.optionSets).toEqual([
      {
        optionSetKey: 'bms.demo.level',
        items: [
          { value: 'a', label: '甲', color: '#f00', disabled: true, sort: 2 },
          { value: 'b', label: '乙' },
          { value: 'c', label: '丙' },
        ],
      },
    ])
    expect(layout.permissions).toEqual({ name: { visible: true, editable: false } })
    expect(layout.source).toBe('tenant')
    expect(layout.readonly).toBe(true)
    expect(layout.fallback).toBe(false)
  })

  it('缺省字段与选项集按空集处理', () => {
    const layout = toEffectiveLayout({
      layout: {},
      level: 'role',
      source: 'empty',
      readonly: true,
      fallback: true,
    })
    expect(layout.fields).toEqual([])
    expect(layout.optionSets).toEqual([])
    expect(layout.permissions).toEqual({})
  })

  it('三层布局按层级与角色归并', () => {
    const rows: LayoutLevelRow[] = [
      { id: '1', form_code: 'user', scope: 'platform', role_id: '0', layout_config: { main: { sections: [] } }, status: 'enabled' },
      { id: '2', form_code: 'user', scope: 'tenant', role_id: '0', layout_config: { main: { sections: [] } }, status: 'enabled' },
      { id: '3', form_code: 'user', scope: 'role', role_id: '88', layout_config: { main: { sections: [] } }, status: 'enabled' },
      { id: '4', form_code: 'user', scope: 'role', role_id: '99', layout_config: { main: { sections: [] } }, status: 'enabled' },
    ]
    const levels = toLevels(rows, '88')
    expect(levels.platform).toBeDefined()
    expect(levels.tenant).toBeDefined()
    expect(levels.role).toBe(rows[2]?.layout_config)
    expect(toLevels(rows).role).toBeUndefined()
  })

  it('层内属性按层级与角色过滤', () => {
    const rows = [
      { id: '1', form_code: 'user', scope: 'tenant', role_id: '0', field_key: 'name', attrs: { required: true } },
      { id: '2', form_code: 'user', scope: 'role', role_id: '88', field_key: 'name', attrs: { required: false } },
      { id: '3', form_code: 'user', scope: 'role', role_id: '99', field_key: 'name', attrs: { hidden: true } },
    ]
    expect(toLayerAttrs(rows, 'tenant')).toEqual({ name: { required: true } })
    expect(toLayerAttrs(rows, 'role', '88')).toEqual({ name: { required: false } })
    expect(toLayerAttrs(rows, 'platform')).toEqual({})
  })
})

describe('缺省值兜底', () => {
  it('字段 / 选项集条目 / 属性行缺省时按空值处理', () => {
    const flat = flattenEffectiveField({
      key: 'name',
      label: '姓名',
      type: 'text',
      group: 'platform',
      sort: 1,
      status: 'active',
      disabled: false,
    } as never)
    expect(flat.attrs).toEqual({})

    const layout = toEffectiveLayout({
      layout: {},
      fields: undefined,
      level: 'role',
      source: 'empty',
      readonly: true,
      fallback: true,
      option_sets: [{ option_set_key: 'bms.demo.x' }],
    } as never)
    expect(layout.optionSets[0]?.items).toEqual([])

    expect(
      toLayerAttrs([{ id: '1', form_code: 'user', scope: 'tenant', role_id: '0', field_key: 'name' } as never], 'tenant'),
    ).toEqual({ name: {} })
  })

  it('选项集标识清单取全部已注册项', async () => {
    stub({ items: [{ option_set_key: 'bms.demo.level', items: [] }] })
    await expect(listOptionSetKeys()).resolves.toEqual(['bms.demo.level'])
    expect(calls[0]).toMatchObject({ method: 'GET', url: '/api/platform/v1/option-sets' })
  })
})
