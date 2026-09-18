/** 模块定义工厂：校验模块清单（名 / 版本）并冻结定义。 */

import { BaseError } from '../mechanisms/error'
import { ErrorCodes } from '../mechanisms/error-codes'

import type { ModuleDefinition } from './types'

/** 模块名合法模式（小写字母开头，可含数字与连字符）。 */
export const MODULE_NAME_PATTERN = /^[a-z][a-z0-9-]*$/

/**
 * 定义模块（校验清单并冻结）。
 *
 * @param definition 模块定义。
 * @returns 冻结后的模块定义。
 * @throws BaseError 模块名或版本非法（`CAPABILITY_VIOLATION`）。
 */
export function defineModule(definition: ModuleDefinition): ModuleDefinition {
  const { name, version } = definition.manifest
  if (!MODULE_NAME_PATTERN.test(name)) {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `模块名非法：${name}`)
  }
  if (version.trim() === '') {
    throw new BaseError(ErrorCodes.CAPABILITY_VIOLATION, `模块版本缺失：${name}`)
  }
  return Object.freeze({ manifest: Object.freeze({ ...definition.manifest }), setup: definition.setup })
}
