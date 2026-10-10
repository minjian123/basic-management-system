/**
 * 能力域基类：能力键声明与依赖登记机制（固定四段第 3 层，对齐后端同名基类）。
 *
 * 只承载「能力如何声明」——键（kebab-case）、依赖清单与元信息；不含 UI 与业务语义。
 * 依赖的单向校验与登记表（`capabilities/manifest.ts`）由 02_03 承接。
 */
import { BaseFrameworkObject } from '../base/framework-object';
/** 能力域基类（抽象）。 */
export class BaseCapability extends BaseFrameworkObject {
    /** 依赖的能力键（登记 / 单向校验由 02_03 承接）。 */
    depends = [];
    /** 元信息描述。 */
    describe() {
        return `${this.key}（能力域基类）`;
    }
}
