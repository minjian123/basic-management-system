/**
 * 菜单管理页用例（03_03）：列表装载 / 树展开策略与本地记忆 / 筛选 / 拖拽调序与保存回滚 /
 * 批量删除与启停 / 记录页签打开与关闭（脏数据拦截）/ 新增态换页签。
 */
// kiwi_id: 2338

import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ElMessage, ElMessageBox } from 'element-plus'
import { createPinia, setActivePinia, type Pinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, nextTick } from 'vue'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'

import { deleteMenu, listMenus, updateMenu, type MenuItem } from '@/api/menuMeta'
import { useMenuMetaStore } from '@/stores/menuMeta'
import { useTabsStore } from '@/stores/tabs'
import MenuView from '@/views/system/menu/MenuView.vue'

vi.mock('@/api/menuMeta', () => ({
  listMenus: vi.fn(),
  listForms: vi.fn(),
  createMenu: vi.fn(),
  updateMenu: vi.fn(),
  deleteMenu: vi.fn(),
  listButtons: vi.fn(),
  listFields: vi.fn(),
  createButton: vi.fn(),
  updateButton: vi.fn(),
  deleteButton: vi.fn(),
  createField: vi.fn(),
  updateField: vi.fn(),
  deleteField: vi.fn(),
  updateForm: vi.fn(),
}))
vi.mock('@/api/business', () => ({ listBusinesses: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/action', () => ({ listActions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/permission', () => ({ listPermissions: vi.fn(async () => ({ items: [] })) }))
vi.mock('@/api/icon', () => ({ listIcons: vi.fn(async () => ({ icons: [] })) }))

const listMock = vi.mocked(listMenus)
const updateMock = vi.mocked(updateMenu)
const deleteMock = vi.mocked(deleteMenu)

/**
 * 构造菜单节点。
 *
 * @param overrides 覆盖字段。
 * @returns 菜单节点。
 */
function node(overrides: Partial<MenuItem>): MenuItem {
  return {
    id: '',
    parent_id: '0',
    name: '',
    path: '',
    component: null,
    icon: null,
    sort: 10,
    hidden: false,
    status: 'enabled',
    i18n: { 'zh-CN': '' },
    children: [],
    ...overrides,
  }
}

/** 样例树。 */
function tree(): MenuItem[] {
  return [
    node({
      id: 'sys',
      name: '系统管理',
      path: '/sys',
      sort: 10,
      children: [
        node({ id: 'user', parent_id: 'sys', name: '用户管理', path: '/sys/users', component: '用户表单', sort: 10 }),
        node({ id: 'role', parent_id: 'sys', name: '角色管理', path: '/sys/roles', component: '角色表单', sort: 20 }),
      ],
    }),
    node({ id: 'home', name: '首页工作台', path: '/', component: '工作台', sort: 20 }),
  ]
}

/** 记录页桩（隔离记录页逻辑）。 */
const RecordStub = defineComponent({
  name: 'MenuRecordTab',
  props: { menuId: { type: String, default: '' } },
  emits: ['saved', 'removed', 'dirty', 'close'],
  template: '<div data-test="menu-record-stub">{{ menuId }}</div>',
})

/** 装饰性 EP 件桩。 */
const stubs = { MenuRecordTab: RecordStub }

/** jsdom 垫片：真实 `el-table` 依赖 ResizeObserver。 */
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
globalThis.ResizeObserver = ResizeObserverStub as unknown as typeof ResizeObserver

let pinia: Pinia
let router: Router

/**
 * 挂载菜单页。
 *
 * @returns 包装器。
 */
async function mountView(): Promise<VueWrapper> {
  pinia = createPinia()
  setActivePinia(pinia)
  router = createRouter({ history: createMemoryHistory(), routes: [] })
  const wrapper = mount(MenuView, { global: { plugins: [pinia, router], stubs } })
  await flushPromises()
  return wrapper
}

/**
 * 取 script setup 暴露面。
 *
 * @param wrapper 包装器。
 * @returns setupState。
 */
/* eslint-disable @typescript-eslint/no-explicit-any */
function stateOf(wrapper: VueWrapper): Record<string, any> {
  return (wrapper.vm as unknown as { $: { setupState: Record<string, any> } }).$.setupState
}

beforeEach(() => {
  localStorage.clear()
  listMock.mockReset()
  updateMock.mockReset()
  deleteMock.mockReset()
  listMock.mockResolvedValue({ items: tree() })
  vi.spyOn(ElMessageBox, 'confirm').mockResolvedValue('confirm')
  vi.spyOn(ElMessage, 'success').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'error').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'warning').mockImplementation(() => undefined as never)
  vi.spyOn(ElMessage, 'info').mockImplementation(() => undefined as never)
})

describe('MenuView（03_03）', () => {
  it('列表装载：树形表格渲染两级节点，工具栏与拖拽提示就位', async () => {
    const wrapper = await mountView()

    expect(listMock).toHaveBeenCalled()
    expect(wrapper.find('[data-test="menu-view"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="menu-drag-handle"]').exists()).toBe(true)
    expect(wrapper.find('[data-test="menu-export"]').attributes('disabled')).toBeDefined()
    expect(wrapper.find('[data-test="menu-table"]').text()).toContain('系统管理')
    expect(wrapper.find('[data-test="menu-table"]').text()).toContain('用户管理')
    expect(useMenuMetaStore().loadedMenus).toBe(true)
  })

  it('展开策略：≤50 节点默认全展开；>50 只展开第一层', async () => {
    const wrapper = await mountView()
    expect(stateOf(wrapper).expandedIds).toEqual(['sys'])

    const many = [node({ id: 'root', name: '根', path: '/root', children: Array.from({ length: 50 }, (_, index) => node({ id: `c${index}`, parent_id: 'root', name: `子${index}`, path: `/c${index}`, component: 'x' })) })]
    listMock.mockResolvedValue({ items: many })
    const wrapper2 = await mountView()
    expect(stateOf(wrapper2).expandedIds).toEqual(['root'])
  })

  it('展开记忆：读取本地偏好 / 脏值回退 / 写入偏好', async () => {
    localStorage.setItem('bms_menu_expanded', JSON.stringify(['sys']))
    const wrapper = await mountView()
    expect(stateOf(wrapper).expandedIds).toEqual(['sys'])

    localStorage.setItem('bms_menu_expanded', 'not-json')
    const wrapper2 = await mountView()
    expect(stateOf(wrapper2).expandedIds).toEqual(['sys'])

    localStorage.setItem('bms_menu_expanded', JSON.stringify(['sys', 1]))
    const wrapper3 = await mountView()
    expect(stateOf(wrapper3).expandedIds).toEqual(['sys'])
  })

  it('展开 / 折叠全部：写入偏好并切换文案', async () => {
    const wrapper = await mountView()
    expect(wrapper.find('[data-test="menu-expand-all"]').text()).toBe('全部折叠')

    await wrapper.find('[data-test="menu-expand-all"]').trigger('click')
    expect(stateOf(wrapper).expandedIds).toEqual([])
    expect(wrapper.find('[data-test="menu-expand-all"]').text()).toBe('全部展开')
    expect(JSON.parse(localStorage.getItem('bms_menu_expanded') ?? '[]')).toEqual([])

    await wrapper.find('[data-test="menu-expand-all"]').trigger('click')
    expect(stateOf(wrapper).expandedIds).toEqual(['sys'])
  })

  it('行内展开回写偏好；筛选态临时展开不写偏好；程序化展开不回写', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    table.vm.$emit('expand-change', tree()[0], false)
    await nextTick()
    expect(stateOf(wrapper).expandedIds).toEqual([])
    expect(JSON.parse(localStorage.getItem('bms_menu_expanded') ?? '[]')).toEqual([])

    stateOf(wrapper).applied = { keyword: '用户' }
    await nextTick()
    table.vm.$emit('expand-change', tree()[0], true)
    await nextTick()
    expect(stateOf(wrapper).expandedIds).toEqual(['sys'])
    expect(JSON.parse(localStorage.getItem('bms_menu_expanded') ?? '[]')).toEqual([])

    stateOf(wrapper).applying = true
    table.vm.$emit('expand-change', tree()[0], false)
    await nextTick()
    expect(stateOf(wrapper).expandedIds).toEqual(['sys'])
  })

  it('筛选与重置：关键字 / 类型 / 状态共同收敛', async () => {
    const wrapper = await mountView()
    await wrapper.find('[data-test="menu-kw"]').setValue('用户')
    await wrapper.find('[data-test="menu-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="menu-table"]').text()).not.toContain('首页工作台')

    await wrapper.find('[data-test="menu-reset"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="menu-table"]').text()).toContain('首页工作台')
  })

  it('拖拽调序：落点提示 / 非法落点 / 原位无变更 / 空拖拽', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    const sys = tree()[0] as MenuItem
    const user = sys.children[0] as MenuItem
    const role = sys.children[1] as MenuItem
    const home = tree()[1] as MenuItem

    state.onDragStart(new Event('dragstart'), user)
    state.onDragOver(role, 'after')
    expect(state.dropHint).toEqual({ id: 'role', position: 'after' })
    expect(state.rowClassName({ row: role })).toBe('menu-view__row-after')
    expect(state.rowClassName({ row: user })).toBe('')

    state.onDragOver(role, 'inner')
    expect(state.rowClassName({ row: role })).toBe('menu-view__row-into')

    // 目标为菜单（非目录）：不可放入其中
    state.onDragStart(new Event('dragstart'), home)
    state.onDrop(user, 'inner')
    expect(ElMessage.warning).toHaveBeenCalled()
    expect(state.pendingMoves).toEqual([])

    // 拖入自身子树：拒绝
    state.onDragStart(new Event('dragstart'), sys)
    state.onDrop(user, 'after')
    expect(ElMessage.warning).toHaveBeenCalledTimes(2)

    // 原位落点：无变更
    state.onDragStart(new Event('dragstart'), user)
    state.onDrop(role, 'before')
    expect(state.pendingMoves).toEqual([])

    // 无拖拽起点：直接忽略
    state.onDragEnd()
    state.onDrop(role, 'after')
    expect(state.pendingMoves).toEqual([])
  })

  it('拖拽调序：本地更新 + 保存排序（逐节点完整载荷）与失败回滚、撤销', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    const sys = tree()[0] as MenuItem
    const user = sys.children[0] as MenuItem
    const role = sys.children[1] as MenuItem

    state.onDragStart(new Event('dragstart'), user)
    state.onDrop(role, 'after')
    await nextTick()
    expect(state.pendingMoves.length).toBeGreaterThan(0)
    expect(wrapper.find('[data-test="menu-sort-dirty"]').exists()).toBe(true)

    updateMock.mockResolvedValue(user)
    await wrapper.find('[data-test="menu-save-sort"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('role', expect.objectContaining({ parent_id: 'sys', sort: 10 }))
    expect(ElMessage.success).toHaveBeenCalledWith('排序已保存')

    // 撤销：重新拉取（先制造待提交变更，使按钮可用）
    listMock.mockClear()
    state.pendingMoves = [{ id: 'home', parent_id: '0', sort: 30 }]
    await nextTick()
    await wrapper.find('[data-test="menu-undo-sort"]').trigger('click')
    await flushPromises()
    expect(listMock).toHaveBeenCalled()
  })

  it('保存排序失败回滚并提示；节点已消失时跳过提交', async () => {
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    state.pendingMoves = [{ id: 'ghost', parent_id: '0', sort: 30 }]
    updateMock.mockResolvedValue(node({ id: 'ghost' }))
    await state.saveSort()
    await flushPromises()
    expect(updateMock).not.toHaveBeenCalled()
    expect(state.pendingMoves).toEqual([])

    state.pendingMoves = [{ id: 'home', parent_id: '0', sort: 30 }]
    updateMock.mockRejectedValueOnce(new Error('排序服务不可用'))
    await state.saveSort()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('排序服务不可用')

    state.pendingMoves = [{ id: 'home', parent_id: '0', sort: 30 }]
    updateMock.mockRejectedValueOnce('boom')
    await state.saveSort()
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('排序保存失败，已回滚')
  })

  it('批量删除：取消 / 成功 / 失败（Error 与非 Error）', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    table.vm.$emit('selection-change', [tree()[1]])
    await nextTick()
    deleteMock.mockResolvedValue(null)

    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="menu-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).not.toHaveBeenCalled()

    await wrapper.find('[data-test="menu-batch-delete"]').trigger('click')
    await flushPromises()
    expect(deleteMock).toHaveBeenCalledWith('home')
    expect(ElMessage.success).toHaveBeenCalledWith('已删除 1 个菜单')

    deleteMock.mockRejectedValueOnce(new Error('菜单被角色授权引用（40206）'))
    table.vm.$emit('selection-change', [tree()[1]])
    await nextTick()
    await wrapper.find('[data-test="menu-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('菜单被角色授权引用（40206）')

    deleteMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="menu-batch-delete"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('删除失败：首页工作台')
  })

  it('批量删除：空选短路', async () => {
    const wrapper = await mountView()
    await stateOf(wrapper).removeSelected()
    expect(ElMessageBox.confirm).not.toHaveBeenCalled()
  })

  it('批量停用 / 启用：成功与失败汇总', async () => {
    const wrapper = await mountView()
    const table = wrapper.findComponent({ name: 'ElTable' })
    updateMock.mockResolvedValue(node({ id: 'home' }))

    await stateOf(wrapper).toggleSelected()
    expect(updateMock).not.toHaveBeenCalled()

    table.vm.$emit('selection-change', [tree()[1]])
    await nextTick()
    await wrapper.find('[data-test="menu-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(updateMock).toHaveBeenCalledWith('home', expect.objectContaining({ status: 'disabled' }))
    expect(ElMessage.success).toHaveBeenCalledWith('已更新 1 个菜单的状态')

    updateMock.mockRejectedValueOnce(new Error('状态更新被拒绝'))
    table.vm.$emit('selection-change', [tree()[1]])
    await nextTick()
    await wrapper.find('[data-test="menu-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新被拒绝')

    updateMock.mockRejectedValueOnce('boom')
    await wrapper.find('[data-test="menu-batch-toggle"]').trigger('click')
    await flushPromises()
    expect(ElMessage.error).toHaveBeenCalledWith('状态更新失败：首页工作台')
  })

  it('记录页签：双击打开 / 新增 / 保存（新增换实体页签、编辑同步标题）/ 删除关闭 / 脏态', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    expect(tabs.active).toBe('record:sys')
    expect(wrapper.find('[data-test="menu-record-stub"]').text()).toBe('sys')

    const record = wrapper.findComponent(RecordStub)
    record.vm.$emit('dirty', true)
    await nextTick()
    expect(tabs.tabOf('record:sys')?.dirty).toBe(true)

    record.vm.$emit('saved', node({ id: 'sys', name: '系统管理（新）', path: '/sys' }))
    await flushPromises()
    expect(tabs.tabOf('record:sys')?.title).toBe('系统管理（新）（/sys）')
    expect(tabs.active).toBe('record:sys')

    record.vm.$emit('removed')
    await flushPromises()
    expect(tabs.tabOf('record:sys')).toBeUndefined()

    await wrapper.find('[data-test="menu-create"]').trigger('click')
    await flushPromises()
    expect(tabs.active).toBe('record:new')
    expect(tabs.tabOf('record:new')?.title).toBe('新增菜单')

    wrapper.findComponent(RecordStub).vm.$emit('saved', node({ id: '9001', name: '新菜单', path: '/new' }))
    await flushPromises()
    expect(tabs.tabOf('record:new')).toBeUndefined()
    expect(tabs.tabOf('record:9001')?.title).toBe('新菜单（/new）')
  })

  it('记录页签关闭：脏数据确认 / 取消 / 非脏直接关闭 / 页签不存在', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()

    tabs.setDirty('record:sys', true)
    await nextTick()
    vi.mocked(ElMessageBox.confirm).mockRejectedValueOnce('cancel')
    await wrapper.find('[data-test="form-frame-close-record:sys"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:sys')).toBeDefined()

    await wrapper.find('[data-test="form-frame-close-record:sys"]').trigger('click')
    await flushPromises()
    expect(tabs.tabOf('record:sys')).toBeUndefined()

    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    tabs.setDirty('record:sys', false)
    await wrapper.find('[data-test="form-frame-close-record:sys"]').trigger('click')
    await flushPromises()
    expect(ElMessageBox.confirm).toHaveBeenCalledTimes(2)
    expect(tabs.tabOf('record:sys')).toBeUndefined()

    const frame = wrapper.findComponent({ name: 'FormFrame' })
    await expect((frame.props('beforeClose') as (key: string) => Promise<boolean>)('record:404')).resolves.toBe(false)
  })

  it('记录页签工具栏关闭：走脏数据拦截', async () => {
    const wrapper = await mountView()
    const tabs = useTabsStore()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('close')
    await flushPromises()
    expect(tabs.tabOf('record:sys')).toBeUndefined()
  })

  it('关闭页面：返回工作台', async () => {
    const wrapper = await mountView()
    const push = vi.spyOn(router, 'push')
    await wrapper.find('[data-test="menu-close-page"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith('/')
  })

  it('列表载入失败：Error 与非 Error 分别提示', async () => {
    listMock.mockRejectedValueOnce(new Error('菜单服务不可用'))
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('菜单服务不可用')

    listMock.mockRejectedValueOnce('boom')
    await mountView()
    expect(ElMessage.error).toHaveBeenCalledWith('菜单列表加载失败')
  })

  it('本地存储异常不阻断：读取 / 写入失败按缺省处理', async () => {
    const getItem = vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {
      throw new Error('storage unavailable')
    })
    const wrapper = await mountView()
    expect(stateOf(wrapper).expandedIds).toEqual(['sys'])
    getItem.mockRestore()

    const setItem = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new Error('quota')
    })
    stateOf(wrapper).toggleExpandAll()
    setItem.mockRestore()
    expect(stateOf(wrapper).expandedIds).toEqual([])
  })

  it('筛选关键字命中路径自动展开（临时展开）', async () => {
    const wrapper = await mountView()
    stateOf(wrapper).expandedIds = []
    await wrapper.find('[data-test="menu-kw"]').setValue('用户')
    await wrapper.find('[data-test="menu-search"]').trigger('click')
    await flushPromises()
    await nextTick()
    expect(wrapper.find('[data-test="menu-table"]').text()).toContain('用户管理')
  })

  it('交互细节：占位 JSON 偏好 / 空拖拽经过 / 无变更保存 / 真实拖拽事件 / 筛选下拉 / 非脏关闭', async () => {
    localStorage.setItem('bms_menu_expanded', JSON.stringify({ a: 1 }))
    const wrapper = await mountView()
    const state = stateOf(wrapper)
    expect(state.expandedIds).toEqual(['sys'])

    // 无拖拽起点时的 dragover 与无变更保存
    state.onDragOver(tree()[0], 'after')
    await state.saveSort()

    // 真实 DOM 拖拽事件（手柄 + 名称落点）
    const handle = wrapper.findAll('[data-test="menu-drag-handle"]')[0]!
    const name = wrapper.findAll('[data-test="menu-drop-name"]')[0]!
    await handle.trigger('dragstart', { dataTransfer: { setData: vi.fn() } })
    await handle.trigger('dragover')
    await handle.trigger('drop')
    await name.trigger('dragover')
    await name.trigger('drop')
    await handle.trigger('dragend')

    // 停用状态标签分支
    state.rows[1].status = 'disabled'
    await nextTick()
    expect(wrapper.find('[data-test="menu-table"]').text()).toContain('停用')

    // 筛选下拉 v-model
    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    selects[0]!.vm.$emit('update:modelValue', 'directory')
    selects[1]!.vm.$emit('update:modelValue', 'enabled')
    await nextTick()
    await wrapper.find('[data-test="menu-search"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-test="menu-table"]').text()).toContain('系统管理')

    // 非脏记录页签由记录区关闭事件关闭
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('close')
    await flushPromises()
    expect(useTabsStore().tabOf('record:sys')).toBeUndefined()

    // 保存返回不存在的页签：跳过标题同步
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    wrapper.findComponent(RecordStub).vm.$emit('saved', node({ id: '404', name: '幽灵', path: '/ghost' }))
    await flushPromises()
    expect(useTabsStore().tabOf('record:404')).toBeUndefined()
    useTabsStore().activate('list')
    await nextTick()

    // 顶层菜单（component=null）批量启停：载荷归一 null
    const table = wrapper.findComponent({ name: 'ElTable' })
    updateMock.mockResolvedValue(tree()[1] as never)
    table.vm.$emit('selection-change', [tree()[0]])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).toHaveBeenCalledWith('sys', expect.objectContaining({ component: null, icon: null }))

    // 停用行反转为启用
    stateOf(wrapper).rows[1].status = 'disabled'
    await nextTick()
    table.vm.$emit('selection-change', [stateOf(wrapper).rows[1]])
    await nextTick()
    await stateOf(wrapper).toggleSelected()
    expect(updateMock).toHaveBeenCalledWith('home', expect.objectContaining({ status: 'enabled' }))
  })

  it('记录页签切换回列表：恢复展开态（表格重新挂载）', async () => {
    const wrapper = await mountView()
    await wrapper.findAll('.el-table__row')[0]!.trigger('dblclick')
    await flushPromises()
    useTabsStore().activate('list')
    await nextTick()
    await flushPromises()
    expect(wrapper.find('[data-test="menu-table"]').exists()).toBe(true)
  })
})
