/**
 * 宿主能力装配：字典 / 远程字典 / 上传 / 验证码 / 通知 / 审计的默认数据源（单一落点）。
 *
 * 组件仍以 Props 注入（`source` / `transport` / `jobs` / `query`），不读全局单例；
 * 页面与核对页经 `useAppCapabilities()` 取默认实例。未装配即抛 `19001`，不静默降级。
 */

import {
  BaseError,
  type BaseCaptchaSource,
  type BaseDictRemoteSource,
  type BaseDictSource,
  type BaseUploadTransport,
  type HelpContextFetcher,
  type NotificationJobs,
} from '@bms/core'
import {
  createHttpAuditQuery,
  createHttpCaptchaSource,
  createHttpDictRemoteSource,
  createHttpDictSource,
  createHttpHelpFetcher,
  createHttpNotificationJobs,
  createHttpUploadTransport,
  type AuditQueryAdapter,
} from '@bms/ui_ep'

import {
  auditOptions,
  captchaSourceOptions,
  dictRemoteSourceOptions,
  dictSourceOptions,
  helpOptions,
  notificationOptions,
  uploadTransportOptions,
} from './api/endpoints'

/** 宿主能力集合（默认实现）。 */
export interface AppCapabilities {
  /** 字典数据源（平台服务）。 */
  dictSource: BaseDictSource
  /** 远程字典数据源（产品服务，目录推导）。 */
  dictRemoteSource: BaseDictRemoteSource
  /** 文件上传通路（文件服务）。 */
  uploadTransport: BaseUploadTransport
  /** 验证码数据源（身份服务）。 */
  captchaSource: BaseCaptchaSource
  /** 通知取数处理函数（通知服务）。 */
  notificationJobs: NotificationJobs
  /** 审计取数适配器（平台服务）。 */
  auditQuery: AuditQueryAdapter
  /** 页面内帮助取数器（平台服务）。 */
  helpFetcher: HelpContextFetcher
}

/** 已装配能力（单例；未装配为 `undefined`）。 */
let installed: AppCapabilities | undefined

/**
 * 装配宿主能力（幂等；重复调用返回同一实例）。
 *
 * @returns 已装配能力。
 */
export function installAppCapabilities(): AppCapabilities {
  if (installed !== undefined) {
    return installed
  }
  installed = {
    dictSource: createHttpDictSource(dictSourceOptions()),
    dictRemoteSource: createHttpDictRemoteSource(dictRemoteSourceOptions()),
    uploadTransport: createHttpUploadTransport(uploadTransportOptions()),
    captchaSource: createHttpCaptchaSource(captchaSourceOptions()),
    notificationJobs: createHttpNotificationJobs(notificationOptions()),
    auditQuery: createHttpAuditQuery(auditOptions()),
    helpFetcher: createHttpHelpFetcher(helpOptions()),
  }
  return installed
}

/**
 * 取已装配能力（未装配即抛 `19001`，不静默降级）。
 *
 * @returns 已装配能力。
 */
export function getAppCapabilities(): AppCapabilities {
  if (installed === undefined) {
    throw new BaseError(19001, '宿主能力未装配（请先调用 installAppCapabilities）')
  }
  return installed
}

/** 复位装配（测试 / 切换会话用；生产启动期不调用）。 */
export function resetAppCapabilities(): void {
  installed = undefined
}
