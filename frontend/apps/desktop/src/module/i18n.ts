/**
 * 模块文案承载实例（宿主单例）：模块文案并入 / 还原。
 *
 * 宿主暂不引入国际化库（归国际化阶段）——接入后以适配层替换内部实现（并入 → 语言包合并、
 * 还原 → 语言包移除），对外接口不变。
 */

import { ModuleMessageStore } from '@bms/core'

/** 模块文案承载（缺省语言与项目 locale 口径一致，键内小写）。 */
export const moduleI18n = new ModuleMessageStore('zh-cn')
