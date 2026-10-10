/**
 * 组件根：所有 UI 组件的公共协议（组件侧入口）。
 *
 * 提供标识与命名空间类名、尺寸 / 密度、`loading` / `disabled` / 显隐、**令牌属性协议**、
 * attrs 透传（保留键过滤）、运行期字段设置、生命周期通知与机制装配点。
 * **纯数据输出**：不触 DOM、不依赖渲染框架；组件只消费令牌语义变量。
 */
import { BasePluggable } from '../mechanisms/pluggable';
/** 组件自有（不透传）的保留键。 */
const RESERVED_KEYS = new Set(['size', 'density', 'loading', 'disabled', 'visible']);
/** 组件根（抽象）。 */
export class BaseComponent extends BasePluggable {
    /** 缺省实现名（具体组件可覆写）。 */
    pluginName = 'core';
    /** 尺寸档位。 */
    size = 'default';
    /** 密度档位。 */
    density = 'default';
    /** 加载态。 */
    loading = false;
    /** 禁用态。 */
    disabled = false;
    /** 显隐。 */
    visible = true;
    /** 机制装配点（名称 → 机制实例）。 */
    mechanisms = new Map();
    /** 已注册的生命周期监听器。 */
    listeners = [];
    constructor(namespace = 'bms', version = '0.0.0') {
        super(namespace, version);
    }
    /** 插件键 = 组件标识。 */
    get pluginKey() {
        return this.identifier;
    }
    /** 命名空间类名（`${namespace}-${identifier}`）。 */
    get nsClass() {
        return `${this.namespace}-${this.identifier}`;
    }
    /** 令牌属性协议：档位 / 状态 / 可访问性属性。 */
    rootAttrs() {
        const attrs = {
            'data-size': this.size,
            'data-density': this.density,
        };
        if (this.loading) {
            attrs['aria-busy'] = 'true';
        }
        if (this.disabled) {
            attrs['aria-disabled'] = 'true';
        }
        if (!this.visible) {
            attrs['aria-hidden'] = 'true';
        }
        return attrs;
    }
    /** 状态类（状态只加状态类）。 */
    stateClasses() {
        const classes = [];
        if (this.loading) {
            classes.push('is-loading');
        }
        if (this.disabled) {
            classes.push('is-disabled');
        }
        if (!this.visible) {
            classes.push('is-hidden');
        }
        return classes;
    }
    /**
     * attrs 透传（过滤组件自有保留键与下划线前缀私有键）。
     *
     * @param attrs 待透传属性。
     */
    passthroughAttrs(attrs) {
        return Object.fromEntries(Object.entries(attrs).filter(([key]) => !RESERVED_KEYS.has(key) && !key.startsWith('_')));
    }
    /**
     * 运行期设置组件字段（已提供的键合并；随后广播 `update`）。
     *
     * @param props 待设置字段。
     */
    setProps(props) {
        if (props.size !== undefined) {
            this.size = props.size;
        }
        if (props.density !== undefined) {
            this.density = props.density;
        }
        if (props.loading !== undefined) {
            this.loading = props.loading;
        }
        if (props.disabled !== undefined) {
            this.disabled = props.disabled;
        }
        if (props.visible !== undefined) {
            this.visible = props.visible;
        }
        if (!this.isDisposed) {
            this.notifyLifecycle('update');
        }
    }
    /**
     * 注册生命周期监听器。
     *
     * @param listener 监听器。
     * @returns 取消函数（幂等）。
     */
    onLifecycle(listener) {
        this.listeners.push(listener);
        return () => {
            const index = this.listeners.indexOf(listener);
            if (index >= 0) {
                this.listeners.splice(index, 1);
            }
        };
    }
    /**
     * 广播生命周期事件（监听器异常上报后继续）。
     *
     * @param event 事件。
     * @param detail 附加信息。
     */
    notifyLifecycle(event, detail) {
        const payload = {
            ...detail,
            identifier: this.identifier,
            nsClass: this.nsClass,
            size: this.size,
            density: this.density,
            loading: this.loading,
            disabled: this.disabled,
            visible: this.visible,
        };
        for (const listener of [...this.listeners]) {
            try {
                listener(event, payload);
            }
            catch (error) {
                this.reportError(error, { scope: 'BaseComponent.notifyLifecycle', event });
            }
        }
    }
    /**
     * 挂接机制到装配点。
     *
     * @param name 机制名。
     * @param mechanism 机制实例。
     */
    mountMechanism(name, mechanism) {
        this.mechanisms.set(name, mechanism);
    }
    /** 释放：广播 `unmount` 并清空监听与装配点。 */
    onDispose() {
        this.notifyLifecycle('unmount');
        this.listeners.length = 0;
        this.mechanisms.clear();
    }
}
