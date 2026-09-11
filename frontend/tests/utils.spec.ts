/** 公共基座用例（Kiwi 23）：useRequest / useListPage / validators / useTabs / EntityStatus。 */

import { describe, expect, it, vi } from 'vitest'

import type { BasePageQuery } from '@/api/types'
import { i18n } from '@/i18n'
import { EntityStatus, entityStatusI18nKey } from '@/utils/status'
import { useListPage } from '@/utils/useListPage'
import { useRequest } from '@/utils/useRequest'
import { useTabs, TABS_STORAGE_KEY } from '@/utils/useTabs'
import { isEmail, isIdCard, isPhone, isUrl, passwordStrength, pattern, required } from '@/utils/validators'

describe('公共基座（Kiwi 23）', () => {
  it('useRequest：成功与失败状态', async () => {
    const onSuccess = vi.fn()
    const onError = vi.fn()
    const request = useRequest(
      vi.fn().mockResolvedValueOnce('ok').mockRejectedValueOnce(new Error('boom')),
      { onSuccess, onError },
    )
    expect(await request.run()).toBe('ok')
    expect(request.data.value).toBe('ok')
    expect(onSuccess).toHaveBeenCalledWith('ok')

    expect(await request.run()).toBeNull()
    expect(request.error.value).toBeInstanceOf(Error)
    expect(onError).toHaveBeenCalled()
    expect(request.loading.value).toBe(false)
  })

  it('useRequest：过期请求失败不写入 error', async () => {
    const rejecters: Array<(reason?: unknown) => void> = []
    const request = useRequest(() => new Promise<string>((_, reject) => rejecters.push(reject)))
    const firstRun = request.run()
    void request.run()
    rejecters[0](new Error('stale'))
    expect(await firstRun).toBeNull()
    expect(request.error.value).toBeNull()
  })

  it('useRequest：竞态保护仅写入最新请求', async () => {
    const deferred: Array<(value: string) => void> = []
    const request = useRequest(() => new Promise<string>((resolve) => deferred.push(resolve)))
    const firstRun = request.run()
    const secondRun = request.run()
    deferred[1]('second')
    expect(await secondRun).toBe('second')
    deferred[0]('first')
    expect(await firstRun).toBe('first')
    expect(request.data.value).toBe('second')
  })

  it('useListPage：搜索/翻页/重置/重载', async () => {
    const list = vi.fn().mockResolvedValue({ list: [], total: 0, page: 1, size: 20 })
    const page = useListPage<{ id: string; name: string }, BasePageQuery & { keyword?: string }>({
      api: { list },
      defaultQuery: { page: 1, size: 20 },
    })
    expect(page.list.value).toEqual([]) // 请求前空数据回退分支
    expect(page.total.value).toBe(0)
    await page.search()
    expect(page.query.value.page).toBe(1)
    page.query.value.keyword = 'k'
    await page.search()
    expect(list).toHaveBeenLastCalledWith({ page: 1, size: 20, keyword: 'k' })
    await page.changePage(3)
    expect(list).toHaveBeenLastCalledWith({ page: 3, size: 20, keyword: 'k' })
    await page.reset()
    expect(page.query.value).toEqual({ page: 1, size: 20 })
    await page.reload()
    expect(list).toHaveBeenCalledTimes(5)
    expect(page.list.value).toEqual([])
    expect(page.total.value).toBe(0)
  })

  it('validators：predicates 与规则工厂', () => {
    expect(isPhone('13800138000')).toBe(true)
    expect(isPhone('12345')).toBe(false)
    expect(isEmail('a@b.com')).toBe(true)
    expect(isEmail('a@b')).toBe(false)
    expect(isIdCard('110101199001011234')).toBe(true)
    expect(isIdCard('123')).toBe(false)
    expect(isUrl('https://example.com/x')).toBe(true)
    expect(isUrl('ftp://x')).toBe(false)
    expect(passwordStrength('abc')).toBe('weak')
    expect(passwordStrength('aaaaaaaa')).toBe('weak')
    expect(passwordStrength('aaaaaaaaaaaa')).toBe('weak')
    expect(passwordStrength('abcdef12')).toBe('medium')
    expect(passwordStrength('abcdefghij12')).toBe('medium')
    expect(passwordStrength('Abcdef12345!')).toBe('strong')
    expect(passwordStrength('ABC12345678!')).toBe('strong')
    expect(required()).toEqual({ required: true, message: '必填项', trigger: 'blur' })
    expect(pattern(/^\d+$/, '仅数字')).toEqual({ pattern: /^\d+$/, message: '仅数字', trigger: 'blur' })
  })

  it('useTabs：建/切/关、白名单、持久化与恢复', () => {
    localStorage.clear()
    const navigate = vi.fn()
    const tabsApi = useTabs({ navigate })
    tabsApi.tabs.value = []
    tabsApi.active.value = ''

    tabsApi.openTab('/home', '首页')
    tabsApi.openTab('/home', '首页') // 重复不新增
    expect(tabsApi.tabs.value).toHaveLength(1)
    expect(tabsApi.active.value).toBe('/home')
    expect(navigate).toHaveBeenLastCalledWith('/home')

    tabsApi.openTab('/other', '其它') // 白名单外忽略
    expect(tabsApi.tabs.value).toHaveLength(1)

    tabsApi.openTab('/', '根')
    expect(tabsApi.active.value).toBe('/')
    expect(tabsApi.tabs.value).toHaveLength(2)
    expect(JSON.parse(localStorage.getItem(TABS_STORAGE_KEY) ?? '[]')).toHaveLength(2)

    tabsApi.closeTab('/home') // 关闭非激活 Tab：不切换激活
    expect(tabsApi.active.value).toBe('/')

    tabsApi.openTab('/home', '首页')
    expect(tabsApi.tabs.value).toHaveLength(2)
    tabsApi.closeTab('/home') // 关闭激活项且仍有剩余：回退最后一个
    expect(tabsApi.active.value).toBe('/')
    tabsApi.closeTab('/') // 关闭激活项且无剩余：清空激活
    expect(tabsApi.active.value).toBe('')

    localStorage.setItem(TABS_STORAGE_KEY, JSON.stringify([{ path: '/home', title: '首页' }]))
    tabsApi.restore()
    expect(tabsApi.tabs.value).toEqual([{ path: '/home', title: '首页' }])

    localStorage.setItem(TABS_STORAGE_KEY, 'not-json')
    tabsApi.restore()
    expect(tabsApi.tabs.value).toEqual([])

    localStorage.removeItem(TABS_STORAGE_KEY)
    tabsApi.restore() // 无持久化数据回退分支

    tabsApi.restore() // 无持久化数据时保持现状
    expect(tabsApi.tabs.value).toEqual([])

    const bare = useTabs() // 无 navigate 回调分支
    bare.activate('/home')
    expect(bare.active.value).toBe('/home')
  })

  it('EntityStatus 映射与 i18n 键', () => {
    expect(entityStatusI18nKey(EntityStatus.Enabled)).toBe('common.enabled')
    expect(entityStatusI18nKey(EntityStatus.Disabled)).toBe('common.disabled')
    expect(entityStatusI18nKey(9)).toBe('common.disabled')
    expect(i18n.global.t('common.enabled')).toBe('启用')
    expect(i18n.global.t('common.disabled')).toBe('停用')
  })
})
