/**
 * 编辑器内核能力基类：懒加载 / 创建销毁 / 内容协议（加载器由宿主注入，占位不请求）。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 编辑器内核能力基类（抽象）。 */
export class BaseEditorKernel extends BaseComponent {
    /** 能力键。 */
    identifier = 'editor-kernel';
    /** 内容。 */
    content = '';
    /** 模式。 */
    mode = 'rich';
    /** 是否已加载内核。 */
    loaded = false;
    /** 内核加载器（未注入则占位不加载）。 */
    loader;
    /** 懒加载内核（未注入加载器则占位不动作）。 */
    async load() {
        if (this.loader === undefined) {
            return;
        }
        await this.loader();
        this.loaded = true;
    }
    /** 销毁内核（复位内容与加载态）。 */
    destroy() {
        this.loaded = false;
        this.content = '';
    }
    /**
     * 设置内容。
     *
     * @param content 内容。
     */
    setContent(content) {
        this.content = content;
    }
    /** 读取内容。 */
    getContent() {
        return this.content;
    }
}
