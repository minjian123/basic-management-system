/** 组件契约套件执行（S4b）：ui-vant 跑 `@bms/core/testing` 的容器件 / 权限按钮同一套断言。 */

import { describeContainerComponentsContract, describePermButtonContract } from '@bms/core/testing'

import { contractKit } from './helpers/contract-kit'

describeContainerComponentsContract(contractKit)
describePermButtonContract(contractKit)
