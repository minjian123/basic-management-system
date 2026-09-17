/** 反馈件契约套件执行（03-2-1）：ui-ep 跑 `@bms/core/testing` 的反馈件同一套断言。 */

import { describeFeedbackComponentsContract } from '@bms/core/testing'

import { contractKit } from './helpers/contract-kit'

describeFeedbackComponentsContract(contractKit)
