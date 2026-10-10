// kiwi_id: 2233
/** 扫码登录状态源插件族与注册表用例（05_04）：插件契约 / 登记解析 / 拒重。 */
import { describe, expect, it } from 'vitest';
import { BaseError, BaseSsoQrSource, SsoQrSourceProvider, SsoQrSourceRegistry } from '../src';
/** 演示状态源（覆盖两方法）。 */
class DemoSource extends BaseSsoQrSource {
    /** 实现名。 */
    pluginName = 'demo';
    /** 取授权 URL。 */
    async init(query) {
        void query;
        return { authorize_url: 'https://idp', state: 's1', expires_in: 30 };
    }
    /** 轮询。 */
    async poll(query) {
        void query;
        return { status: 'pending' };
    }
}
describe('BaseSsoQrSource 插件契约', () => {
    it('插件键与实现名，未覆写方法返回 undefined（不请求）', async () => {
        const source = new DemoSource();
        expect(source.pluginKey).toBe('sso-qr-source');
        expect(source.pluginName).toBe('demo');
        expect(await source.init({ idpKey: 'k' })).toEqual({ authorize_url: 'https://idp', state: 's1', expires_in: 30 });
        expect(await source.poll({ idpKey: 'k', state: 's1', attempt: 1 })).toEqual({ status: 'pending' });
    });
    it('基类缺省方法返回 undefined', async () => {
        class BareSource extends BaseSsoQrSource {
            pluginName = 'bare';
        }
        const source = new BareSource();
        expect(await source.init({ idpKey: 'k' })).toBeUndefined();
        expect(await source.poll({ idpKey: 'k', state: 's', attempt: 1 })).toBeUndefined();
    });
});
describe('SsoQrSourceRegistry 注册表', () => {
    it('登记 / 解析 / 注销与快照', () => {
        const registry = new SsoQrSourceRegistry();
        expect(registry.pluginKey).toBe('sso-qr-source-registry');
        registry.register(new SsoQrSourceProvider('http', () => new DemoSource()));
        expect(registry.keys()).toEqual(['http']);
        expect(registry.get('http')).toBeInstanceOf(SsoQrSourceProvider);
        expect(registry.get('missing')).toBeUndefined();
        expect(registry.snapshot().size).toBe(1);
        expect(registry.unregister('http')).toBe(true);
        expect(registry.values()).toEqual([]);
    });
    it('同键重复登记抛 BaseError', () => {
        const registry = new SsoQrSourceRegistry();
        registry.register(new SsoQrSourceProvider('http', () => new DemoSource()));
        expect(() => registry.register(new SsoQrSourceProvider('http', () => new DemoSource()))).toThrow(BaseError);
    });
});
