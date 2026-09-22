/** 活动模块作用域：加载 / 挂载期间与模块路由停留期间标注「当前模块」，供上报与归因取用。 */

/** 活动模块标识（模块名 + 版本）。 */
export interface ActiveModule {
  /** 模块名。 */
  name: string
  /** 模块版本。 */
  version: string
}

/** 当前活动模块（无活动模块为 `null`）。 */
let active: ActiveModule | null = null

/**
 * 设置活动模块。
 *
 * @param name 模块名。
 * @param version 模块版本。
 */
export function setActiveModule(name: string, version: string): void {
  active = { name, version }
}

/** 清除活动模块（平台页面 / 非模块路由）。 */
export function clearActiveModule(): void {
  active = null
}

/** 读取当前活动模块（无则 `null`）。 */
export function activeModule(): ActiveModule | null {
  return active
}

/**
 * 在活动模块作用域内执行（加载 / 挂载期；结束恢复上一层作用域）。
 *
 * @param name 模块名。
 * @param version 模块版本。
 * @param task 待执行任务。
 * @returns 任务结果。
 */
export async function withModuleScope<T>(name: string, version: string, task: () => Promise<T>): Promise<T> {
  const previous = active
  setActiveModule(name, version)
  try {
    return await task()
  } finally {
    active = previous
  }
}
