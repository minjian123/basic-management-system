/**
 * 用户展示片段（`user-display`）：用户 / 组织的姓名、头像、状态与部门路径展示。
 *
 * 契约见《组件设计 · 用户展示片段》：`loadUsers` / `loadDepts` / `display` / `deptPath` /
 * `status` / `invalidate`（头像组件、组织选择回显、审批流、通知共用）。
 * **占位先行**：未注入 `loader`（用户 / 组织接口未接入）时 `display()` 回落 `fallback`（默认取 id），
 * 不发请求；条件允许时用「已缓存值 → 占位值」两级降级。
 */

import { computed, ref, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 用户展示数据 */
export interface UserDisplayInfo {
  id: string | number
  name: string
  avatar?: string
  status?: 'active' | 'disabled' | 'locked'
  deptId?: string | number
}

/** 组织展示数据 */
export interface DeptDisplayInfo {
  id: string | number
  name: string
  parentId?: string | number
}

/** 数据加载器（用户 / 组织接口接入后注入） */
export interface UserDisplayLoader {
  loadUsers: (ids: Array<string | number>) => Promise<UserDisplayInfo[]>
  loadDepts: (ids: Array<string | number>) => Promise<DeptDisplayInfo[]>
}

/** 用户展示片段参数 */
export interface UseUserDisplayOptions {
  /** 展示字段控制（`name` / `avatar` / `status` 中取用；缺省全开） */
  fields?: MaybeRefOrGetter<Array<'name' | 'avatar' | 'status'>>
  /** 部门路径分隔符（默认 `/`） */
  deptPathSep?: MaybeRefOrGetter<string>
  /** 是否缓存（默认 true） */
  cache?: MaybeRefOrGetter<boolean>
  /** 取不到数据时的兜底（缺省返回 id 字符串） */
  fallback?: (id: string | number) => string
  /** 加载器（缺省即占位：不请求） */
  loader?: UserDisplayLoader
}

/** 用户展示片段返回值 */
export interface UseUserDisplayReturn {
  readonly isPlaceholder: boolean
  readonly users: Record<string, UserDisplayInfo>
  readonly depts: Record<string, DeptDisplayInfo>
  loadUsers: (ids: Array<string | number>) => Promise<void>
  loadDepts: (ids: Array<string | number>) => Promise<void>
  /** 用户展示文本（姓名或兜底） */
  display: (id: string | number | undefined) => string
  /** 头像地址（无则空串） */
  avatar: (id: string | number | undefined) => string
  /** 状态文案（`active` / `disabled` / `locked`；未加载返回空串） */
  status: (id: string | number | undefined) => string
  /** 部门全路径（如 `集团/华东/上海`） */
  deptPath: (deptId: string | number | undefined) => string
  invalidate: (id?: string | number) => void
}

/**
 * 获取用户展示能力。
 *
 * 用法：`const userDisplay = useUserDisplay({ loader })`；接口未接入时省略 `loader` 即得占位行为
 * （`display()` 返回 id，界面显示占位文本）。
 */
export function useUserDisplay(options: UseUserDisplayOptions = {}): UseUserDisplayReturn {
  const capability = declareFragment('user-display')

  const users = ref<Record<string, UserDisplayInfo>>({})
  const depts = ref<Record<string, DeptDisplayInfo>>({})
  const isPlaceholder = computed(() => options.loader === undefined)

  const useCache = () => toValue(options.cache) ?? true
  const fallbackText = (id: string | number): string => (options.fallback ? options.fallback(id) : String(id))

  const loadUsers = async (ids: Array<string | number>): Promise<void> => {
    const missing = useCache() ? ids.filter((id) => users.value[String(id)] === undefined) : ids
    if (missing.length === 0 || !options.loader) {
      if (!options.loader) {
        capability.log('debug', 'user-display 占位：用户数据加载器未接入')
      }
      return
    }
    const result = await options.loader.loadUsers(missing)
    const next = { ...users.value }
    for (const user of result) {
      next[String(user.id)] = user
    }
    users.value = next
  }

  const loadDepts = async (ids: Array<string | number>): Promise<void> => {
    const missing = useCache() ? ids.filter((id) => depts.value[String(id)] === undefined) : ids
    if (missing.length === 0 || !options.loader) {
      return
    }
    const result = await options.loader.loadDepts(missing)
    const next = { ...depts.value }
    for (const dept of result) {
      next[String(dept.id)] = dept
    }
    depts.value = next
  }

  const deptPath = (deptId: string | number | undefined): string => {
    if (deptId === undefined) {
      return ''
    }
    const separator = String(toValue(options.deptPathSep) ?? '/')
    const parts: string[] = []
    let current: DeptDisplayInfo | undefined = depts.value[String(deptId)]
    let guard = 0
    while (current && guard < 20) {
      parts.unshift(current.name)
      current = current.parentId === undefined ? undefined : depts.value[String(current.parentId)]
      guard += 1
    }
    return parts.join(separator)
  }

  return {
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get users() {
      return users.value
    },
    get depts() {
      return depts.value
    },
    loadUsers,
    loadDepts,
    display: (id) => {
      if (id === undefined) {
        return ''
      }
      return users.value[String(id)]?.name ?? fallbackText(id)
    },
    avatar: (id) => (id === undefined ? '' : (users.value[String(id)]?.avatar ?? '')),
    status: (id) => (id === undefined ? '' : (users.value[String(id)]?.status ?? '')),
    deptPath,
    invalidate: (id) => {
      if (id === undefined) {
        users.value = {}
        depts.value = {}
        return
      }
      const nextUsers = { ...users.value }
      delete nextUsers[String(id)]
      users.value = nextUsers
      const nextDepts = { ...depts.value }
      delete nextDepts[String(id)]
      depts.value = nextDepts
    },
  }
}
