// kiwi_id: 983
/** 样例占位数据服务用例：筛选 / 分页 / 增删改 / 未命中抛错 / 零延迟注入。 */

import { BaseError } from '@bms/core'
import { describe, expect, it } from 'vitest'

import type { SampleInput } from '../src/domain'
import { SampleDataService } from '../src/services/sample-service'

/** 新建入参。 */
const INPUT: SampleInput = {
  name: '测试记录',
  category: 'other',
  priority: 'normal',
  amount: 100,
  owner: '测试员',
  status: 'draft',
  remark: '',
}

describe('样例占位数据服务（Kiwi 982）', () => {
  it('列表默认返回首页数据并按页长切分', async () => {
    const service = new SampleDataService({ delayMs: 0 })
    const page = await service.list({ page: 1, size: 10 })
    expect(page.total).toBe(23)
    expect(page.list).toHaveLength(10)
    expect(page.list[0]?.code).toBe('SP-0001')
  })

  it('关键词与分类 / 状态筛选生效（并集为空）', async () => {
    const service = new SampleDataService({ delayMs: 0 })
    expect((await service.list({ keyword: '服务器', page: 1, size: 10 })).total).toBe(1)
    expect((await service.list({ category: 'hardware', page: 1, size: 50 })).total).toBe(7)
    expect((await service.list({ status: 'active', page: 1, size: 50 })).total).toBe(9)
    expect((await service.list({ keyword: '不存在', page: 1, size: 10 })).total).toBe(0)
  })

  it('详情未命中抛未登记错误', async () => {
    const service = new SampleDataService({ delayMs: 0 })
    await expect(service.get('s999')).rejects.toBeInstanceOf(BaseError)
  })

  it('新建 / 更新 / 删除改内存集并维护时间戳', async () => {
    const service = new SampleDataService({ delayMs: 0 })
    const created = await service.create(INPUT)
    expect(created.code).toBe('SP-0024')
    expect((await service.list({ keyword: '测试记录', page: 1, size: 10 })).total).toBe(1)

    const updated = await service.update(created.id, { ...INPUT, name: '改名记录' })
    expect(updated.name).toBe('改名记录')
    expect((await service.get(created.id)).name).toBe('改名记录')

    await service.remove(created.id)
    await expect(service.get(created.id)).rejects.toBeInstanceOf(BaseError)
  })

  it('可关闭种子数据（空集）', async () => {
    const service = new SampleDataService({ delayMs: 0, seed: false })
    expect((await service.list({ page: 1, size: 10 })).total).toBe(0)
  })
})
