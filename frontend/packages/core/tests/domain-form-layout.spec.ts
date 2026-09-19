// kiwi_id: 771
/** 布局元数据领域纯函数用例（08-6-1）：归一 / 回退 / 层级 / 结构操作 / 列名 / 校验 / 脏比对。 */

import { describe, expect, it } from 'vitest'

import {
  DEFAULT_LAYOUT_COLUMNS,
  DEFAULT_SECTION_KEY,
  EXT_FIELD_TYPES,
  addSection,
  canDragField,
  checkExtField,
  collectFieldKeys,
  countLayoutFields,
  defaultLayout,
  emptyLayout,
  extColumnName,
  extFieldNeedsOptions,
  findDisabledFields,
  findDuplicateFields,
  findUnknownFields,
  hasField,
  insertField,
  isLayoutDirty,
  isLayoutEmpty,
  layoutEqual,
  locateField,
  moveField,
  newSectionKey,
  normalizeColumns,
  normalizeFieldRef,
  normalizeFieldRefs,
  normalizeLayout,
  normalizeSelection,
  removeField,
  removeSection,
  renameSection,
  resolveEffectiveLayout,
  resolveExtDdlStatus,
  resolveLayoutForLevel,
  resolveLevelReadOnly,
  resolveRestoreTarget,
  setDetailColumns,
  setLabelPosition,
  setLabelWidth,
  setQueryFields,
  setSectionColumns,
  toRenderMetadata,
  toggleColSpan,
  validateLayout,
  type FormField,
  type FormLayout,
} from '../src'

/** 字段清单样例（含停用与建列失败）。 */
const FIELDS: FormField[] = [
  { key: 'name', label: '姓名', type: 'text', group: 'platform', status: 'active' },
  { key: 'remark', label: '备注', type: 'longtext', group: 'platform', status: 'active' },
  { key: 'project_no', label: '项目编号', type: 'text', group: 'tenant', status: 'active' },
  { key: 'ext_off', label: '停用字段', type: 'text', group: 'tenant', disabled: true },
  { key: 'ext_broken', label: '建列失败', type: 'text', group: 'tenant', status: 'failed' },
]

/** 布局工厂。 */
function layoutOf(keys: readonly string[], columns: 1 | 2 | 3 = 2): FormLayout {
  return {
    main: {
      labelPosition: 'top',
      sections: [{ key: 's1', title: '基本信息', columns, fields: keys.map((key) => ({ key })) }],
    },
  }
}

describe('布局归一与空布局', () => {
  it('空布局与空判定', () => {
    const layout = emptyLayout()
    expect(layout.main.labelPosition).toBe('top')
    expect(layout.main.sections).toEqual([])
    expect(isLayoutEmpty(layout)).toBe(true)
    expect(isLayoutEmpty(undefined)).toBe(true)
    expect(isLayoutEmpty(layoutOf(['name']))).toBe(false)
    expect(
      isLayoutEmpty({ main: { labelPosition: 'top', sections: [{ key: 's1', title: '', columns: 2, fields: [] }] } }),
    ).toBe(true)
  })

  it('空布局回退按字段顺序生成默认栅格并排除不可用字段', () => {
    const layout = defaultLayout(FIELDS)
    expect(layout.main.sections).toHaveLength(1)
    expect(layout.main.sections[0]?.key).toBe(DEFAULT_SECTION_KEY)
    expect(layout.main.sections[0]?.columns).toBe(DEFAULT_LAYOUT_COLUMNS)
    expect(layout.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark', 'project_no'])

    expect(defaultLayout(FIELDS, 1).main.sections[0]?.columns).toBe(1)
  })

  it('装载归一：缺省项补确定值、失败引用不抛错', () => {
    const normalized = normalizeLayout({
      main: {
        labelPosition: 'left',
        labelWidth: 120.7,
        sections: [
          {
            key: '',
            title: '甲',
            columns: 9,
            fields: [{ key: 'name' }, { key: '' }, 'name', { key: 'remark', colSpan: true }],
          },
        ],
      },
      query: { fields: ['name', 'name', 'remark'] },
      detail: { columns: [{ key: 'project_no', width: 9999 }, 'name', 'name'] },
      dictAdvanced: { fields: ['name'], operators: ['eq', ''], scheme: 'default', columns: ['remark'] },
    })
    expect(normalized.main.labelPosition).toBe('left')
    expect(normalized.main.labelWidth).toBe(120)
    const section = normalized.main.sections[0]
    expect(section?.key).toBe('section-1')
    expect(section?.columns).toBe(DEFAULT_LAYOUT_COLUMNS)
    expect(section?.fields).toEqual([{ key: 'name' }, { key: 'remark', colSpan: true }])
    expect(normalized.query?.fields).toEqual(['name', 'remark'])
    expect(normalized.detail?.columns).toEqual([{ key: 'project_no', width: 800 }, { key: 'name' }])
    expect(normalized.dictAdvanced).toEqual({
      fields: ['name'],
      operators: ['eq'],
      scheme: 'default',
      columns: ['remark'],
    })

    expect(normalizeLayout(undefined).main.sections).toEqual([])
  })

  it('分组归一（缺键自动生成、字段引用去重）', () => {
    const normalized = normalizeLayout({
      main: {
        labelPosition: 'top',
        sections: [
          {
            key: 's1',
            title: '基本信息',
            columns: 2,
            groups: [{ key: '', title: '基础', fields: ['name', 'name'] }],
            fields: [],
          },
        ],
      },
    })
    const group = normalized.main.sections[0]?.groups?.[0]
    expect(group?.key).toBe('section-1-g1')
    expect(group?.fields).toEqual([{ key: 'name' }])
  })

  it('字段引用与列数归一', () => {
    expect(normalizeFieldRef('name')).toEqual({ key: 'name' })
    expect(normalizeFieldRef({ key: 'name', colSpan: true })).toEqual({ key: 'name', colSpan: true })
    expect(normalizeFieldRef('')).toBeUndefined()
    expect(normalizeFieldRefs(['a', { key: 'b', colSpan: true }, '', 'a'])).toEqual([
      { key: 'a' },
      { key: 'b', colSpan: true },
    ])
    expect(normalizeColumns(1)).toBe(1)
    expect(normalizeColumns('2')).toBe(2)
    expect(normalizeColumns(4)).toBe(3)
    expect(normalizeColumns(undefined)).toBe(3)
  })

  it('字段键收集与计数覆盖主表 / 查询区 / 明细区 / 高级查询', () => {
    const layout = normalizeLayout({
      main: {
        labelPosition: 'top',
        sections: [
          {
            key: 's1',
            title: '',
            columns: 2,
            fields: ['name', 'remark'],
            groups: [{ key: 'g1', title: '', fields: ['project_no'] }],
          },
        ],
      },
      query: { fields: ['name'] },
      detail: { columns: [{ key: 'remark' }] },
      dictAdvanced: { fields: ['project_no'], columns: ['remark'] },
    })
    expect(collectFieldKeys(layout)).toEqual(['name', 'remark', 'project_no'])
    expect(countLayoutFields(layout)).toBe(3)
  })
})

describe('结构操作（不可变与幂等）', () => {
  it('插入幂等、定位与存在判定', () => {
    const layout = layoutOf(['name'])
    const inserted = insertField(layout, 'remark')
    expect(inserted).not.toBe(layout)
    expect(inserted.main.sections[0]?.fields.map((field) => field.key)).toEqual(['name', 'remark'])
    expect(insertField(inserted, 'remark')).toBe(inserted)
    expect(insertField(inserted, '')).toBe(inserted)
    expect(hasField(inserted, 'name')).toBe(true)
    expect(hasField(inserted, 'absent')).toBe(false)
    expect(locateField(inserted, 'remark')).toEqual({ sectionKey: 's1', index: 1 })
    expect(locateField(inserted, 'absent')).toBeUndefined()
  })

  it('插入到不存在分区时自动建分区', () => {
    const layout = insertField(layoutOf([]), 'name', 's9')
    expect(layout.main.sections).toHaveLength(2)
    expect(layout.main.sections[1]?.key).toBe('s9')
    expect(layout.main.sections[1]?.fields.map((field) => field.key)).toEqual(['name'])
  })

  it('移动：跨分区与分区内排序同一条路径（移出后插入）', () => {
    const layout = normalizeLayout({
      main: {
        labelPosition: 'top',
        sections: [
          { key: 's1', title: '', columns: 2, fields: ['a', 'b', 'c'] },
          { key: 's2', title: '', columns: 2, fields: ['d'] },
        ],
      },
    })
    const moved = moveField(layout, 'a', 's2', 1)
    expect(moved.main.sections[0]?.fields.map((field) => field.key)).toEqual(['b', 'c'])
    expect(moved.main.sections[1]?.fields.map((field) => field.key)).toEqual(['d', 'a'])

    const reordered = moveField(layout, 'a', 's1', 2)
    expect(reordered.main.sections[0]?.fields.map((field) => field.key)).toEqual(['b', 'c', 'a'])

    const appended = moveField(layout, 'a', 's1')
    expect(appended.main.sections[0]?.fields.map((field) => field.key)).toEqual(['b', 'c', 'a'])
    expect(moveField(layout, 'absent', 's1')).toBe(layout)
  })

  it('移动时目标索引越界夹取', () => {
    const layout = layoutOf(['a', 'b'])
    expect(moveField(layout, 'a', 's1', 99).main.sections[0]?.fields.map((field) => field.key)).toEqual(['b', 'a'])
    expect(moveField(layout, 'b', 's1', -5).main.sections[0]?.fields.map((field) => field.key)).toEqual(['b', 'a'])
  })

  it('移出字段与跨列翻转', () => {
    const layout = layoutOf(['name', 'remark'])
    const removed = removeField(layout, 'name')
    expect(removed.main.sections[0]?.fields.map((field) => field.key)).toEqual(['remark'])
    expect(removeField(layout, 'absent')).toBe(layout)

    const spanned = toggleColSpan(layout, 'name')
    expect(spanned.main.sections[0]?.fields[0]?.colSpan).toBe(true)
    expect(toggleColSpan(spanned, 'name').main.sections[0]?.fields[0]?.colSpan).toBeUndefined()
    expect(toggleColSpan(layout, 'absent')).toBe(layout)
  })

  it('分区增删改（删分区连带引用、末分区删除后仍合法）', () => {
    const layout = layoutOf(['name'], 2)
    const renamed = renameSection(layout, 's1', '扩展信息')
    expect(renamed.main.sections[0]?.title).toBe('扩展信息')
    expect(renameSection(layout, 'absent', 'x')).toBe(layout)

    const columned = setSectionColumns(layout, 's1', 3)
    expect(columned.main.sections[0]?.columns).toBe(3)
    expect(setSectionColumns(layout, 'absent', 3)).toBe(layout)

    const added = addSection(layout, undefined, '新增分区', 1)
    expect(added.key).toBe('section-2')
    expect(added.layout.main.sections).toHaveLength(2)
    expect(added.layout.main.sections[1]?.columns).toBe(1)
    expect(addSection(layout, 's1').key).toBe('')
    expect(addSection(added.layout).key).toBe('section-3')

    const removedSection = removeSection(added.layout, added.key)
    expect(removedSection.main.sections).toHaveLength(1)
    expect(removeSection(layout, 'absent')).toBe(layout)

    const single = {
      main: {
        labelPosition: 'top' as const,
        sections: [{ key: 's1', title: '', columns: 2 as const, fields: [{ key: 'name' }] }],
      },
    }
    const wiped = removeSection(single, 's1')
    expect(wiped.main.sections).toEqual([])
    expect(isLayoutEmpty(wiped)).toBe(true)
  })

  it('新分区键不冲突', () => {
    const layout = normalizeLayout({
      main: {
        labelPosition: 'top',
        sections: [
          { key: 'section-2', title: '', columns: 2, fields: [] },
          { key: 'section-1', title: '', columns: 2, fields: [] },
        ],
      },
    })
    expect(newSectionKey(layout)).toBe('section-3')
  })

  it('标签位置与宽度、查询区与明细区归一', () => {
    const layout = layoutOf(['name'])
    expect(setLabelPosition(layout, 'left').main.labelPosition).toBe('left')
    expect(setLabelPosition(layout, 'top').main.labelPosition).toBe('top')
    expect(setLabelWidth(layout, -10).main.labelWidth).toBe(0)
    expect(setLabelWidth(layout, 250).main.labelWidth).toBe(250)
    expect(setLabelWidth(layout, 'x').main.labelWidth).toBe(100)

    expect(setQueryFields(layout, ['name', 'name', 'remark']).query?.fields).toEqual(['name', 'remark'])
    expect(setQueryFields(layout, []).query).toBeUndefined()
    expect(setDetailColumns(layout, [{ key: 'a', width: 10 }, 'a', 'b']).detail?.columns).toEqual([
      { key: 'a', width: 40 },
      { key: 'b' },
    ])
    expect(setDetailColumns(layout, []).detail).toBeUndefined()
  })

  it('选中项归一', () => {
    expect(normalizeSelection({ kind: 'field', key: 'name' })).toEqual({ kind: 'field', key: 'name' })
    expect(normalizeSelection({ kind: 'section', key: '' })).toBeNull()
    expect(normalizeSelection(null)).toBeNull()
    expect(normalizeSelection(undefined)).toBeNull()
  })
})

describe('层级解析与回退', () => {
  it('层级只读判定（平台默认恒只读）', () => {
    expect(resolveLevelReadOnly('platform', true)).toBe(true)
    expect(resolveLevelReadOnly('platform', false)).toBe(true)
    expect(resolveLevelReadOnly('tenant', true)).toBe(false)
    expect(resolveLevelReadOnly('tenant', false)).toBe(true)
    expect(resolveLevelReadOnly('role', true)).toBe(false)
    expect(resolveLevelReadOnly('role', true, true)).toBe(true)
  })

  it('恢复默认逐级回退', () => {
    expect(resolveRestoreTarget('role')).toEqual({ level: 'role', remove: true, fallbackTo: 'tenant' })
    expect(resolveRestoreTarget('tenant')).toEqual({ level: 'tenant', remove: true, fallbackTo: 'platform' })
    expect(resolveRestoreTarget('platform')).toEqual({ level: 'platform', remove: true, fallbackTo: 'empty' })
  })

  it('按层级解析（角色 → 租户 → 平台；皆无为空）', () => {
    const levels = { platform: layoutOf(['name']), tenant: layoutOf(['name', 'remark']) }
    expect(resolveLayoutForLevel(levels, 'role').source).toBe('tenant')
    expect(resolveLayoutForLevel(levels, 'tenant').source).toBe('tenant')
    expect(resolveLayoutForLevel({ platform: layoutOf(['name']) }, 'tenant').source).toBe('platform')
    expect(resolveLayoutForLevel({}, 'role').source).toBe('empty')
    expect(resolveLayoutForLevel(undefined, 'role')).toEqual({ layout: undefined, source: 'empty' })
  })

  it('空布局不参与命中（视为缺失）', () => {
    expect(resolveLayoutForLevel({ tenant: emptyLayout(), platform: layoutOf(['name']) }, 'tenant').source).toBe(
      'platform',
    )
  })

  it('生效布局含空布局回退与只读判定', () => {
    const effective = resolveEffectiveLayout({ levels: {}, level: 'tenant', fields: FIELDS })
    expect(effective.fallback).toBe(true)
    expect(effective.source).toBe('empty')
    expect(effective.layout.main.sections[0]?.fields.map((field) => field.key)).toEqual([
      'name',
      'remark',
      'project_no',
    ])
    expect(effective.readonly).toBe(false)

    const readonlyEffective = resolveEffectiveLayout({ levels: {}, level: 'platform', fields: FIELDS })
    expect(readonlyEffective.readonly).toBe(true)

    const noManage = resolveEffectiveLayout({ levels: {}, level: 'tenant', fields: FIELDS, hasManage: false })
    expect(noManage.readonly).toBe(true)

    const forced = resolveEffectiveLayout({ levels: {}, level: 'tenant', fields: FIELDS, readOnly: true })
    expect(forced.readonly).toBe(true)
  })

  it('渲染输入与生效布局同形', () => {
    const effective = resolveEffectiveLayout({
      levels: { tenant: layoutOf(['name', 'remark']) },
      level: 'tenant',
      fields: FIELDS,
    })
    const metadata = toRenderMetadata(effective)
    expect(metadata).toEqual(effective)
    expect(layoutEqual(metadata.layout, effective.layout)).toBe(true)
    expect(metadata.fields).toEqual(effective.fields)
  })
})

describe('失效引用、校验与脏比对', () => {
  it('失效 / 停用 / 重复引用识别', () => {
    const layout = normalizeLayout({
      main: {
        labelPosition: 'top',
        sections: [
          { key: 's1', title: '', columns: 2, fields: ['name', 'absent_key'] },
          { key: 's2', title: '', columns: 2, fields: ['name', 'ext_off', 'ext_broken'] },
        ],
      },
    })
    expect(findUnknownFields(layout, FIELDS)).toEqual(['absent_key'])
    expect(findDisabledFields(layout, FIELDS)).toEqual(['ext_off', 'ext_broken'])
    expect(findDuplicateFields(layout)).toEqual(['name'])
  })

  it('校验（引用失效 / 停用 / 重复 / 空分区）逐项入错', () => {
    const layout = normalizeLayout({
      main: {
        labelPosition: 'top',
        sections: [
          { key: 's1', title: '', columns: 2, fields: ['name', 'absent_key'] },
          { key: 's2', title: '空分区', columns: 2, fields: [] },
        ],
      },
    })
    const result = validateLayout(layout, FIELDS)
    expect(result.valid).toBe(false)
    expect(result.errors.map((issue) => issue.kind).sort()).toEqual(['empty-section', 'unknown-field'])
    expect(result.message).toContain('字段引用失效')

    expect(validateLayout(layoutOf(['name', 'remark']), FIELDS)).toEqual({ valid: true, errors: [], message: '' })
  })

  it('脏比对（键序无关、基线缺失不脏）', () => {
    const layout = layoutOf(['name', 'remark'])
    expect(layoutEqual(layout, layoutOf(['name', 'remark']))).toBe(true)
    expect(layoutEqual(layout, layoutOf(['remark', 'name']))).toBe(false)
    expect(layoutEqual(undefined, undefined)).toBe(true)
    expect(layoutEqual(layout, undefined)).toBe(false)

    expect(isLayoutDirty(layout, undefined)).toBe(false)
    expect(isLayoutDirty(layout, layoutOf(['name', 'remark']))).toBe(false)
    expect(isLayoutDirty(layout, layoutOf(['name']))).toBe(true)
  })
})

describe('自建字段与可拖入', () => {
  it('列名派生（驼峰 / 连字符 / 空格 / 非法字符）', () => {
    expect(extColumnName('projectNo')).toBe('ext_project_no')
    expect(extColumnName('project-no')).toBe('ext_project_no')
    expect(extColumnName('project no')).toBe('ext_project_no')
    expect(extColumnName('项目编号')).toBe('ext_')
    expect(extColumnName('a.b.c')).toBe('ext_a_b_c')
    expect(extColumnName('__x__')).toBe('ext_x')
  })

  it('自建字段校验（名称 / 类型 / 唯一性 / 选项集）', () => {
    expect(EXT_FIELD_TYPES).toContain('multi_select')
    expect(EXT_FIELD_TYPES).not.toContain('richtext')
    expect(extFieldNeedsOptions('select')).toBe(true)
    expect(extFieldNeedsOptions('multi_select')).toBe(true)
    expect(extFieldNeedsOptions('text')).toBe(false)

    expect(checkExtField({ name: '  ', type: 'text' }, [])).toMatchObject({ valid: false })
    expect(checkExtField({ name: 'no', type: 'richtext' }, []).message).toContain('白名单')
    expect(checkExtField({ name: 'name', type: 'text' }, ['name']).message).toContain('已存在')
    expect(checkExtField({ name: 'no', type: 'select' }, []).message).toContain('选项集')

    const ok = checkExtField({ name: 'projectNo', type: 'select', options: [{ value: 'a', label: '甲' }] }, ['name'])
    expect(ok).toEqual({ valid: true, columnName: 'ext_project_no', message: '' })
  })

  it('DDL 状态文案', () => {
    expect(resolveExtDdlStatus('active')).toBe('已生效')
    expect(resolveExtDdlStatus('failed')).toBe('建列失败')
    expect(resolveExtDdlStatus('pending')).toBe('待建列')
    expect(resolveExtDdlStatus(undefined)).toBe('待建列')
  })

  it('可拖入判定（未注册类型 / 停用 / 建列失败不可拖入）', () => {
    expect(canDragField(FIELDS[0] as FormField, [])).toBe(true)
    expect(canDragField(FIELDS[0] as FormField, ['text'])).toBe(true)
    expect(canDragField(FIELDS[0] as FormField, ['number'])).toBe(false)
    expect(canDragField(FIELDS[3] as FormField, ['text'])).toBe(false)
    expect(canDragField(FIELDS[4] as FormField, ['text'])).toBe(false)
  })
})
