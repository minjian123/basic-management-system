/** 宿主统一提示用例（05_02 / Kiwi 2230）：会话失效 / 强制改密 / 一般错误三类提示经统一通道发出。 */
// kiwi_id: 2230

import { ElMessage } from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('element-plus', () => ({ ElMessage: { warning: vi.fn(), error: vi.fn() } }))

import {
  MENU_LOAD_ERROR_MESSAGE,
  MUST_CHANGE_PASSWORD_MESSAGE,
  SESSION_EXPIRED_MESSAGE,
  notifyError,
  notifyMustChangePassword,
  notifySessionExpired,
} from '@/utils/feedback'

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

describe('notifyMustChangePassword（Kiwi 2230）', () => {
  it('发出强制改密提示（固定文案）', () => {
    notifyMustChangePassword()
    expect(ElMessage.warning).toHaveBeenCalledWith(MUST_CHANGE_PASSWORD_MESSAGE)
  })
})

describe('notifyError（Kiwi 2230）', () => {
  it('发出一般错误提示（走 error 通道）', () => {
    notifyError(MENU_LOAD_ERROR_MESSAGE)
    expect(ElMessage.error).toHaveBeenCalledWith(MENU_LOAD_ERROR_MESSAGE)
  })
})
