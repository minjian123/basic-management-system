/**
 * 标签语义能力基类：label 文案 / 位置 / 宽度、必填标记、帮助与错误位。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 标签能力基类（抽象）。 */
export class BaseLabeled extends BaseComponent {
    /** 能力键。 */
    identifier = 'labeled';
    /** 标签文案。 */
    label = '';
    /** 标签位置。 */
    labelPosition = 'top';
    /** 标签宽度（数字按像素）。 */
    labelWidth;
    /** 是否必填。 */
    required = false;
    /** 帮助提示。 */
    helpText;
    /** 错误提示（由校验回填）。 */
    errorText;
}
