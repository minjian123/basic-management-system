/**
 * 用户扩展信息数据通路（后端契约：platform 服务 `/api/v1/user-extensions`）。
 *
 * 一律经宿主注入的 `api` 能力按「服务键 + 资源子路径」调用——模块**不接触凭据、不感知服务寻址、
 * 不自建 HTTP**；统一响应解包与 401 静默刷新由宿主请求层处理（模块无 401 逻辑）。
 */

import type { ModuleApi } from '@bms/core'

import { hostApiOf } from '../runtime'

/** API 服务键（契约由 platform 服务承载）。 */
const SERVICE_KEY = 'platform'
/** 资源子路径（服务内前缀 `/api/v1` 由宿主组装）。 */
const RESOURCE = '/user-extensions'

/** 扩展信息行（与后端契约同形；整型字段以字符串承载）。 */
export interface UserExtensionItem {
  /** 主键（雪花 ID）。 */
  id: string
  /** 用户主键。 */
  user_id: string
  /** 扩展标签。 */
  label: string
  /** 备注。 */
  remark: string | null
  /** 创建时间（UTC）。 */
  created_at: string
  /** 更新时间（UTC）。 */
  updated_at: string
}

/** 扩展信息列表载荷。 */
export interface UserExtensionList {
  /** 行列表。 */
  items: UserExtensionItem[]
}

/** 宿主未注入请求能力（调用方降级，不假定存在）。 */
export class ModuleApiUnavailableError extends Error {
  /** 构造。 */
  constructor() {
    super('宿主未注入请求能力（api）')
    this.name = 'ModuleApiUnavailableError'
  }
}

/**
 * 取宿主请求能力（未注入即抛错，由调用方降级）。
 *
 * @returns 请求能力。
 * @throws ModuleApiUnavailableError 未注入请求能力。
 */
function requireApi(): ModuleApi {
  const api = hostApiOf()
  if (api === undefined) {
    throw new ModuleApiUnavailableError()
  }
  return api
}

/**
 * 按用户列示扩展信息。
 *
 * @param userId 用户主键（路由参数）。
 * @returns 扩展信息行列表。
 */
export async function listUserExtensions(userId: string): Promise<UserExtensionItem[]> {
  const data = await requireApi().get<UserExtensionList>(SERVICE_KEY, RESOURCE, { user_id: userId })
  return data.items ?? []
}

/**
 * 新增一条扩展信息。
 *
 * @param input 用户主键 / 标签 / 备注。
 * @returns 新建行。
 */
export async function createUserExtension(input: {
  userId: string
  label: string
  remark?: string | null
}): Promise<UserExtensionItem> {
  return requireApi().post<UserExtensionItem>(SERVICE_KEY, RESOURCE, {
    user_id: Number(input.userId),
    label: input.label,
    remark: input.remark ?? null,
  })
}

/**
 * 更新一条扩展信息（整体替换标签与备注）。
 *
 * @param extensionId 扩展信息主键。
 * @param input 标签 / 备注。
 * @returns 更新后行。
 */
export async function updateUserExtension(
  extensionId: string,
  input: { label: string; remark?: string | null },
): Promise<UserExtensionItem> {
  return requireApi().put<UserExtensionItem>(SERVICE_KEY, `${RESOURCE}/${extensionId}`, {
    label: input.label,
    remark: input.remark ?? null,
  })
}
