/** 反馈组合式：基于核心 `BaseFeedback` 投影四态状态机与降级重试。 */

import { BaseFeedback, type FeedbackState } from '@bms/core'
import { onScopeDispose, ref, type Ref } from 'vue'

/** 具体反馈件（可实例化）。 */
class Feedback extends BaseFeedback {}

/** `useFeedback` 返回面。 */
export interface UseFeedbackResult {
  /** 当前状态（响应式）。 */
  state: Ref<FeedbackState>
  /** 置为加载中。 */
  begin: () => void
  /** 置为就绪。 */
  ready: () => void
  /** 置为空。 */
  empty: () => void
  /** 置为错误。 */
  error: () => void
  /** 注入重试回调。 */
  setRetry: (retry: (() => void) | undefined) => void
  /** 触发重试（仅错误态；未触发返回 `false`）。 */
  retry: () => boolean
}

/**
 * 使用反馈组合式。
 *
 * @returns 反馈状态与操作方法。
 */
export function useFeedback(): UseFeedbackResult {
  const feedback = new Feedback()
  const state = ref<FeedbackState>(feedback.state)
  const off = feedback.onLifecycle((event) => {
    if (event === 'update') {
      state.value = feedback.state
    }
  })
  onScopeDispose(off)

  return {
    state,
    begin: () => feedback.setState('loading'),
    ready: () => feedback.setState('ready'),
    empty: () => feedback.setState('empty'),
    error: () => feedback.setState('error'),
    setRetry: (retry) => {
      feedback.retry = retry
    },
    retry: () => feedback.doRetry(),
  }
}
