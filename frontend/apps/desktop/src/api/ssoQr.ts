/**
 * 扫码登录状态源（宿主机内建实现）：真实取授权 URL + 占位轮询。
 *
 * - `init` 经 `fetchSsoAuthorizeInfo` 真实调用后端 `authorize-url` 取授权 URL / `state` / 有效期；
 * - `poll` 为**占位实现**（恒 `pending`、零请求、零副作用）——后端不做扫码轮询状态机与
 *   会话旁路存储，且平台不对外暴露「已扫」态；四态流转由可注入状态源 / 测试夹具覆盖，
 *   真实平台适配（企微 `@wecom/jssdk` / 钉钉内嵌登录或后端状态端点）归阶段十七。
 */

import type { SsoQrLoginSourceAdapter } from '@bms/core'

import { fetchSsoAuthorizeInfo } from './identity'
import { getTenantCode } from './tenant'

/**
 * 构造宿主扫码登录状态源（取授权 URL + 占位轮询）。
 *
 * @returns 状态源。
 */
export function createHttpSsoQrSource(): SsoQrLoginSourceAdapter {
  return {
    init: ({ idpKey, tenant }) => fetchSsoAuthorizeInfo(idpKey, tenant ?? getTenantCode()),
    poll: () => Promise.resolve({ status: 'pending' }),
  }
}
