/**
 * 页面帮助上下文派生（宿主）：当前路由 → 模块 / 表单锚点 → 帮助描述符。
 *
 * - 模块键：菜单锚点第 2 段（当前路径未登记则向父路径回溯）；
 * - 表单键：当前路径主表单的业务码；
 * - 锚点可用：模块或表单登记了 `help_key`（页内入口首次显隐判据，不在页面加载时请求）；
 * - 字段 / 动作键默认空，暴露 setter 供字段级 / 按钮级后续接入。
 */

import type { HelpContextFetcher, HelpContextInput, HelpDescriptor } from '@bms/core'
import { computed, ref, type ComputedRef } from 'vue'
import { useRoute } from 'vue-router'

import { useAppCapabilities } from '@/composables/useAppCapabilities'
import { useMenuStore } from '@/stores/menu'

/** `usePageHelpContext` 返回面。 */
export interface UsePageHelpContextResult {
  /** 帮助描述符（上下文 + 锚点可用性）。 */
  help: ComputedRef<HelpDescriptor>
  /** 帮助取数器（宿主未装配时为 `undefined`）。 */
  fetcher: HelpContextFetcher | undefined
  /** 设置字段键（字段级帮助后续接入用）。 */
  setFieldKey: (fieldKey: string | undefined) => void
  /** 设置动作码（按钮级帮助后续接入用）。 */
  setActionCode: (actionCode: string | undefined) => void
}

/**
 * 取宿主帮助取数器（未装配返回 `undefined`，不阻塞页面）。
 *
 * @returns 帮助取数器。
 */
function resolveFetcher(): HelpContextFetcher | undefined {
  try {
    return useAppCapabilities().helpFetcher
  } catch {
    return undefined
  }
}

/**
 * 路径父级序列（自身 → 逐级父路径 → 根）。
 *
 * @param path 当前路径。
 * @returns 路径序列。
 */
function ancestorPaths(path: string): string[] {
  const paths: string[] = []
  let current = path
  while (current !== '' && current !== '/') {
    paths.push(current)
    const index = current.lastIndexOf('/')
    current = index <= 0 ? '' : current.slice(0, index)
  }
  paths.push('/')
  return paths
}

/**
 * 取路径上最近的菜单锚点。
 *
 * @param helpKeyByPath 菜单路径 → 锚点。
 * @param path 当前路径。
 * @returns 锚点（无则空串）。
 */
function nearestMenuKey(helpKeyByPath: Record<string, string>, path: string): string {
  for (const candidate of ancestorPaths(path)) {
    const key = helpKeyByPath[candidate]
    if (key !== undefined && key !== '') {
      return key
    }
  }
  return ''
}

/**
 * 从五段式锚点取模块段（`产品:模块:表单:字段:动作`）。
 *
 * @param helpKey 锚点。
 * @returns 模块键（无则空串）。
 */
function moduleKeyOf(helpKey: string): string {
  return helpKey.split(':')[1] ?? ''
}

/**
 * 使用页面帮助上下文派生。
 *
 * @returns 帮助描述符与取数器。
 */
export function usePageHelpContext(): UsePageHelpContextResult {
  const route = useRoute() as ReturnType<typeof useRoute> | undefined
  const menu = useMenuStore()
  const fieldKey = ref<string | undefined>(undefined)
  const actionCode = ref<string | undefined>(undefined)

  const help = computed<HelpDescriptor>(() => {
    const path = route?.path ?? ''
    const moduleKey = moduleKeyOf(nearestMenuKey(menu.helpKeyByPath, path))
    const formId = menu.formIdByPath[path]
    const form = formId === undefined ? undefined : menu.forms[formId]
    const formKey = form?.businessCode ?? ''
    const context: HelpContextInput = {
      productKey: 'platform',
      ...(moduleKey === '' ? {} : { moduleKey }),
      ...(formKey === '' ? {} : { formKey }),
      ...(fieldKey.value === undefined ? {} : { fieldKey: fieldKey.value }),
      ...(actionCode.value === undefined ? {} : { actionCode: actionCode.value }),
    }
    return {
      context,
      anchorAvailable: moduleKey !== '' || (form?.helpKey ?? '') !== '',
      ready: resolveFetcher() !== undefined,
    }
  })

  return {
    help,
    fetcher: resolveFetcher(),
    setFieldKey: (value) => {
      fieldKey.value = value
    },
    setActionCode: (value) => {
      actionCode.value = value
    },
  }
}
