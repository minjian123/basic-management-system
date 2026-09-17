/**
 * `@bms/core/testing`：契约用例工厂（仅测试消费）。
 *
 * 各渲染插件（`ui-ep` / `ui-vant`）在自己的 spec 中传入本实现的可配置入口，
 * 跑同一套断言——「同接口多实现」的机器保障。运行时入口（`@bms/core`）不含本入口。
 */

export { describeConfirmContract, type ConfirmContractSubject } from './confirm'
export { describePermissionContract, type PermissionContractSubject } from './permission'
export {
  describeContainerComponentsContract,
  describePermButtonContract,
  type ComponentContractKit,
  type ComponentMountOptions,
  type ComponentViewHandle,
  type ScrollMetricsStub,
} from './components'
