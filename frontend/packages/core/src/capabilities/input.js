/**
 * 输入组件基类（输入族）：受控绑定 / 清空 / 只读判定 / composition / 焦点。
 */
import { BaseField } from './field';
/** 输入组件基类（抽象）。 */
export class BaseInput extends BaseField {
    /** 能力键（组件基类身份）。 */
    identifier = 'input';
    /** 占位提示。 */
    placeholder = '';
    /** 是否可清空。 */
    clearable = false;
    /** 是否输入法组合中。 */
    composing = false;
    /** 是否聚焦。 */
    focused = false;
    /** 是否只读（缺省值链只读态）。 */
    inputReadOnly = false;
    /** 清空值（仅当可清空）。 */
    clear() {
        if (this.clearable) {
            this.setValue(undefined);
        }
    }
    /**
     * 设置输入法组合态。
     *
     * @param composing 是否组合中。
     */
    setComposing(composing) {
        this.composing = composing;
    }
    /** 聚焦。 */
    focus() {
        if (!this.focused) {
            this.focused = true;
            this.notifyLifecycle('update');
        }
    }
    /** 失焦。 */
    blur() {
        if (this.focused) {
            this.focused = false;
            this.notifyLifecycle('update');
        }
    }
}
