/**
 * `serve-module-releases.mjs` 的类型声明（供用例在 TS 下直接引用；纯类型，无运行期产物）。
 */

import type { Server } from 'node:http'

/** 发布存储目录名（相对 `frontend/`）。 */
export const RELEASES_DIR: string

/** 缺省端口。 */
export const DEFAULT_PORT: number

/** 缺省主机。 */
export const DEFAULT_HOST: string

/** 取 MIME 类型（未知扩展名回落 `application/octet-stream`）。 */
export function mimeTypeOf(file: string): string

/** 解析请求路径到发布存储内文件（防路径穿越；越界返回 `undefined`）。 */
export function resolveRequestPath(releasesRoot: string, urlPath: string): string | undefined

/** 渲染发布存储索引（模块 → 已归档版本）。 */
export function renderIndex(releasesRoot: string): string

/** 启动服务。 */
export function createReleaseServer(options?: { root?: string; port?: number | string; host?: string }): Server
