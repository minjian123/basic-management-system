/** 框架对象层基类 `BaseFrameworkObject` 用例（09_02，Kiwi 2215）。 */
import { describe, expect, it } from 'vitest';
import { BaseAsyncResource, BaseCapability, BaseComponent, BaseFactory, BaseFrameworkObject, BaseNullObject, BaseObject, BasePlaceholder, BasePluggable, BaseProvider, BaseProviderRegistry, BaseStub, BaseSubscription, } from '../src';
describe('BaseFrameworkObject 框架对象层（09_02，Kiwi 2215）', () => {
    it('继承链 BaseFrameworkObject → BaseObject（框架对象层直承总基类）', () => {
        expect(Object.getPrototypeOf(BaseFrameworkObject)).toBe(BaseObject);
        expect(BaseFrameworkObject.prototype).toBeInstanceOf(BaseObject);
    });
    it('objectKind 缺省 framework，且子类可覆写', () => {
        expect(new BaseFrameworkObject().objectKind).toBe('framework');
        class CustomFrameworkObject extends BaseFrameworkObject {
            objectKind = 'registry';
        }
        expect(new CustomFrameworkObject().objectKind).toBe('registry');
    });
    it('四段：能力域 / 插件 / 组件根 / 注册项 / 注册表 / 工厂均经框架对象层', () => {
        const bases = [BaseCapability, BasePluggable, BaseComponent, BaseProvider, BaseProviderRegistry, BaseFactory];
        for (const base of bases) {
            expect(base.prototype).toBeInstanceOf(BaseFrameworkObject);
            expect(base.prototype).toBeInstanceOf(BaseObject);
        }
    });
    it('框架类底座改挂：异步资源 / 占位三件 / 订阅', () => {
        const bases = [BaseAsyncResource, BasePlaceholder, BaseNullObject, BaseStub, BaseSubscription];
        for (const base of bases) {
            expect(base.prototype).toBeInstanceOf(BaseFrameworkObject);
            expect(base.prototype).toBeInstanceOf(BaseObject);
        }
    });
    it('能力语义不变（改挂不改行为）', () => {
        class DemoCapability extends BaseCapability {
            key = 'demo';
        }
        const demo = new DemoCapability();
        expect(demo).toBeInstanceOf(BaseFrameworkObject);
        expect(demo.key).toBe('demo');
        expect(demo.objectKind).toBe('framework');
    });
});
