/**
 * 宿主统一提示（会话失效等）。
 *
 * 请求层不依赖 UI 库——提示经宿主入口注入（《前端开发规范》§11）；宿主暂未引入国际化库
 * （见 `module/i18n.ts` 说明，归国际化阶段），故提示文案为宿主常量；错误码 → 文案映射随登录页
 * （`05_01`）与国际化阶段落地。
 */

import { ElMessage } from 'element-plus'
import 'element-plus/es/components/message/style/css'

/** 会话失效提示文案。 */
export const SESSION_EXPIRED_MESSAGE = '登录状态已失效，请重新登录'

/**
 * 提示会话失效。
 *
 * @param message 提示文案（缺省 `SESSION_EXPIRED_MESSAGE`）。
 */
export function notifySessionExpired(message: string = SESSION_EXPIRED_MESSAGE): void {
  ElMessage.warning(message)
}
