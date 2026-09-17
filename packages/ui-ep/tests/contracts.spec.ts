/**
 * 契约套件执行（S4a）：ui-ep 实现跑 `@bms/core/testing` 的同一套断言。
 *
 * 与 `@bms/ui-vant` 侧的契约套件同源——「同接口多实现」的机器保障。
 */

import { describeConfirmContract, describePermissionContract } from '@bms/core/testing'

import { checkPerm, configurePermissionChecker, configureConfirm, confirm } from '../src'

describeConfirmContract({
  configure: configureConfirm,
  confirm,
})

describePermissionContract({
  configure: configurePermissionChecker,
  check: checkPerm,
})
