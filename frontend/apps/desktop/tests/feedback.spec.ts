/** 宿主提示用例（05_02 / Kiwi 2230）：会话失效提示经统一通道发出。 */
// kiwi_id: 2230

import { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn() } }))

import { SESSION_EXPIRED_MESSAGE, notifySessionExpired } from '@/utils/feedback'

beforeEach(() => {
  vi.clearAllMocks()
})

describe('notifySessionExpired（Kiwi 2230）', () => {
  it('发出会话失效提示（缺省文案）', () => {
    notifySessionExpired()
    expect(ElMessage.warning).toHaveBeenCalledWith(SESSION_EXPIRED_MESSAGE)
  })

  it('支持自定义文案', () => {
    notifySessionExpired('自定义')
    expect(ElMessage.warning).toHaveBeenCalledWith('自定义')
  })
})
