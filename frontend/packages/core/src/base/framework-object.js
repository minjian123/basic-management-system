/**
 * 框架对象体系基类（对齐后端 `BaseFrameworkObject`；《前端基类清单》§3.2）。
 *
 * **框架对象**＝非渲染、非数据对象（能力域 / 插件 / 注册表 / 工厂 / 资源 / 占位等）；本层承载
 * 其公共语义——统一标识 `objectKind`。生命周期沿用总基类 `dispose()` / `onDispose()`，不在本层
 * 重复定义（后端同名基类另提供可选异步钩子位 `aclose`，前端无异步资源释放口径）。
 *
 * 四段继承链：`BaseObject` → `BaseFrameworkObject` → `BaseCapability` → `BasePluggable`。
 */
import { BaseObject } from './BaseObject';
/** 框架对象体系基类。 */
export class BaseFrameworkObject extends BaseObject {
    /** 框架对象统一标识（子层覆写，如 `capability` / `component` / `registry` / `resource`）。 */
    objectKind = 'framework';
}
