// kiwi_id: 2260
/**
 * 角色分配页签具名插槽与显式上下文用例（需求 05-11）：
 * 非路由承载宿主页（表单框架记录页签）经插槽件注入**只读上下文**（`roleId` + `registerSubmitter`），
 * 区域项（插件）经注入通道只读取得；插件缺失即隐藏、不报错。
 *
 * 口径修订（2026-10-09，`02_03/_02`）：本页签改为纯 outlet 宿主——平台内建「用户分配」按区域项注册
 * （与 mdm 岗位 / 部门插件同槽并列），宿主页不再自带用户表格；草稿收集与提交归记录页。
 */

import { PageAreaProvider } from '@bms/core'
import { useModuleSlotField, type HostSubmitterRegistrar } from '@bms/ui_ep'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'

import { registries } from '@/module/registries'
import RoleAssignTab from '@/views/system/role/RoleAssignTab.vue'

vi.mock('@/api/role', () => ({ listRoleUsers: vi.fn(), applyRoleAssignments: vi.fn() }))
vi.mock('@/api/user', () => ({ listUsers: vi.fn() }))
vi.mock('@/stores/session', () => ({ useSessionStore: () => ({ codes: [] }) }))

/** 探针插件项（消费插槽上下文，渲染取得的角色标识）。 */
const PROBE_COMPONENT = {
  name: 'role-assign-probe',
  setup: () => {
    const roleId = useModuleSlotField<string>('roleId')
    return () => h('span', { class: 'probe-role' }, String(roleId.value ?? 'none'))
  },
}

/** 探针插件项键（用例内注册 / 清理）。 */
const PROBE_KEY = 'mdm_org:role_posts'

/** 装饰性 EP 件桩（原生表格在 jsdom 下依赖 ResizeObserver，此处只需行为）。 */
const stubs = {
  ElTable: defineComponent({
    name: 'ElTable',
    props: { data: { type: Array, default: () => [] } },
    template: '<div class="el-table-stub"><slot name="empty" /></div>',
  }),
  ElTableColumn: defineComponent({ name: 'ElTableColumn', template: '<div />' }),
}

/**
 * 挂载角色分配页签。
 *
 * @param roleId 角色主键。
 */
async function mountTab(roleId: string) {
  setActivePinia(createPinia())
  const wrapper = mount(RoleAssignTab, { props: { roleId }, global: { stubs } })
  await flushPromises()
  return wrapper
}

beforeEach(() => {
  registries.pageArea.unregister(PROBE_KEY)
})

afterEach(() => {
  registries.pageArea.unregister(PROBE_KEY)
})

describe('角色分配页签具名插槽与显式上下文（05-11 · Kiwi 2260）', () => {
  it('留槽并注入只读上下文：区域项经注入通道取到当前角色标识', async () => {
    registries.pageArea.register(
      new PageAreaProvider(PROBE_KEY, 'sys.role.detail.assign', PROBE_COMPONENT, 20, { title: '岗位分配' }),
    )

    const wrapper = await mountTab('r-9')

    expect(wrapper.find('.probe-role').text()).toBe('r-9')
    expect(wrapper.findAll('.el-tabs__item').map((item) => item.text())).toEqual(['岗位分配'])
    expect(wrapper.find('[data-test="role-assign"]').exists()).toBe(true)
  })

  it('插件缺失即隐藏、不报错：插槽区为空而宿主页正常', async () => {
    const wrapper = await mountTab('r-1')

    expect(wrapper.find('.probe-role').exists()).toBe(false)
    expect(wrapper.find('[data-test="role-assign"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="role-assign-slot"]').exists()).toBe(true)
  })

  it('上下文随宿主实体切换（记录页签切换角色即刷新注入值）', async () => {
    registries.pageArea.register(
      new PageAreaProvider(PROBE_KEY, 'sys.role.detail.assign', PROBE_COMPONENT, 20, { title: '岗位分配' }),
    )

    const wrapper = await mountTab('r-1')
    expect(wrapper.find('.probe-role').text()).toBe('r-1')

    await wrapper.setProps({ roleId: 'r-2' })
    await flushPromises()

    expect(wrapper.find('.probe-role').text()).toBe('r-2')
  })

  it('新增态不渲染挂接位（创建后可分配）', async () => {
    const wrapper = await mountTab('new')
    expect(wrapper.find('[data-test="role-assign-new-hint"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="role-assign-slot"]').exists()).toBe(false)
  })

  it('向区域项注入宿主提交器通道（registerSubmitter 值即函数）', async () => {
    let captured: HostSubmitterRegistrar | undefined
    const probeWithRegistrar = {
      name: 'role-assign-registrar-probe',
      setup: () => {
        captured = useModuleSlotField<HostSubmitterRegistrar>('registerSubmitter').value
        return () => h('span')
      },
    }
    registries.pageArea.register(
      new PageAreaProvider('mdm_org:role_depts', 'sys.role.detail.assign', probeWithRegistrar, 30, {
        title: '部门分配',
      }),
    )

    const wrapper = await mountTab('r-1')
    expect(typeof captured).toBe('function')

    // 登记一个草稿提交器后，宿主页签可收集到分段
    captured?.({
      isDirty: () => true,
      buildSegment: () => ({ key: 'role_depts', value: { dept_ids: ['d1'] } }),
      reload: async () => {},
    })
    await flushPromises()
    expect(wrapper.vm.buildSegments()).toEqual({ role_depts: { dept_ids: ['d1'] } })

    registries.pageArea.unregister('mdm_org:role_depts')
  })

  it('草稿提交器登记：同项重复登记去重（不重复收集），脏态经暴露面上抛', async () => {
    let captured: HostSubmitterRegistrar | undefined
    const probe = {
      name: 'role-assign-dedupe-probe',
      setup: () => {
        captured = useModuleSlotField<HostSubmitterRegistrar>('registerSubmitter').value
        return () => h('span')
      },
    }
    registries.pageArea.register(new PageAreaProvider('mdm_org:role_posts', 'sys.role.detail.assign', probe, 10))

    const wrapper = await mountTab('r-1')
    expect(wrapper.vm.isDirty()).toBe(false)

    const entry = {
      isDirty: () => true,
      buildSegment: () => ({ key: 'role_posts', value: { post_ids: ['p1'] } }),
      reload: async () => {},
    }
    // 同一提交器登记两次：去重后只保留一份（分段不重复）
    captured?.(entry)
    captured?.(entry)
    await flushPromises()

    expect(wrapper.vm.buildSegments()).toEqual({ role_posts: { post_ids: ['p1'] } })
    expect(wrapper.vm.isDirty()).toBe(true)
    expect(wrapper.emitted('dirty')?.at(-1)).toEqual([true])

    registries.pageArea.unregister('mdm_org:role_posts')
  })

  it('草稿分段收集：无改动（返回 `null`）的段不出现', async () => {
    let captured: HostSubmitterRegistrar | undefined
    const probe = {
      name: 'role-assign-null-segment-probe',
      setup: () => {
        captured = useModuleSlotField<HostSubmitterRegistrar>('registerSubmitter').value
        return () => h('span')
      },
    }
    registries.pageArea.register(new PageAreaProvider('mdm_org:role_depts', 'sys.role.detail.assign', probe, 30))

    const wrapper = await mountTab('r-1')
    captured?.({ isDirty: () => false, buildSegment: () => null, reload: async () => {} })
    await flushPromises()

    expect(wrapper.vm.buildSegments()).toEqual({})
    expect(wrapper.vm.isDirty()).toBe(false)

    registries.pageArea.unregister('mdm_org:role_depts')
  })

  it('撤销：逐项调用各插件的 `reload` 复位草稿', async () => {
    let captured: HostSubmitterRegistrar | undefined
    const probe = {
      name: 'role-assign-revert-probe',
      setup: () => {
        captured = useModuleSlotField<HostSubmitterRegistrar>('registerSubmitter').value
        return () => h('span')
      },
    }
    registries.pageArea.register(new PageAreaProvider('mdm_org:role_depts', 'sys.role.detail.assign', probe, 30))

    const first = vi.fn(async () => undefined)
    const second = vi.fn(async () => undefined)
    const wrapper = await mountTab('r-1')
    captured?.({
      isDirty: () => true,
      buildSegment: () => ({ key: 'role_depts', value: { dept_ids: ['d1'] } }),
      reload: first,
    })
    captured?.({ isDirty: () => false, buildSegment: () => null, reload: second })
    await flushPromises()

    await wrapper.vm.revert()

    expect(first).toHaveBeenCalledTimes(1)
    expect(second).toHaveBeenCalledTimes(1)

    registries.pageArea.unregister('mdm_org:role_depts')
  })

  it('新增态插槽上下文：角色标识归一为空串（不向插件暴露 `new`）', async () => {
    const wrapper = await mountTab('new')

    const context = (wrapper.vm as unknown as { $: { setupState: Record<string, unknown> } }).$.setupState
      .slotContext as Record<string, unknown>
    expect(context.roleId).toBe('')
    expect(typeof context.registerSubmitter).toBe('function')
  })

  it('实体切换：记录页签切换角色即清空已登记草稿', async () => {
    let captured: HostSubmitterRegistrar | undefined
    const probe = {
      name: 'role-assign-switch-probe',
      setup: () => {
        captured = useModuleSlotField<HostSubmitterRegistrar>('registerSubmitter').value
        return () => h('span')
      },
    }
    registries.pageArea.register(new PageAreaProvider('mdm_org:role_depts', 'sys.role.detail.assign', probe, 30))

    const wrapper = await mountTab('r-1')
    captured?.({
      isDirty: () => true,
      buildSegment: () => ({ key: 'role_depts', value: { dept_ids: ['d1'] } }),
      reload: async () => {},
    })
    await flushPromises()
    expect(wrapper.vm.buildSegments()).toEqual({ role_depts: { dept_ids: ['d1'] } })

    await wrapper.setProps({ roleId: 'r-2' })
    await flushPromises()

    expect(wrapper.vm.buildSegments()).toEqual({})
    expect(wrapper.vm.isDirty()).toBe(false)

    registries.pageArea.unregister('mdm_org:role_depts')
  })
})
