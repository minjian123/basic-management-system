/** 动态菜单 store 用例（03_01）：装载映射与权限码回填 / 幂等 / 失败降级 / 重置。 */
// kiwi_id: 2242

import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { fetchMyMenus, type MyMenuResponse } from '@/api/menu'
import { useMenuStore } from '@/stores/menu'
import { MENU_LOAD_ERROR_MESSAGE, notifyError } from '@/utils/feedback'
import { getPermissionCodes } from '@/utils/perm'

vi.mock('@/api/menu', () => ({ fetchMyMenus: vi.fn() }))
vi.mock('@/utils/feedback', () => ({
  MENU_LOAD_ERROR_MESSAGE: '菜单加载失败，请稍后重试',
  notifyError: vi.fn(),
}))

/** 典型动态菜单响应（菜单树 + 表单 / 按钮 / 字段元数据）。 */
const RESPONSE: MyMenuResponse = {
  locale: 'zh-CN',
  version: 3,
  permissions: ['user', 'user:create'],
  menus: [
    {
      id: '1',
      parent_id: '0',
      name: '系统管理',
      path: '/sys',
      component: null,
      icon: 'el:setting',
      sort: 10,
      hidden: false,
      forms: [],
      children: [
        {
          id: '2',
          parent_id: '1',
          name: '用户管理',
          path: '/sys/users',
          component: 'sys/users',
          icon: null,
          sort: 1,
          hidden: false,
          forms: [
            {
              id: '10',
              menu_id: '2',
              business_id: '1',
              business_code: 'user',
              component: 'sys/users',
              buttons: [
                {
                  id: '20',
                  action_id: '30',
                  action_code: 'user:create',
                  name: '新增',
                  type: 'toolbar',
                  sort: 1,
                  visible: true,
                },
              ],
              fields: [
                {
                  id: '40',
                  field_key: 'username',
                  name: '用户名',
                  type: 'input',
                  sort: 1,
                  visible: true,
                  editable: false,
                },
              ],
            },
            {
              id: '11',
              menu_id: '2',
              business_id: '2',
              business_code: 'user_extra',
              component: null,
              buttons: [],
              fields: [],
            },
          ],
          children: [],
        },
      ],
    },
  ],
}

const fetchMock = vi.mocked(fetchMyMenus)
const notifyMock = vi.mocked(notifyError)

beforeEach(() => {
  setActivePinia(createPinia())
  fetchMock.mockReset()
  notifyMock.mockReset()
})

afterEach(() => {
  vi.unstubAllEnvs()
})

describe('useMenuStore（03_01）', () => {
  it('装载成功：菜单树映射、表单索引、权限码回填 utils/perm', async () => {
    fetchMock.mockResolvedValue(RESPONSE)
    const store = useMenuStore()

    await store.load()

    expect(store.loaded).toBe(true)
    expect(store.locale).toBe('zh-CN')
    expect(store.version).toBe(3)
    expect(store.tree.map((node) => node.title)).toEqual(['系统管理'])
    expect(store.tree[0]?.children?.map((node) => node.path)).toEqual(['/sys/users'])
    expect(store.formOf('/sys/users')?.businessCode).toBe('user')
    expect(store.formOf('/sys/users')?.visibleButtonCodes).toEqual(['user:create'])
    expect(store.formOf('/sys')).toBeUndefined()
    expect(store.fieldPermissions('10')).toEqual({ username: { visible: true, editable: false } })
    // 多对多（02_03）：同一入口的多个表单全部进索引，按路径取首个为主表单
    expect(Object.keys(store.forms).sort()).toEqual(['10', '11'])
    expect(store.formOf('/sys/users')?.id).toBe('10')
    expect(store.permissions).toEqual(['user', 'user:create'])
    expect(getPermissionCodes()).toEqual(['user', 'user:create'])
  })

  it('叶子节点不带 children 键（核心权限过滤按叶子保留，避免整链丢弃）', async () => {
    fetchMock.mockResolvedValue(RESPONSE)
    const store = useMenuStore()

    await store.load()

    const group = store.tree[0]
    const leaf = group?.children?.[0]
    expect(leaf?.path).toBe('/sys/users')
    // 契约侧叶子 `children: []` → 映射后必须**无** `children` 键，否则 `filterMenuByPermission` 视作空子树整链丢弃。
    expect(leaf !== undefined && 'children' in leaf).toBe(false)
    expect(group !== undefined && 'children' in group).toBe(true)
  })

  it('幂等：已装载 / 已尝试均不再拉取；reload 可强制重取', async () => {
    fetchMock.mockResolvedValue(RESPONSE)
    const store = useMenuStore()

    await store.load()
    await store.load()
    expect(fetchMock).toHaveBeenCalledTimes(1)

    await store.reload()
    expect(fetchMock).toHaveBeenCalledTimes(2)
  })

  it('生产：装载失败置空菜单 + 一次错误提示（不重复提示、不重复拉取）', async () => {
    vi.stubEnv('DEV', false)
    fetchMock.mockRejectedValue(new Error('boom'))
    const store = useMenuStore()

    await store.load()
    expect(store.loaded).toBe(false)
    expect(store.tree).toEqual([])
    expect(store.error).toBe('boom')
    expect(store.permissions).toEqual([])
    expect(getPermissionCodes()).toEqual([])
    expect(notifyMock).toHaveBeenCalledTimes(1)
    expect(notifyMock).toHaveBeenCalledWith(MENU_LOAD_ERROR_MESSAGE)

    await store.load()
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(notifyMock).toHaveBeenCalledTimes(1)
  })

  it('开发态：装载失败回退占位菜单便于本地调页', async () => {
    fetchMock.mockRejectedValue(new Error('boom'))
    const store = useMenuStore()

    await store.load()
    expect(store.loaded).toBe(false)
    expect(store.tree.length).toBeGreaterThan(0)
    expect(notifyMock).not.toHaveBeenCalled()
  })

  it('reset：清空菜单与权限码（登出 / 会话失效）', async () => {
    fetchMock.mockResolvedValue(RESPONSE)
    const store = useMenuStore()
    await store.load()

    store.reset()
    expect(store.tree).toEqual([])
    expect(store.formOf('/sys/users')).toBeUndefined()
    expect(store.loaded).toBe(false)
    expect(getPermissionCodes()).toEqual([])
  })
})
