/** 注册表基座用例（02-5）。 */
import { describe, expect, it } from 'vitest';
import { BaseError, BaseProviderRegistry } from '../src';
class DemoRegistry extends BaseProviderRegistry {
    pluginKey = 'demo-registry';
    pluginName = 'core';
    providerKey(provider) {
        return provider;
    }
}
describe('BaseProviderRegistry 注册表基座', () => {
    it('登记 / 未命中 undefined / 保序 / 只读快照', () => {
        const registry = new DemoRegistry();
        registry.register('b');
        registry.register('a');
        expect(registry.get('a')).toBe('a');
        expect(registry.get('missing')).toBeUndefined();
        expect(registry.keys()).toEqual(['b', 'a']);
        expect(registry.values()).toEqual(['b', 'a']);
        expect([...registry.snapshot().keys()]).toEqual(['b', 'a']);
    });
    it('同键拒重抛 BaseError(REGISTRY_CONFLICT)', () => {
        const registry = new DemoRegistry();
        registry.register('a');
        try {
            registry.register('a');
            throw new Error('should throw');
        }
        catch (error) {
            expect(error).toBeInstanceOf(BaseError);
            expect(error.code).toBe(10003);
        }
    });
});
