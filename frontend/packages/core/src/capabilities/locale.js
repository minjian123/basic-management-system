/**
 * 语言上下文能力基类：locale / 时区 / 格式上下文（切换与缓存）。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 语言上下文能力基类（抽象）。 */
export class BaseLocale extends BaseComponent {
    /** 能力键。 */
    identifier = 'locale';
    /** 当前语言。 */
    locale = 'zh-CN';
    /** 当前时区。 */
    timezone = 'Asia/Shanghai';
    /** 格式上下文快照。 */
    get formatContext() {
        return { locale: this.locale, timezone: this.timezone };
    }
    /**
     * 切换语言。
     *
     * @param locale 语言标识。
     */
    setLocale(locale) {
        if (locale === this.locale) {
            return;
        }
        this.locale = locale;
        this.notifyLifecycle('update');
    }
    /**
     * 切换时区。
     *
     * @param timezone 时区标识。
     */
    setTimezone(timezone) {
        if (timezone === this.timezone) {
            return;
        }
        this.timezone = timezone;
        this.notifyLifecycle('update');
    }
}
