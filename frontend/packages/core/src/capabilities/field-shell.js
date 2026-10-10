/**
 * 字段壳组件基类（字段壳族）：label / 必填 / 帮助 / 错误 / 栅格跨度 / 只读回显。
 */
import { BaseLabeled } from './labeled';
/** 字段壳组件基类（抽象）。 */
export class BaseFieldShell extends BaseLabeled {
    /** 能力键（组件基类身份）。 */
    identifier = 'field-shell';
    /** 栅格跨度（列数）。 */
    span = 24;
    /** 是否只读回显。 */
    displayOnly = false;
    /** 是否处于错误态。 */
    get hasError() {
        return this.errorText !== undefined && this.errorText !== '';
    }
}
