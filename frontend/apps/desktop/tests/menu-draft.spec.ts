/**
 * 菜单记录页草稿纯函数用例（03_03）：载荷组装 / 脏态指纹 / 明细差异 / 校验 / 行排序 / 语言注入。
 */
// kiwi_id: 2338

import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useMenuStore } from '@/stores/menu'
import { currentUserLocale, DEFAULT_LOCALE, ENABLED_LOCALES } from '@/views/system/metaLocale'
import {
  diffButtons,
  diffFields,
  isEmptyDiff,
  linkFingerprint,
  moveDraftRow,
  nextRowSort,
  sortI18n,
  toButtonPayload,
  toFieldPayload,
  validateButtons,
  validateFields,
  type ButtonDraft,
  type FieldDraft,
} from '@/views/system/menu/linkDraft'
import { menuFingerprint, toMenuPayload, validateMenuDraft, type MenuDraft } from '@/views/system/menu/menuDraft'

/**
 * 按钮草稿。
 *
 * @param overrides 覆盖字段。
 * @returns 草稿行。
 */
function button(overrides: Partial<ButtonDraft>): ButtonDraft {
  return {
    form_id: '10',
    permission_id: '20',
    name: '新增',
    type: 'toolbar',
    sort: 10,
    status: 'enabled',
    ...overrides,
  }
}

/**
 * 字段草稿。
 *
 * @param overrides 覆盖字段。
 * @returns 草稿行。
 */
function field(overrides: Partial<FieldDraft>): FieldDraft {
  return {
    form_id: '10',
    field_key: 'username',
    type: 'string',
    sort: 10,
    status: 'enabled',
    i18n: { 'zh-CN': '用户名' },
    ...overrides,
  }
}

/**
 * 菜单草稿。
 *
 * @param overrides 覆盖字段。
 * @returns 草稿。
 */
function menuDraft(overrides: Partial<MenuDraft>): MenuDraft {
  return {
    parent_id: '0',
    path: '/sys/menus',
    component: 'sys/menus',
    icon: 'el:menu',
    sort: 10,
    hidden: false,
    status: 'enabled',
    i18n: { 'zh-CN': '菜单管理', 'en-US': 'Menus' },
    ...overrides,
  }
}

beforeEach(() => {
  setActivePinia(createPinia())
})

describe('菜单本体草稿（03_03）', () => {
  it('载荷组装：空串归一 null、字段去空白、多语言按键排序', () => {
    expect(toMenuPayload(menuDraft({ path: ' /sys/menus ', component: ' ', icon: '' }))).toEqual({
      parent_id: '0',
      path: '/sys/menus',
      component: null,
      icon: null,
      sort: 10,
      hidden: false,
      status: 'enabled',
      i18n: { 'en-US': 'Menus', 'zh-CN': '菜单管理' },
    })
  })

  it('脏态指纹随字段变化', () => {
    const base = menuDraft({})
    expect(menuFingerprint(base)).toBe(menuFingerprint({ ...base }))
    expect(menuFingerprint(base)).not.toBe(menuFingerprint({ ...base, hidden: true }))
  })

  it('本地校验：路径 / 必填语言', () => {
    expect(validateMenuDraft(menuDraft({ path: ' ' }), 'zh-CN')).toBe('路由路径必填')
    expect(validateMenuDraft(menuDraft({ i18n: { 'zh-CN': ' ' } }), 'zh-CN')).toBe('名称（zh-CN）不能为空')
    expect(validateMenuDraft(menuDraft({ i18n: {} }), 'zh-CN')).toBe('名称（zh-CN）不能为空')
    expect(validateMenuDraft(menuDraft({}), 'zh-CN')).toBeUndefined()
  })
})

describe('挂接明细差异（03_03）', () => {
  it('按钮差异：新增 / 更新 / 删除 / 未变', () => {
    const original = [button({ id: '1' }), button({ id: '2', name: '编辑', sort: 20 }), button({ id: '3', permission_id: '30' })]
    const current = [
      button({ id: '1' }),
      button({ id: '2', name: '编辑（改）', sort: 20 }),
      button({ form_id: '10', permission_id: '40', name: '新行', sort: 30 }),
    ]
    const diff = diffButtons(original, current)
    expect(diff.created).toHaveLength(1)
    expect(diff.updated.map((row) => row.id)).toEqual(['2'])
    expect(diff.deleted).toEqual(['3'])
    expect(isEmptyDiff(diff)).toBe(false)
  })

  it('字段差异：多语言 / 类型 / 排序 / 删除', () => {
    const original = [field({ id: '1' }), field({ id: '2', field_key: 'age', type: 'number' })]
    const current = [
      field({ id: '1', i18n: { 'zh-CN': '用户名（新）' } }),
      field({ form_id: '10', field_key: 'email', i18n: { 'zh-CN': '邮箱' } }),
    ]
    const diff = diffFields(original, current)
    expect(diff.created.map((row) => row.field_key)).toEqual(['email'])
    expect(diff.updated.map((row) => row.id)).toEqual(['1'])
    expect(diff.deleted).toEqual(['2'])
    expect(isEmptyDiff({ created: [], updated: [], deleted: [] })).toBe(true)
  })

  it('无差异时为空', () => {
    const rows = [button({ id: '1' })]
    expect(isEmptyDiff(diffButtons(rows, rows))).toBe(true)
  })
})

describe('挂接明细校验（03_03）', () => {
  it('按钮：名称 / 权限码 / 同表重复', () => {
    expect(validateButtons([button({ name: ' ' })])).toBe('按钮名称必填')
    expect(validateButtons([button({ permission_id: '' })])).toBe('按钮挂接权限码必填')
    expect(validateButtons([button({}), button({ name: '编辑' })])).toBe('同一表单内权限码不可重复')
    expect(validateButtons([button({}), button({ form_id: '11' })])).toBeUndefined()
  })

  it('字段：标识 / 类型 / 表单内重复', () => {
    expect(validateFields([field({ field_key: ' ' })])).toBe('字段标识必填')
    expect(validateFields([field({ type: ' ' })])).toBe('字段类型必填')
    expect(validateFields([field({}), field({ i18n: {} })])).toBe('字段标识重复（40205）')
    expect(validateFields([field({}), field({ form_id: '11' })])).toBeUndefined()
  })
})

describe('挂接指纹与行操作（03_03）', () => {
  it('指纹随关联表单 / 按钮 / 字段变化', () => {
    const base = linkFingerprint(['10'], { 10: [button({ id: '1' })] }, { 10: [field({ id: '1' })] })
    expect(linkFingerprint(['10'], { 10: [button({ id: '1' })] }, { 10: [field({ id: '1' })] })).toBe(base)
    expect(linkFingerprint(['10', '11'], { 10: [] }, { 10: [] })).not.toBe(base)
    expect(linkFingerprint(['10'], { 10: [button({ id: '1', name: '改' })] }, { 10: [field({ id: '1' })] })).not.toBe(base)
    expect(linkFingerprint(['10'], { 10: [button({ id: '1' })] }, { 10: [field({ id: '1', type: 'number' })] })).not.toBe(base)
    expect(linkFingerprint([], {}, {})).toBe('##')
  })

  it('下一排序值与上移 / 下移（越界原样返回副本）', () => {
    expect(nextRowSort([])).toBe(10)
    expect(nextRowSort([{ sort: 10 }, { sort: 30 }])).toBe(40)

    const rows = [
      { name: 'a', sort: 10 },
      { name: 'b', sort: 20 },
      { name: 'c', sort: 30 },
    ]
    expect(moveDraftRow(rows, 2, -1).map((row) => row.name)).toEqual(['a', 'c', 'b'])
    expect(moveDraftRow(rows, 2, -1).map((row) => row.sort)).toEqual([10, 20, 30])
    expect(moveDraftRow(rows, 0, 1).map((row) => row.name)).toEqual(['b', 'a', 'c'])
    expect(moveDraftRow(rows, 0, 1).map((row) => row.sort)).toEqual([10, 20, 30])
    expect(moveDraftRow(rows, -1, 1)).toEqual(rows)
    expect(moveDraftRow(rows, 5, 1)).toEqual(rows)
    expect(moveDraftRow(rows, 0, -1)).toEqual(rows)
    expect(moveDraftRow(rows, 2, 1)).toEqual(rows)
  })

  it('载荷组装：新增携带 form_id / field_key，更新不携带', () => {
    expect(toButtonPayload(button({}), true)).toMatchObject({ form_id: '10' })
    expect(toButtonPayload(button({}), false)).not.toHaveProperty('form_id')
    expect(toFieldPayload(field({}), true)).toMatchObject({ form_id: '10', field_key: 'username' })
    expect(toFieldPayload(field({}), false)).not.toHaveProperty('field_key')
  })

  it('多语言映射按键排序', () => {
    expect(sortI18n({ 'en-US': 'User', 'zh-CN': '用户' })).toEqual({ 'en-US': 'User', 'zh-CN': '用户' })
  })

  it('缺省语言键与缺省明细映射的容错', () => {
    // 多语言键缺失按空串比较
    const base = field({ id: '1', i18n: { 'zh-CN': '用户名', 'en-US': '' } })
    const current = field({ id: '1', i18n: { 'zh-CN': '用户名', 'en-US': undefined as unknown as string } })
    expect(diffFields([base], [current])).toEqual({ created: [], updated: [], deleted: [] })

    // 明细映射缺键按空数组
    expect(linkFingerprint(['10', '11'], {}, {})).toBe('10,11##')

    // 指纹中 id 缺省按 new
    expect(linkFingerprint([], { 10: [button({ id: undefined })] }, { 10: [field({ id: undefined })] })).toContain('new')
  })
})

describe('语言注入（03_03）', () => {
  it('启用语言清单与当前用户语言（缺省回退默认语言）', () => {
    expect(ENABLED_LOCALES.map((item) => item.code)).toEqual(['zh-CN', 'en-US'])
    expect(DEFAULT_LOCALE).toBe('zh-CN')
    expect(currentUserLocale()).toBe('zh-CN')

    useMenuStore().locale = 'en-US'
    expect(currentUserLocale()).toBe('en-US')
  })
})
