/**
 * 选项源能力基类：加载 / 缓存与版本比对 / 搜索 / 回显（加载器由宿主注入，占位不请求）。
 *
 * 父基类 `BaseField`（经值链 `BaseValue → BaseField` 取得受控值与字段语义），
 * 供字典 / 组织 / 枚举 / 树 / 级联等字段族派生；`BaseOrgSelect` 即其下位组件基类。
 */
import { BaseField } from './field';
/** 选项源能力基类（抽象）。 */
export class BaseOptionSource extends BaseField {
    /** 能力键。 */
    identifier = 'option-source';
    /** 依赖登记。 */
    depends = ['field'];
    /** 已加载选项。 */
    options = [];
    /** 数据版本（加载后递增，用于版本比对；命名避开根字段 `version`）。 */
    dataVersion = 0;
    /** 选项加载器（未注入则占位不请求）。 */
    loader;
    /** 加载选项（未注入加载器则占位不动作）。 */
    async load() {
        if (this.loader === undefined) {
            return;
        }
        this.options = await this.loader();
        this.dataVersion += 1;
    }
    /**
     * 按值回显文案。
     *
     * @param value 值。
     */
    getLabel(value) {
        return this.options.find((item) => Object.is(item.value, value))?.label;
    }
    /**
     * 按关键字搜索（空串返回全部）。
     *
     * @param keyword 关键字。
     */
    search(keyword) {
        const text = keyword.trim();
        if (text === '') {
            return [...this.options];
        }
        return this.options.filter((item) => item.label.includes(text));
    }
}
