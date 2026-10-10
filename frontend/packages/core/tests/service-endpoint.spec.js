/**
 * 服务寻址契约用例（04-1-1 / Kiwi 2191；产品命名空间寻址 05-13 / Kiwi 2259）：
 * 服务键与产品键 / 前缀 / URL 组装与边界。
 */
// kiwi_id: 2191
// kiwi_id: 2259
import { describe, expect, it } from 'vitest';
import { BaseError, PRODUCT_KEYS, SERVICE_KEYS, isProductKey, isServiceKey, productDomain, productPrefix, productUrl, servicePrefix, serviceUrl, } from '../src';
describe('服务键与「域 → 服务前缀」映射（Kiwi 2191）', () => {
    it('服务键为 8 个已启用平台服务且顺序与目录一致', () => {
        expect(SERVICE_KEYS).toEqual([
            'platform',
            'identity',
            'tenant',
            'file',
            'notification',
            'search',
            'ai',
            'report',
        ]);
    });
    it('isServiceKey 正反例', () => {
        expect(isServiceKey('platform')).toBe(true);
        expect(isServiceKey('workflow')).toBe(false);
        expect(isServiceKey(1)).toBe(false);
        expect(isServiceKey(undefined)).toBe(false);
    });
    it('servicePrefix 逐服务给出外部前缀', () => {
        for (const service of SERVICE_KEYS) {
            expect(servicePrefix(service)).toBe(`/api/${service}/v1`);
        }
    });
    it('未登记服务键抛参数段位错误', () => {
        try {
            servicePrefix('workflow');
            throw new Error('should throw');
        }
        catch (error) {
            expect(error).toBeInstanceOf(BaseError);
            expect(error.code).toBe(10001);
        }
    });
});
describe('serviceUrl 组装与路径归一（Kiwi 2191）', () => {
    it('空路径返回前缀本身', () => {
        expect(serviceUrl('platform')).toBe('/api/platform/v1');
        expect(serviceUrl('platform', '')).toBe('/api/platform/v1');
    });
    it('带 / 与不带 / 的首部斜杠等价', () => {
        expect(serviceUrl('file', '/files')).toBe('/api/file/v1/files');
        expect(serviceUrl('file', 'files')).toBe('/api/file/v1/files');
    });
    it('折叠重复斜杠', () => {
        expect(serviceUrl('file', '//files//uploads')).toBe('/api/file/v1/files/uploads');
    });
    it('保留查询串与深层路径', () => {
        expect(serviceUrl('search', '/search/global?q=a&page=1')).toBe('/api/search/v1/search/global?q=a&page=1');
    });
});
describe('产品命名空间寻址（05-13 · Kiwi 2259）', () => {
    it('产品键清单与判定（未登记产品不静默放行）', () => {
        expect(PRODUCT_KEYS).toEqual(['mdm']);
        expect(isProductKey('mdm')).toBe(true);
        expect(isProductKey('biz')).toBe(false);
        expect(isProductKey(1)).toBe(false);
        expect(isProductKey(undefined)).toBe(false);
    });
    it('productPrefix / productUrl 按「产品键 + 域 + 路径」组装', () => {
        expect(productPrefix('mdm', 'org')).toBe('/api/mdm/v1/org');
        expect(productUrl('mdm', 'org')).toBe('/api/mdm/v1/org');
        expect(productUrl('mdm', 'org', '/posts')).toBe('/api/mdm/v1/org/posts');
        expect(productUrl('mdm', 'org', 'posts')).toBe('/api/mdm/v1/org/posts');
    });
    it('域段归一（首尾斜杠 / 空白）与路径归一与服务通道同口径', () => {
        expect(productDomain('/org/')).toBe('org');
        expect(productUrl('mdm', ' /org/ ', '//data-source//dept-tree')).toBe('/api/mdm/v1/org/data-source/dept-tree');
    });
    it('保留查询串与深层路径', () => {
        expect(productUrl('mdm', 'org', 'posts?deptId=1&page=2')).toBe('/api/mdm/v1/org/posts?deptId=1&page=2');
    });
    it('未登记产品键 / 非法或缺失域段抛参数段位错误', () => {
        const calls = [
            () => productPrefix('biz', 'org'),
            () => productPrefix('mdm', ''),
            () => productPrefix('mdm', 'ORG'),
            () => productPrefix('mdm', '1org'),
            () => productUrl('mdm', 'org/x'),
        ];
        for (const call of calls) {
            try {
                call();
                throw new Error('should throw');
            }
            catch (error) {
                expect(error).toBeInstanceOf(BaseError);
                expect(error.code).toBe(10001);
            }
        }
    });
    it('平台服务寻址零变化（清单不含产品域，产品键不进入服务清单）', () => {
        expect(SERVICE_KEYS).toEqual([
            'platform',
            'identity',
            'tenant',
            'file',
            'notification',
            'search',
            'ai',
            'report',
        ]);
        expect(SERVICE_KEYS.includes('org')).toBe(false);
        expect(serviceUrl('platform', '/tenants')).toBe('/api/platform/v1/tenants');
    });
});
