#!/usr/bin/env node
/**
 * 本机发布存储静态服务（零依赖；演练与本地联调形态；见任务 03_02 详细设计 §3.7）。
 *
 * 托管 `frontend/releases/**`：URL 即 `/模块名/版本/remoteEntry.js`，与清单 `entry` 同构——
 * 宿主按清单加载归档产物，多版本并存，回滚演练端到端可跑。生产由 nginx / CDN 托管版本目录
 * （部署阶段落地），本服务不承担生产职责。
 *
 * 用法：
 *     node frontend/scripts/serve-module-releases.mjs [--root <frontend 目录>] [--port 5002] [--host 127.0.0.1]
 */
import { createServer } from 'node:http'
import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { extname, join, normalize, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'
import { exit } from 'node:process'

/**
 * `frontend/` 目录（本文件位于 `frontend/scripts/`）。
 *
 * Node 直跑按脚本位置推断；经 Vite / Vitest 载入时 `import.meta.url` 非 `file:` 协议，
 * 回退按测试工程目录（`apps/desktop` / `modules/<模块名>` 均为 `frontend/` 下两级）推断；
 * 调用方亦可显式传入目录（导出函数选项）。
 */
const FRONTEND_DIR = (() => {
  if (import.meta.url.startsWith('file:')) return resolve(fileURLToPath(import.meta.url), '..', '..')
  return resolve(process.cwd(), '..', '..')
})()

/** 发布存储目录名（相对 `frontend/`）。 */
export const RELEASES_DIR = 'releases'

/** 缺省端口 / 主机（与演示清单地址一致）。 */
export const DEFAULT_PORT = 5002
export const DEFAULT_HOST = '127.0.0.1'

/** 扩展名 → MIME（覆盖模块产物与常见静态资源）。 */
const MIME_TYPES = {
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.html': 'text/html; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.jpg': 'image/jpeg',
  '.jpeg': 'image/jpeg',
  '.gif': 'image/gif',
  '.webp': 'image/webp',
  '.ico': 'image/x-icon',
  '.woff': 'font/woff',
  '.woff2': 'font/woff2',
  '.ttf': 'font/ttf',
  '.map': 'application/json; charset=utf-8',
  '.txt': 'text/plain; charset=utf-8',
}

/**
 * 取 MIME 类型（未知扩展名回落 `application/octet-stream`）。
 *
 * @param file 文件路径。
 * @returns MIME 类型。
 */
export function mimeTypeOf(file) {
  return MIME_TYPES[extname(file).toLowerCase()] ?? 'application/octet-stream'
}

/**
 * 解析请求路径到发布存储内文件（防路径穿越）。
 *
 * @param releasesRoot 发布存储根。
 * @param urlPath 请求路径（已去查询串）。
 * @returns 文件绝对路径（越界返回 `undefined`）。
 */
export function resolveRequestPath(releasesRoot, urlPath) {
  const decoded = decodeURIComponent(urlPath)
  const target = resolve(releasesRoot, `.${normalize(decoded)}`)
  if (target !== releasesRoot && !target.startsWith(releasesRoot + sep)) return undefined
  return target
}

/**
 * 渲染发布存储索引（模块 → 已归档版本）。
 *
 * @param releasesRoot 发布存储根。
 * @returns HTML 文本。
 */
export function renderIndex(releasesRoot) {
  const rows = []
  if (existsSync(releasesRoot)) {
    for (const moduleEntry of readdirSync(releasesRoot, { withFileTypes: true })) {
      if (!moduleEntry.isDirectory()) continue
      const moduleDir = join(releasesRoot, moduleEntry.name)
      const versions = readdirSync(moduleDir, { withFileTypes: true })
        .filter((item) => item.isDirectory())
        .map((item) => item.name)
        .sort()
      rows.push(`<li>${moduleEntry.name}：${versions.length > 0 ? versions.join(' / ') : '（无归档版本）'}</li>`)
    }
  }
  return `<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>模块发布存储</title><body><h1>模块发布存储</h1><ul>${rows.join('')}</ul></body></html>`
}

/**
 * 启动服务。
 *
 * @param options `{ root?, port?, host? }`。
 * @returns HTTP 服务实例。
 */
export function createReleaseServer(options = {}) {
  const frontendDir = resolve(options.root ?? FRONTEND_DIR)
  const releasesRoot = resolve(frontendDir, RELEASES_DIR)
  const port = Number(options.port ?? DEFAULT_PORT)
  const host = options.host ?? DEFAULT_HOST
  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error(`端口非法：${String(options.port)}`)
  }

  const server = createServer((request, response) => {
    const method = request.method ?? 'GET'
    const headers = {
      'Access-Control-Allow-Origin': '*',
      'Cache-Control': 'no-cache',
      'X-Content-Type-Options': 'nosniff',
    }
    if (method !== 'GET' && method !== 'HEAD') {
      response.writeHead(405, { ...headers, Allow: 'GET, HEAD' })
      response.end('Method Not Allowed')
      return
    }
    const urlPath = (request.url ?? '/').split('?')[0]
    if (urlPath === '/' || urlPath === '/index.html') {
      const body = renderIndex(releasesRoot)
      response.writeHead(200, { ...headers, 'Content-Type': MIME_TYPES['.html'] })
      response.end(method === 'HEAD' ? undefined : body)
      return
    }
    const file = resolveRequestPath(releasesRoot, urlPath)
    if (file === undefined || !existsSync(file) || !statSync(file).isFile()) {
      response.writeHead(404, { ...headers, 'Content-Type': MIME_TYPES['.txt'] })
      response.end(`Not Found: ${urlPath}`)
      return
    }
    const body = readFileSync(file)
    response.writeHead(200, { ...headers, 'Content-Type': mimeTypeOf(file), 'Content-Length': body.length })
    response.end(method === 'HEAD' ? undefined : body)
  })

  server.listen(port, host, () => {
    console.log(`[module-releases] 发布存储已启动：http://${host}:${port}/（根目录 ${releasesRoot}）`)
    console.log(`[module-releases] 模块入口形如 http://${host}:${port}/<模块名>/<版本>/remoteEntry.js`)
  })
  return server
}

/**
 * CLI 入口。
 *
 * @param argv 进程参数。
 */
function main(argv) {
  const valueOf = (flag) => {
    const index = argv.indexOf(flag)
    return index >= 0 ? argv[index + 1] : undefined
  }
  try {
    createReleaseServer({ root: valueOf('--root'), port: valueOf('--port'), host: valueOf('--host') })
  } catch (error) {
    console.error(`[module-releases] 启动失败：${error instanceof Error ? error.message : String(error)}`)
    exit(1)
  }
}

if (
  import.meta.url.startsWith('file:') &&
  process.argv[1] !== undefined &&
  resolve(process.argv[1]) === fileURLToPath(import.meta.url)
) {
  main(process.argv)
}
