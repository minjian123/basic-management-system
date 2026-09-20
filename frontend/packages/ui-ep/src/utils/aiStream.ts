/**
 * 浏览器原生 SSE 流适配器（08_10）：`fetch` + `ReadableStream` 解析服务端事件流（POST 携带请求头与 Body）。
 *
 * 浏览器 API（`fetch` / `ReadableStream` / `AbortController`）集中在本文件；核心与投影不触 DOM。
 * 未注入适配器时能力基类即占位（不发请求）；本适配器为可选的真实通路实现。
 */

import type { AiChatRequest, AiStreamAdapter, AiStreamDonePayload, AiStreamHandlers } from '@bms/core'

/** SSE 流适配器选项。 */
export interface SseStreamAdapterOptions {
  /** 流式端点（缺省 `/api/v1/ai/chat/stream`）。 */
  endpoint?: string
  /** 请求头（含鉴权，由宿主注入；支持函数以动态取 token）。 */
  headers?: Record<string, string> | (() => Record<string, string>)
  /** 单行解析（缺省按 `data:` 行 JSON 解析 `{ delta | done | auditId | result | citations | risks | error }`）。 */
  parse?: (line: string) => AiStreamDonePayload | { delta: string } | { error: unknown } | undefined
}

/** 缺省单行解析。 */
function defaultParse(line: string): AiStreamDonePayload | { delta: string } | { error: unknown } | undefined {
  const text = line.trim()
  if (text === '' || text === '[DONE]') {
    return undefined
  }
  try {
    const payload = JSON.parse(text) as Record<string, unknown>
    if (typeof payload.error === 'string') {
      return { error: new Error(payload.error) }
    }
    if (typeof payload.delta === 'string') {
      return { delta: payload.delta }
    }
    return {
      auditId: payload.auditId as string | undefined,
      result: payload.result,
      citations: payload.citations,
      risks: payload.risks,
    }
  } catch {
    return { delta: text }
  }
}

/**
 * 解析请求头。
 *
 * @param headers 请求头配置。
 * @returns 请求头对象。
 */
function resolveHeaders(headers: SseStreamAdapterOptions['headers']): Record<string, string> {
  if (typeof headers === 'function') {
    return { ...headers() }
  }
  return { ...(headers ?? {}) }
}

/**
 * 派发一行 SSE 数据。
 *
 * @param line 原始行。
 * @param parse 解析函数。
 * @param handlers 流式回调。
 */
function dispatchLine(
  line: string,
  parse: SseStreamAdapterOptions['parse'],
  handlers: AiStreamHandlers,
): void {
  const raw = line.startsWith('data:') ? line.slice(5) : line
  const parsed = (parse ?? defaultParse)(raw)
  if (parsed === undefined) {
    return
  }
  if ('error' in parsed) {
    handlers.onError(parsed.error)
    return
  }
  if ('delta' in parsed) {
    handlers.onChunk(parsed.delta)
    return
  }
  handlers.onDone(parsed)
}

/**
 * 创建浏览器原生 SSE 流适配器。
 *
 * @param options 选项。
 * @returns 流式适配器。
 */
export function createSseStreamAdapter(options: SseStreamAdapterOptions = {}): AiStreamAdapter {
  const endpoint = options.endpoint ?? '/api/v1/ai/chat/stream'
  return {
    start({ request, handlers }) {
      const controller = new AbortController()
      const run = async (): Promise<void> => {
        if (typeof fetch !== 'function' || typeof TextDecoder !== 'function') {
          handlers.onError(new Error('当前环境不支持流式请求'))
          return
        }
        try {
          const response = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', ...resolveHeaders(options.headers) },
            body: JSON.stringify(toBody(request)),
            signal: controller.signal,
          })
          if (!response.ok) {
            throw new Error(`流式请求失败（${response.status}）`)
          }
          if (response.body === null) {
            handlers.onError(new Error('流式响应为空'))
            return
          }
          const reader = response.body.getReader()
          const decoder = new TextDecoder()
          let buffer = ''
          for (;;) {
            const { done, value } = await reader.read()
            if (done) {
              break
            }
            buffer += decoder.decode(value, { stream: true })
            const lines = buffer.split('\n')
            buffer = lines.pop() ?? ''
            for (const line of lines) {
              dispatchLine(line, options.parse, handlers)
            }
          }
          if (buffer.trim() !== '') {
            dispatchLine(buffer, options.parse, handlers)
          }
        } catch (error) {
          if (error instanceof Error && error.name === 'AbortError') {
            return
          }
          handlers.onError(error)
        }
      }
      void run()
      return {
        abort: () => {
          controller.abort()
        },
      }
    },
  }
}

/**
 * 组装请求体（与后端对话接口字段同源）。
 *
 * @param request 请求。
 * @returns 请求体。
 */
function toBody(request: AiChatRequest): Record<string, unknown> {
  const body: Record<string, unknown> = {
    module: request.mode,
    content: request.content,
  }
  if (request.sessionId !== undefined) {
    body.session_id = request.sessionId
  }
  if (request.datasetId !== undefined) {
    body.dataset_id = request.datasetId
  }
  if (request.fileIds !== undefined) {
    body.file_ids = request.fileIds
  }
  return body
}
