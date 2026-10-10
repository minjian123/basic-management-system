/**
 * 校验能力基类：规则汇总 / 触发时机 / 结果回传 / 错误定位。
 */
import { BaseLabeled } from './labeled';
/** 校验能力基类（抽象）。 */
export class BaseValidatable extends BaseLabeled {
    /** 能力键。 */
    identifier = 'validatable';
    /** 依赖能力键。 */
    depends = ['labeled'];
    /** 校验规则（按序执行，遇错即止）。 */
    rules = [];
    /** 当前错误。 */
    #errors = [];
    /** 当前错误清单（只读）。 */
    get errors() {
        return this.#errors;
    }
    /** 是否校验通过。 */
    get valid() {
        return this.#errors.length === 0;
    }
    /**
     * 执行校验并回填错误位（`errorText`）。
     *
     * @param value 待校验值。
     * @returns 是否通过。
     */
    validate(value) {
        const errors = [];
        for (const rule of this.rules) {
            const message = rule(value);
            if (message !== undefined) {
                errors.push(message);
                break;
            }
        }
        this.#errors = errors;
        this.errorText = errors[0];
        return errors.length === 0;
    }
    /** 清空错误。 */
    clearErrors() {
        this.#errors = [];
        this.errorText = undefined;
    }
}
