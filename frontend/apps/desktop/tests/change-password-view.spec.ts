/**
 * 自助改密页用例（04_01 · Kiwi 2325）：强制改密提示 / 表单校验 / 提交成功（会话清理与回跳）/ 失败提示。
 */
// kiwi_id: 2325

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage } from 'element-plus'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { changePassword } from '@/api/identity'
import { useSessionStore } from '@/stores/session'
import ChangePasswordView from '@/views/ChangePasswordView.vue'

vi.mock('@/api/identity', () => ({
  changePassword: vi.fn(),
}))

const changeMock = vi.mocked(changePassword)

/** 构造最小路由（含回跳目标）。 */
function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/', name: 'Home', component: { template: '<div />' } },
      { path: '/change-password', name: 'ChangePassword', component: { template: '<div />' } },
      { path: '/org/users', name: 'Users', component: { template: '<div />' } },
    ],
  })
}

/**
 * 挂载改密页。
 *
 * @param mustChange 是否处于强制改密态。
 * @param query 附加查询串。
 */
async function mountView(
  mustChange = true,
  query = '',
): Promise<{ wrapper: VueWrapper; router: Router; session: ReturnType<typeof useSessionStore> }> {
  const pinia = createPinia()
  setActivePinia(pinia)
  const session = useSessionStore(pinia)
  session.user = {
    id: '1',
    username: 'admin',
    name: '管理员',
    tenant: 'platform',
    locale: null,
    timezone: null,
    must_change_password: mustChange,
  }
  session.token = 'token'
  const router = makeRouter()
  await router.push(query === '' ? '/change-password' : `/change-password?${query}`)
  await router.isReady()
  const wrapper = mount(ChangePasswordView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  return { wrapper, router, session }
}

/**
 * 填写三个口令字段。
 *
 * @param wrapper 组件包装器。
 * @param oldValue 旧口令。
 * @param newValue 新口令。
 * @param confirmValue 确认口令。
 */
async function fill(wrapper: VueWrapper, oldValue: string, newValue: string, confirmValue: string): Promise<void> {
  await wrapper.find('[data-test="change-password-old"] input').setValue(oldValue)
  await wrapper.find('[data-test="change-password-new"] input').setValue(newValue)
  await wrapper.find('[data-test="change-password-confirm"] input').setValue(confirmValue)
}

beforeEach(() => {
  changeMock.mockReset()
  changeMock.mockResolvedValue({ changed: true, revoked_sessions: 0 })
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
})

describe('ChangePasswordView（04_01）', () => {
  it('强制改密态：展示提示；普通改密态不展示', async () => {
    const forced = await mountView(true)
    expect(forced.wrapper.find('[data-test="change-password-forced"]').exists()).toBe(true)
    forced.wrapper.unmount()

    const normal = await mountView(false)
    expect(normal.wrapper.find('[data-test="change-password-forced"]').exists()).toBe(false)
    normal.wrapper.unmount()
  })

  it('表单校验：空字段 / 两次不一致 / 新旧相同', async () => {
    const { wrapper } = await mountView()
    await wrapper.find('form').trigger('submit')
    expect(wrapper.find('[data-test="change-password-error"]').text()).toContain('请填写旧口令与新口令')

    await fill(wrapper, 'old-pass', 'NewPass@1', 'NewPass@2')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.find('[data-test="change-password-error"]').text()).toContain('两次输入的新口令不一致')

    await fill(wrapper, 'SamePass@1', 'SamePass@1', 'SamePass@1')
    await wrapper.find('form').trigger('submit')
    expect(wrapper.find('[data-test="change-password-error"]').text()).toContain('新口令不能与旧口令相同')
    expect(changeMock).not.toHaveBeenCalled()
  })

  it('提交成功：清除强制改密标记、提示会话失效数并回跳', async () => {
    changeMock.mockResolvedValue({ changed: true, revoked_sessions: 2 })
    const { wrapper, router, session } = await mountView(true, 'redirect=%2Forg%2Fusers')

    await fill(wrapper, 'old-pass', 'NewPass@123', 'NewPass@123')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(changeMock).toHaveBeenCalledWith({ old_password: 'old-pass', new_password: 'NewPass@123' })
    expect(session.user?.must_change_password).toBe(false)
    expect(ElMessage.success).toHaveBeenCalledWith('口令已修改，其它 2 个会话已失效')
    expect(router.currentRoute.value.path).toBe('/org/users')
  })

  it('提交成功：无其它会话失效时提示简化文案', async () => {
    const { wrapper } = await mountView()
    await fill(wrapper, 'old-pass', 'NewPass@123', 'NewPass@123')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(ElMessage.success).toHaveBeenCalledWith('口令已修改')
  })

  it('提交失败：按 Error / 非 Error 回显', async () => {
    changeMock.mockRejectedValueOnce(new Error('旧口令不正确'))
    const { wrapper } = await mountView()
    await fill(wrapper, 'bad', 'NewPass@123', 'NewPass@123')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="change-password-error"]').text()).toContain('旧口令不正确')

    changeMock.mockRejectedValueOnce('boom')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(wrapper.find('[data-test="change-password-error"]').text()).toContain('口令修改失败')
  })

  it('用户概要为空的降级：不写入强制改密标记', async () => {
    const { wrapper, session } = await mountView()
    session.user = null
    await fill(wrapper, 'old-pass', 'NewPass@123', 'NewPass@123')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(session.user).toBeNull()
  })
})
