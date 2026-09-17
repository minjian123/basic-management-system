/** 输入控件契约（`@bms/core/testing` 工厂；`ui-ep` / `ui-vant` 跑同一套断言）。 */

import { describeInputControlsContract } from '@bms/core/testing'

import { contractKit } from './helpers/contract-kit'

describeInputControlsContract(contractKit)
