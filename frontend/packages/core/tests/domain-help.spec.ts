// kiwi_id: 2525
/** 帮助领域纯函数（09_02）：线参数 / 上下文键 / 结果归一 / 展示映射。 */

import { describe, expect, it } from 'vitest'

import {
  HELP_LEVEL_LABELS,
  buildHelpQuery,
  emptyHelpResult,
  helpContextKey,
  helpLevelLabel,
  helpSourceLabel,
  normalizeHelpContext,
  normalizeHelpResult,
} from '@bms/core'

describe('帮助领域纯函数（09_02）', () => {
  it('上下文归一与线参数：去空白、空串不传、字段级缺表单键不传字段键', () => {
    const context = normalizeHelpContext({
      productKey: ' platform ',
      moduleKey: ' system ',
      formKey: '',
      fieldKey: ' username ',
      actionCode: ' user:create ',
    })
    expect(context).toEqual({ productKey: 'platform', moduleKey: 'system', fieldKey: 'username', actionCode: 'user:create' })
    expect(buildHelpQuery(context)).toEqual({
      product_key: 'platform',
      module_key: 'system',
      action_code: 'user:create',
    })

    expect(buildHelpQuery({ formKey: 'user', fieldKey: 'username' })).toEqual({
      form_key: 'user',
      field_key: 'username',
    })
    expect(buildHelpQuery({})).toEqual({})
  })

  it('上下文键按五段拼接；空上下文为空键', () => {
    expect(helpContextKey({})).toBe('||||')
    expect(helpContextKey({ moduleKey: 'm', formKey: 'f' })).toBe('|m|f||')
    expect(helpContextKey({ moduleKey: 'm' })).not.toBe(helpContextKey({ moduleKey: 'm', formKey: 'f' }))
  })

  it('结果归一：命中文章、相关内容与分类；脏项剔除', () => {
    const result = normalizeHelpResult({
      matched: true,
      anchor_found: true,
      level: 'form',
      help_key: 'platform:m:f::',
      article: { id: 101, title: '表单帮助', content: '<p>正文</p>', source: 'product' },
      related: [
        { id: 102, title: '更多帮助', source: 'tenant' },
        { id: '', title: '脏项' },
        null,
      ],
      categories: [{ id: 900, name: '快速上手', path: '快速上手' }, { id: 901 }],
    })
    expect(result.matched).toBe(true)
    expect(result.anchorFound).toBe(true)
    expect(result.level).toBe('form')
    expect(result.helpKey).toBe('platform:m:f::')
    expect(result.article).toMatchObject({ id: '101', title: '表单帮助', source: 'product' })
    expect(result.related).toHaveLength(1)
    expect(result.related[0]?.source).toBe('tenant')
    expect(result.categories).toHaveLength(1)
  })

  it('兼容旧后端：缺 anchor_found 时回落 matched；无文章即未命中', () => {
    const legacy = normalizeHelpResult({ matched: true, article: { id: '1', title: 'A', content: 'x' } })
    expect(legacy.anchorFound).toBe(true)

    const noArticle = normalizeHelpResult({ matched: true, anchor_found: true, categories: [] })
    expect(noArticle.matched).toBe(false)
    expect(noArticle.anchorFound).toBe(true)
    expect(noArticle.article).toBeUndefined()

    expect(normalizeHelpResult(null)).toEqual(emptyHelpResult())
    expect(normalizeHelpResult({ article: { id: '2', title: '' } }).matched).toBe(false)
  })

  it('层级 / 来源展示映射（未知回落空串）', () => {
    expect(helpLevelLabel('module')).toBe(HELP_LEVEL_LABELS.module)
    expect(helpLevelLabel(undefined)).toBe('')
    expect(helpSourceLabel('tenant')).toBe('租户维护')
    expect(helpSourceLabel(undefined)).toBe('')
  })
})
