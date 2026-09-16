/** 弹窗容器用例（Kiwi 724）：三态 / 尺寸阶梯 / 脏数据拦截链 / 提交与权限（FormDrawer / FormDialog / ConfirmDialog）。 */

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'

import ConfirmDialog from '@/components/modal/ConfirmDialog.vue'
import FormDialog from '@/components/modal/FormDialog.vue'
import FormDrawer from '@/components/modal/FormDrawer.vue'

import { mountWithPlugins } from './helpers/mount'

// jsdom 缺 ResizeObserver（EP 容器组件需要）
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
if (!('ResizeObserver' in globalThis)) {
  ;(globalThis as Record<string, unknown>).ResizeObserver = ResizeObserverStub
}

const hasPermMock = vi.hoisted(() => vi.fn<(code: string) => boolean>(() => true))
const confirmMock = vi.hoisted(() => vi.fn<(options: unknown) => Promise<boolean>>(async () => true))

vi.mock('@/utils/perm', () => ({ hasPerm: (code: string) => hasPermMock(code) }))
vi.mock('@/utils/useConfirm', () => ({
  useConfirm: () => ({ confirm: (options: unknown) => confirmMock(options) }),
}))

beforeEach(() => {
  hasPermMock.mockReset().mockReturnValue(true)
  confirmMock.mockReset().mockResolvedValue(true)
})

function mountDrawer(props: Record<string, unknown> = {}) {
  return mountWithPlugins(FormDrawer, {
    props: { modelValue: true, ...props },
    global: { stubs: { teleport: true, transition: false } },
  })
}

/** EP Dialog 在 jsdom 下需经 setProps 打开（初始 modelValue=true 不触发渲染） */
async function mountDialog(component: typeof FormDialog | typeof ConfirmDialog, props: Record<string, unknown> = {}) {
  const wrapper = mountWithPlugins(component, {
    props: { modelValue: false, ...props },
    global: { stubs: { teleport: true, transition: false } },
  })
  await wrapper.setProps({ modelValue: true })
  await nextTick()
  return wrapper
}

/** 等待关闭过渡完成（EP 在 afterLeave 后才 emit update:modelValue） */
async function waitClose(wrapper: ReturnType<typeof mountDrawer>): Promise<void> {
  await vi.waitFor(() => {
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })
}

function buttonByText(wrapper: ReturnType<typeof mountDrawer>, text: string) {
  return wrapper.findAll('button').find((button) => button.text().includes(text))
}
describe('弹窗容器（Kiwi 724）', () => {
  it('三态标题：动作词 + 对象名（create / edit / view）', () => {
    expect(mountDrawer({ mode: 'create', title: '用户' }).text()).toContain('新增用户')
    expect(mountDrawer({ mode: 'edit', title: '用户' }).text()).toContain('编辑用户')
    expect(mountDrawer({ mode: 'view', title: '用户' }).text()).toContain('查看用户')
  })

  it('尺寸阶梯：抽屉 400/480/640/720；对话框 420/480/520（xl 落 lg）', async () => {
    const drawer = mountDrawer({ width: 'lg' })
    expect(drawer.findComponent({ name: 'ElDrawer' }).props('size')).toBe(640)

    const dialogXl = await mountDialog(FormDialog, { width: 'xl' })
    expect(dialogXl.findComponent({ name: 'ElDialog' }).props('width')).toBe(520)

    const drawerNumber = mountDrawer({ width: 500 })
    expect(drawerNumber.findComponent({ name: 'ElDrawer' }).props('size')).toBe(500)
  })

  it('页脚动作：view 态无保存；持 submitPerm 显示编辑入口；无权限不渲染保存 / 删除', () => {
    const view = mountDrawer({ mode: 'view', submitPerm: 'user:edit' })
    expect(buttonByText(view, '保存')).toBeUndefined()
    expect(buttonByText(view, '编辑')).toBeTruthy()

    const viewNoPermCode = mountDrawer({ mode: 'view' })
    expect(buttonByText(viewNoPermCode, '编辑')).toBeUndefined()

    hasPermMock.mockReturnValue(false)
    const denied = mountDrawer({ mode: 'create', submitPerm: 'user:save', showDelete: true, deleteHandler: () => {} })
    expect(buttonByText(denied, '保存')).toBeUndefined()
    expect(buttonByText(denied, '删除')).toBeUndefined()

    hasPermMock.mockReturnValue(true)
    const allowed = mountDrawer({ mode: 'create', submitPerm: 'user:save' })
    expect(buttonByText(allowed, '保存')).toBeTruthy()
  })

  it('提交中：保存按钮 loading，点取消不关闭（拦截链忽略）', async () => {
    const wrapper = mountDrawer({ submitLoading: true, submitPerm: 'user:save' })
    const submit = buttonByText(wrapper, '保存')
    expect(submit?.classes()).toContain('is-loading')

    await buttonByText(wrapper, '取消')?.trigger('click')
    expect(confirmMock).not.toHaveBeenCalled()
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('脏数据拦截：确认放弃后关闭，继续编辑不关闭', async () => {
    confirmMock.mockResolvedValue(false)
    const wrapper = mountDrawer({ dirty: true })
    await buttonByText(wrapper, '取消')?.trigger('click')
    expect(confirmMock).toHaveBeenCalledTimes(1)
    expect(confirmMock.mock.calls[0]?.[0]).toMatchObject({
      message: '有未保存的修改，确定放弃吗？',
    })
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    confirmMock.mockResolvedValue(true)
    await buttonByText(wrapper, '取消')?.trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
    await waitClose(wrapper)
  })

  it('beforeClose 钩子串联：不调 done 拒绝关闭，调 done 放行', async () => {
    let release: (() => void) | null = null
    const beforeClose = vi.fn((done: () => void) => {
      release = done
    })
    const wrapper = mountDrawer({ beforeClose })

    await buttonByText(wrapper, '取消')?.trigger('click')
    expect(beforeClose).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('update:modelValue')).toBeUndefined()

    release?.()
    await waitClose(wrapper)
  })

  it('ConfirmDialog：禁遮罩 / Esc、danger 确定、confirm 与 cancel、loading', async () => {
    const wrapper = await mountDialog(ConfirmDialog, { danger: true, loading: true })
    const dialog = wrapper.findComponent({ name: 'ElDialog' })
    expect(dialog.props('closeOnClickModal')).toBe(false)
    expect(dialog.props('closeOnPressEscape')).toBe(false)

    const confirm = buttonByText(wrapper, '确定')
    expect(confirm?.classes()).toContain('el-button--danger')
    expect(confirm?.classes()).toContain('is-loading')

    await wrapper.setProps({ loading: false })
    await nextTick()
    await buttonByText(wrapper, '确定')?.trigger('click')
    expect(wrapper.emitted('confirm')).toBeTruthy()

    await buttonByText(wrapper, '取消')?.trigger('click')
    expect(wrapper.emitted('cancel')).toBeTruthy()
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([false])
  })
})
