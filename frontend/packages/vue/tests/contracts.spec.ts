/** 契约用例工厂在 Vue 绑定侧的跑通（02-7）：`useValue` / `useAccess` 投影契约。 */

import { BaseAccess, BaseValue } from '@bms/core'
import {
  describePermissionContract,
  describeValueContract,
  type PermissionContractTarget,
  type ValueContractTarget,
} from '@bms/core/testing'

import { useAccess, useValue } from '../src'

/** 最小值实现（被投影对象）。 */
class DemoValue extends BaseValue<number> {}

/** 最小权限实现（被投影对象）。 */
class DemoAccess extends BaseAccess {}

describeValueContract<number>(
  '值契约（useValue 投影）',
  (): ValueContractTarget<number> => {
    const source = new DemoValue()
    const view = useValue(source)
    return {
      get value() {
        return view.value.value
      },
      get isEmpty() {
        return view.isEmpty.value
      },
      setValue: view.setValue,
      onChange: (listener) => source.onChange((next) => listener(next)),
    }
  },
  42,
)

describePermissionContract('权限契约（useAccess 投影）', (): PermissionContractTarget => {
  const source = new DemoAccess()
  const view = useAccess(source)
  return {
    get codes() {
      return view.codes.value
    },
    setCodes: (codes) => source.setCodes(codes),
    has: view.has,
    hasAny: view.hasAny,
    hasAll: view.hasAll,
  }
})
