// kiwi_id: 2290
/** 字典元数据列表包装（`{items}`）归一兼容用例（02_12）：attrs / query-providers 响应收敛为 `{items:[...]}`。 */

import { BaseDictQuery } from '@bms/core'
import { createDictSourceStub } from '@bms/core/testing'
import { describe, expect, it } from 'vitest'

/** 具体高级查询编排（可实例化）。 */
class DictQueryState extends BaseDictQuery {}

describe('字典元数据包装响应归一（Kiwi 2290）', () => {
  it('loadMeta 兼容 {items:[...]} 包装（attrs + providers）', async () => {
    const query = new DictQueryState()
    const stub = createDictSourceStub({
      loadAttrs: async () => ({
        items: [{ attr_key: 'value', name: '值', data_type: 'text', operators: ['eq'] }],
      }),
      loadProviders: async () => ({
        items: [
          { key: 'builtin', name: '内建', target: 'business', data_source_keys: [], param_schema: {} },
        ],
      }),
    })
    query.setReady(true)
    query.setSource(stub.source)
    query.setDictType('region')
    await query.loadMeta()
    expect(query.attrs).toHaveLength(1)
    expect(query.attrs[0].attrKey).toBe('value')
    expect(query.providers).toHaveLength(1)
    expect(query.providers[0].key).toBe('builtin')
  })

  it('loadMeta 兼容裸数组（旧桩形状，向后兼容）', async () => {
    const query = new DictQueryState()
    const stub = createDictSourceStub({
      loadAttrs: async () => [{ attr_key: 'label', name: '标签', data_type: 'text', operators: ['like'] }],
      loadProviders: async () => [{ key: 'legacy', name: '旧', target: 'business', data_source_keys: [] }],
    })
    query.setReady(true)
    query.setSource(stub.source)
    query.setDictType('region')
    await query.loadMeta()
    expect(query.attrs).toHaveLength(1)
    expect(query.attrs[0].attrKey).toBe('label')
    expect(query.providers).toHaveLength(1)
    expect(query.providers[0].key).toBe('legacy')
  })
})
