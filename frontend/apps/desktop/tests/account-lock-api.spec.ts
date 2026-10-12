// kiwi_id: 2277
/**
 * 账号锁定端点封装用例（`02_02` · Kiwi 2277）：
 * 服务段寻址（platform）、路径 / 方法 / 载荷透传，以及列表缺省空参数（`params = {}`）分支。
 */

import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getAccountLock, listAccountLocks, lockAccount, unlockAccount } from '@/api/accountLock'

const getMock = vi.fn()
const postMock = vi.fn()
const putMock = vi.fn()

vi.mock('@/api/request', () => ({
  get: (...args: unknown[]) => getMock(...args),
  post: (...args: unknown[]) => postMock(...args),
  put: (...args: unknown[]) => putMock(...args),
}))

beforeEach(() => {
  getMock.mockReset()
  postMock.mockReset()
  putMock.mockReset()
})

describe('账号锁定端点封装（02_02）', () => {
  it('列表：platform 服务段只读寻址（缺省空参数与全量筛选）', async () => {
    // 缺省参数分支：`params = {}` 展开为空对象（不外传 undefined）
    await listAccountLocks()
    expect(getMock).toHaveBeenCalledWith('platform', '/account-locks', {})

    const params = { kw: 'zhang', lock_type: 'manual', active: true, user_id: '1001', page: 2, size: 20 }
    await listAccountLocks(params)
    expect(getMock).toHaveBeenCalledWith('platform', '/account-locks', params)
  })

  it('详情：按主键 GET `/account-locks/{id}`', async () => {
    await getAccountLock('1001')
    expect(getMock).toHaveBeenCalledWith('platform', '/account-locks/1001')
  })

  it('手动锁定：POST 提交请求体（无路径参数）', async () => {
    const body = { user_id: 1001, reason: '连续违规操作' }
    await lockAccount(body)
    expect(postMock).toHaveBeenCalledWith('platform', '/account-locks', body)
  })

  it('解锁：PUT `/account-locks/{id}/unlock` 且不携带请求体', async () => {
    await unlockAccount('1001')
    expect(putMock).toHaveBeenCalledWith('platform', '/account-locks/1001/unlock')
  })
})
