/**
 * `@bms/core/testing`：契约用例工厂（仅测试消费）。
 *
 * 各渲染插件（`ui-ep` / `ui-vant`）在自己的 spec 中调用本工厂并传入本实现，
 * 跑同一套断言——「同接口多实现」的机器保障。运行时入口（`@bms/core`）不含本入口。
 *
 * 本期只交付统一登记入口；具体契约套件（值 / 字段 / 输入 / 确认 / 权限 / 容器件 / 反馈件等）
 * 随 `02_03` / `02_04` / `02_05` 就位后在本文件追加导出。
 */

import { describe } from 'vitest'

/** 契约用例套件定义体。 */
export type ContractDefine = () => void

/**
 * 登记一个契约用例套件（「同一契约、多实现」的统一入口）。
 *
 * @param name 契约名（如「受控值契约」）。
 * @param define 套件定义体（在各实现 spec 中传入本实现后执行同一套断言）。
 */
export function describeContract(name: string, define: ContractDefine): void {
  describe(name, define)
}
