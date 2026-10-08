/**
 * `check-shared-deps.mjs` 的类型声明（供宿主用例在 TS 下直接引用；纯类型，无运行期产物）。
 */

/** 共享依赖产物级断言结果。 */
export interface SharedDepsResult {
  /** 违规清单（空数组即通过）。 */
  problems: string[]
  /** 单一来源共享面（包名，排序）。 */
  sharedNames: string[]
  /** 参与断言的模块名清单。 */
  moduleNames: string[]
}

/** 共享依赖产物级断言（宿主 × 每个在册仓内模块；跨仓模块由发布时强校验承担）。 */
export function checkSharedDeps(options?: { frontendDir?: string }): SharedDepsResult
