/**
 * 上传通路插件基类与提供者注册表：上传通路为**可替换实现（纵向）**——
 * 内建 / 定制实现继承 `BaseUploadTransport`，经 `UploadTransportRegistry` 登记接入；
 * 未登记 / 未注入时上传引擎即占位（不发请求）。
 *
 * 方法与后端对象存储扩展基座（`02-4-18`）及冻结的契约缺口一一对应：
 * 分片 `initiate` / `upload_part` / `complete` / `abort` / `check`（`/api/v1/files/*`）、
 * 已传分片查询、批量元数据、整包上传与下载 / 预览预签名（只增不改，登记后端需求）。
 */

import { BaseProviderRegistry } from '../mechanisms/registry'
import { BaseProvider } from '../mechanisms/provider'
import { BasePluggable } from '../mechanisms/pluggable'
import type { UploadAbortSignal } from '../domain/file'
import type { UploadProgressReporter } from './upload-engine'

/** 整包上传入参。 */
export interface UploadWholeQuery {
  /** 文件对象（透传实现，核心不触）。 */
  file: unknown
  /** 目标对象键（缺省由实现生成）。 */
  key?: string
  /** 文件名。 */
  name: string
  /** 字节数。 */
  size: number
  /** 内容类型。 */
  mime: string
  /** 整文件 SHA-256（可选）。 */
  sha256?: string
  /** 进度回传（可选）。 */
  report?: UploadProgressReporter
  /** 中断信号（可选）。 */
  signal?: UploadAbortSignal
}

/** 秒传判定入参。 */
export interface UploadCheckQuery {
  /** 整文件 SHA-256。 */
  sha256: string
  /** 文件字节数。 */
  size: number
}

/** 分片初始化入参。 */
export interface UploadInitQuery {
  /** 目标对象键（缺省由实现生成）。 */
  key?: string
  /** 文件名。 */
  name: string
  /** 字节数。 */
  size: number
  /** 内容类型。 */
  mime: string
  /** 整文件 SHA-256（可选）。 */
  sha256?: string
  /** 分片大小（字节，可选）。 */
  partSize?: number
}

/** 分片上传入参（`file` 与字节区间由引擎下发，切片归通路实现）。 */
export interface UploadPartQuery {
  /** 会话标识。 */
  uploadId: string
  /** 分片序号（从 1 起）。 */
  partNo: number
  /** 文件对象（透传实现）。 */
  file: unknown
  /** 起始字节（含）。 */
  start: number
  /** 结束字节（不含）。 */
  end: number
  /** 分片 SHA-256（可选，供后端校验）。 */
  sha256?: string
  /** 中断信号（可选）。 */
  signal?: UploadAbortSignal
}

/** 会话查询 / 合并 / 取消入参。 */
export interface UploadSessionQuery {
  /** 会话标识。 */
  uploadId: string
}

/** 批量元数据入参（一次批量，避免 N+1）。 */
export interface UploadResolveQuery {
  /** 文件标识列表。 */
  ids: readonly string[]
}

/** 预签名入参（供 `BasePresignedUrl` 装配）。 */
export interface UploadPresignQuery {
  /** 文件标识。 */
  fileId: string
  /** 用途。 */
  purpose: 'preview' | 'download'
  /** 期望有效期（秒，可选）。 */
  expiresIn?: number
}

/** 哈希入参。 */
export interface UploadHashQuery {
  /** 文件对象（透传实现）。 */
  file: unknown
  /** 分片大小（字节，可选；用于产出每片哈希）。 */
  partSize?: number
  /** 中断信号（可选）。 */
  signal?: UploadAbortSignal
}

/** 上传通路契约面（方法与 `BaseUploadTransport` 一致；未覆写的方法返回 `undefined`，即不请求）。 */
export interface UploadTransportAdapter {
  /** 整文件（含每片）哈希。 */
  hash?(query: UploadHashQuery): Promise<unknown>
  /** 秒传判定。 */
  check?(query: UploadCheckQuery): Promise<unknown>
  /** 整包上传。 */
  uploadWhole?(query: UploadWholeQuery): Promise<unknown>
  /** 分片初始化。 */
  initiate?(query: UploadInitQuery): Promise<unknown>
  /** 分片上传。 */
  uploadPart?(query: UploadPartQuery): Promise<unknown>
  /** 分片合并。 */
  complete?(query: UploadSessionQuery): Promise<unknown>
  /** 取消会话。 */
  abort?(query: UploadSessionQuery): Promise<unknown>
  /** 已传分片查询（断点续传）。 */
  listParts?(query: UploadSessionQuery): Promise<unknown>
  /** 批量元数据。 */
  resolveFiles?(query: UploadResolveQuery): Promise<unknown>
  /** 下载 / 预览预签名。 */
  presign?(query: UploadPresignQuery): Promise<unknown>
}

/** 通路装载选项。 */
export interface UploadTransportOptions {
  /** 端点前缀（缺省 `/api/v1`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
}

/** 上传通路插件基类（抽象；未覆写的方法返回 `undefined`，即不请求）。 */
export abstract class BaseUploadTransport extends BasePluggable implements UploadTransportAdapter {
  /** 插件键。 */
  readonly pluginKey: string = 'upload-transport'
  /** 实现名（具体实现覆写）。 */
  readonly pluginName: string = 'base'

  /**
   * 整文件（含每片）哈希。
   *
   * @param query 哈希入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  hash(query: UploadHashQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 秒传判定。
   *
   * @param query 判定入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  check(query: UploadCheckQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 整包上传。
   *
   * @param query 上传入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  uploadWhole(query: UploadWholeQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 分片初始化。
   *
   * @param query 初始化入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  initiate(query: UploadInitQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 分片上传。
   *
   * @param query 分片入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  uploadPart(query: UploadPartQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 分片合并。
   *
   * @param query 会话入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  complete(query: UploadSessionQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 取消会话。
   *
   * @param query 会话入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  abort(query: UploadSessionQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 已传分片查询（断点续传）。
   *
   * @param query 会话入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  listParts(query: UploadSessionQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 批量元数据。
   *
   * @param query 批量入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  resolveFiles(query: UploadResolveQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }

  /**
   * 下载 / 预览预签名。
   *
   * @param query 预签名入参。
   * @returns 原始结果（缺省 `undefined`）。
   */
  presign(query: UploadPresignQuery): Promise<unknown> {
    void query
    return Promise.resolve(undefined)
  }
}

/** 通路注册项（工厂创建插件实例）。 */
export class UploadTransportProvider extends BaseProvider {
  /** 注册键。 */
  readonly key: string
  /** 工厂（按选项创建通路实例）。 */
  readonly create: (options: UploadTransportOptions) => BaseUploadTransport | Promise<BaseUploadTransport>

  /**
   * 构造注册项。
   *
   * @param key 通路键（如 `http`）。
   * @param create 通路工厂。
   */
  constructor(key: string, create: (options: UploadTransportOptions) => BaseUploadTransport | Promise<BaseUploadTransport>) {
    super()
    this.key = key
    this.create = create
  }
}

/** 通路注册表（统一注册表基座；同键唯一性拒重）。 */
export class UploadTransportRegistry extends BaseProviderRegistry<UploadTransportProvider> {
  /** 插件键。 */
  readonly pluginKey = 'upload-transport-registry'
  /** 实现名。 */
  readonly pluginName = 'core'

  /**
   * 注册项键。
   *
   * @param provider 注册项。
   * @returns 注册项键。
   */
  protected providerKey(provider: UploadTransportProvider): string {
    return provider.key
  }
}
