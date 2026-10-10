/**
 * 字段语义能力基类：字段标识 / 校验触发 / 字段上下文（输入族公共能力）。
 */
import { BaseValue } from './value';
/** 字段能力基类（抽象）。 */
export class BaseField extends BaseValue {
    /** 能力键。 */
    identifier = 'field';
    /** 依赖能力键。 */
    depends = ['value'];
    /** 字段标识（提交键）。 */
    fieldName = '';
    /** 校验触发时机。 */
    trigger = 'change';
}
