/** 契约用例工厂自测（02-7）：以核心最小实现跑 5 套契约断言。 */

import { BaseAccess, BaseContainer, BaseFeedback, BaseValue } from '../src'
import {
  describeConfirmContract,
  describeContainerContract,
  describeFeedbackContract,
  describePermissionContract,
  describeValueContract,
} from '../testing'

/** 最小值实现。 */
class DemoValue extends BaseValue<number> {}

/** 最小权限实现。 */
class DemoAccess extends BaseAccess {}

/** 最小反馈实现。 */
class DemoFeedback extends BaseFeedback {}

/** 最小容器实现。 */
class DemoContainer extends BaseContainer {}

describeValueContract('值契约（BaseValue 实现）', () => new DemoValue(), 42)
describePermissionContract('权限契约（BaseAccess 实现）', () => new DemoAccess())
describeFeedbackContract('反馈契约（BaseFeedback 实现）', () => new DemoFeedback())
describeContainerContract('容器契约（BaseContainer 实现）', () => new DemoContainer())

describeConfirmContract('确认契约（登记入口冒烟）', () => {
  let open = false
  let resolver: ((value: boolean) => void) | undefined
  return {
    get open() {
      return open
    },
    confirm: () => {
      open = true
      return new Promise<boolean>((resolve) => {
        resolver = resolve
      })
    },
    resolve: (value: boolean) => {
      open = false
      resolver?.(value)
      resolver = undefined
    },
  }
})
