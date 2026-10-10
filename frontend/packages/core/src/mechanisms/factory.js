/**
 * 工厂基类（对齐后端工厂口径）：一切工厂类之根。
 *
 * 层级：`BaseFactory` → 各域工厂基类 → 具体工厂类；只负责创建与装配，不承载业务判定。
 */
import { BasePluggable } from './pluggable';
/** 工厂基类（抽象）。 */
export class BaseFactory extends BasePluggable {
    /** 参数校验（缺省空实现；子类按需覆写）。 */
    validate(options) {
        void options;
    }
}
