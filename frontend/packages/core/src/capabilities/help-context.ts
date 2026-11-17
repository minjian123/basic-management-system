/**
 * 帮助上下文能力基类：上下文解析 / 竞态 / 同上下文合并 / 失败重试（页面内帮助与顶栏共用）。
 *
 * 继承链：`BaseComponent → BasePlaceholderState → BaseDataState → BaseHelpContext`。
 * 取数经注入式 `fetcher`（未注入即抛 `19001`，不发请求）；核心不触 DOM、不请求、不缓存跨上下文。
 * 结果状态按 `matched` 落 `ready` / `empty`，失败落 `error` + 文案，不自动轮询。
 */

import { BaseError } from '../mechanisms/error'
import {
  buildHelpQuery,
  helpContextKey,
  normalizeHelpContext,
  normalizeHelpResult,
  type HelpArticle,
  type HelpArticleSummary,
  type HelpCategory,
  type HelpContextInput,
  type HelpLevel,
  type HelpResult,
} from '../domain/help'
import { BaseDataState } from './data-state'

/** 帮助取数器（线参数 + 上下文；返回后端 `data` 原样，由能力归一）。 */
export type HelpContextFetcher = (query: Record<string, string>, context?: HelpContextInput) => Promise<unknown>

/** 帮助上下文能力基类（抽象）。 */
export abstract class BaseHelpContext extends BaseDataState {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'help_context'
  /** 取数器（未注入即抛 `19001`）。 */
  fetcher: HelpContextFetcher | undefined
  /** 当前上下文。 */
  context: HelpContextInput = {}
  /** 解析结果（未解析 / 已重置为 `undefined`）。 */
  result: HelpResult | undefined
  /** 错误文案。 */
  errorMessage = ''
  /** 结果所属上下文键（上下文变化即失效）。 */
  #resultKey = ''
  /** 在途请求（同上下文合并）。 */
  #pending: { key: string; promise: Promise<HelpResult | undefined> } | undefined

  constructor() {
    super()
    this.setReady(false)
  }

  /** 是否登记了锚点（页面内入口显隐判据）。 */
  get anchorFound(): boolean {
    return this.result?.anchorFound === true
  }

  /** 是否命中可展示文章。 */
  get matched(): boolean {
    return this.result?.matched === true
  }

  /** 帮助入口是否可见（按锚点；顶栏常驻由件层处理）。 */
  get buttonVisible(): boolean {
    return this.anchorFound
  }

  /** 命中层级。 */
  get level(): HelpLevel | undefined {
    return this.result?.level
  }

  /** 命中锚点。 */
  get helpKey(): string | undefined {
    return this.result?.helpKey
  }

  /** 命中文章。 */
  get article(): HelpArticle | undefined {
    return this.result?.article
  }

  /** 相关内容。 */
  get related(): HelpArticleSummary[] {
    return this.result?.related ?? []
  }

  /** 分类列表。 */
  get categories(): HelpCategory[] {
    return this.result?.categories ?? []
  }

  /**
   * 注入取数器（`undefined` 表示移除）。
   *
   * @param fetcher 取数器。
   */
  setFetcher(fetcher: HelpContextFetcher | undefined): void {
    this.fetcher = fetcher
    this.touch()
  }

  /**
   * 设置上下文（变化即丢弃旧结果与错误态；首次显隐不触发请求）。
   *
   * @param context 上下文。
   */
  setContext(context: HelpContextInput): void {
    const next = normalizeHelpContext(context)
    if (helpContextKey(next) === helpContextKey(this.context)) {
      return
    }
    this.context = next
    this.result = undefined
    this.errorMessage = ''
    this.#resultKey = ''
    this.touch()
  }

  /**
   * 解析当前上下文（未就绪零请求；同上下文在途合并；已解析且未强制刷新时复用）。
   *
   * @param force 是否强制重取（重试 / 上下文外刷新用）。
   * @returns Promise<HelpResult | undefined>: 解析结果；未就绪 / 竞态丢弃时为 `undefined`。
   *
   * @throws BaseError: 已就绪但未注入取数器（`19001`）。
   */
  async resolve(force = false): Promise<HelpResult | undefined> {
    if (!this.ready) {
      return undefined
    }
    const key = helpContextKey(this.context)
    if (this.fetcher === undefined) {
      throw new BaseError(19001, '帮助取数器未注入（请先 setFetcher）')
    }
    const pending = this.#pending
    if (pending !== undefined && pending.key === key) {
      return pending.promise
    }
    if (!force && this.result !== undefined && this.#resultKey === key) {
      return this.result
    }

    const fetcher = this.fetcher
    const token = this.begin()
    this.markLoaded()
    const promise = this.#run(fetcher, key, token)
    this.#pending = { key, promise }
    try {
      return await promise
    } finally {
      if (this.#pending?.promise === promise) {
        this.#pending = undefined
      }
    }
  }

  /**
   * 重试（强制重取）。
   *
   * @returns Promise<HelpResult | undefined>: 解析结果。
   */
  async retry(): Promise<HelpResult | undefined> {
    return this.resolve(true)
  }

  /** 重置（清空上下文与结果；下一次解析从全局级开始）。 */
  reset(): void {
    this.context = {}
    this.result = undefined
    this.errorMessage = ''
    this.#resultKey = ''
    this.#pending = undefined
    this.settle(this.begin(), 'empty')
    this.touch()
  }

  /**
   * 执行一次解析（竞态与上下文键双校验）。
   *
   * @param fetcher 取数器。
   * @param key 上下文键。
   * @param token 竞态令牌。
   * @returns Promise<HelpResult | undefined>: 解析结果。
   */
  async #run(fetcher: HelpContextFetcher, key: string, token: number): Promise<HelpResult | undefined> {
    try {
      const raw = await fetcher(buildHelpQuery(this.context), { ...this.context })
      const normalized = normalizeHelpResult(raw)
      if (!this.settle(token, normalized.matched ? 'ready' : 'empty')) {
        return undefined
      }
      if (helpContextKey(this.context) !== key) {
        return undefined
      }
      this.result = normalized
      this.#resultKey = key
      this.errorMessage = ''
      this.touch()
      return normalized
    } catch (cause) {
      if (!this.settle(token, 'error')) {
        return undefined
      }
      this.result = undefined
      this.#resultKey = ''
      this.errorMessage = cause instanceof Error && cause.message !== '' ? cause.message : '帮助内容加载失败'
      this.touch()
      return undefined
    }
  }

  /** 广播更新（已释放则忽略）。 */
  protected touch(): void {
    if (!this.isDisposed) {
      this.notifyLifecycle('update')
    }
  }
}
