// kiwi_id: 2236
// kiwi_id: 2259
/**
 * 模块请求能力基类与契约面用例（06_02；产品域通道 05-13）：
 * 服务键 + 路径寻址 / 产品键 + 域寻址 / 幂等键实现点 / 未注入占位 / 非法服务键与产品键。
 */
import { describe, expect, it } from 'vitest';
import { BaseModuleApi, ErrorCodes, configureRequestAdapter, productUrl, serviceUrl } from '../src';
/** 测试用请求能力实现（幂等键口径固定，便于断言实现点被调用）。 */
class ProbeModuleApi extends BaseModuleApi {
    /**
     * 幂等键（探针口径）。
     *
     * @param target 寻址主体（服务键或 `产品键:域`）。
     * @param path 资源子路径。
     */
    createIdempotencyKey(target, path) {
        return `probe:${target}:${path}`;
    }
}
/**
 * 记录调用的适配器（返回固定载荷）。
 *
 * @returns `{ configs, adapter }`。
 */
function recordingAdapter() {
    const configs = [];
    const adapter = {
        request(config) {
            configs.push(config);
            return Promise.resolve({ ok: true });
        },
    };
    return { configs, adapter };
}
describe('模块请求能力基类（06_02）', () => {
    it('未注入请求适配器时抛 NOT_IMPLEMENTED（占位零请求）', async () => {
        const api = new ProbeModuleApi();
        await expect(api.get('identity', '/auth/me')).rejects.toMatchObject({ code: ErrorCodes.NOT_IMPLEMENTED });
    });
    it('能力键与占位状态：identifier 为 module-api、就绪缺省为真', () => {
        const api = new ProbeModuleApi();
        expect(api.identifier).toBe('module-api');
        expect(api.ready).toBe(true);
    });
    it('get 按服务键 + 路径组装地址（前缀来自单一来源），无幂等键', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        const result = await new ProbeModuleApi().get('identity', '/auth/me', { withProfile: true });
        expect(result).toEqual({ ok: true });
        expect(configs).toEqual([
            {
                method: 'GET',
                url: serviceUrl('identity', '/auth/me'),
                params: { withProfile: true },
                data: undefined,
                headers: undefined,
                idempotencyKey: undefined,
            },
        ]);
    });
    it('post / put 自动带幂等键（口径由宿主实现点提供）', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        const api = new ProbeModuleApi();
        await api.post('file', '/files', { name: '张三' });
        await api.put('file', '/files/f1', { name: '李四' });
        expect(configs[0]).toMatchObject({
            method: 'POST',
            url: serviceUrl('file', '/files'),
            data: { name: '张三' },
            idempotencyKey: 'probe:file:/files',
        });
        expect(configs[1]).toMatchObject({ method: 'PUT', idempotencyKey: 'probe:file:/files/f1' });
    });
    it('del 带查询参数、无幂等键', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        await new ProbeModuleApi().del('file', '/files/f1', { force: true });
        expect(configs[0]).toMatchObject({ method: 'DELETE', url: serviceUrl('file', '/files/f1'), params: { force: true } });
        expect(configs[0]?.idempotencyKey).toBeUndefined();
    });
    it('request 逃生口：方法 / 头部 / 显式幂等键原样透传，缺省路径取服务前缀', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        await new ProbeModuleApi().request({
            method: 'PATCH',
            service: 'platform',
            headers: { 'X-Trace': 't1' },
            idempotencyKey: 'k1',
            data: { enabled: true },
        });
        expect(configs[0]).toEqual({
            method: 'PATCH',
            url: serviceUrl('platform'),
            params: undefined,
            data: { enabled: true },
            headers: { 'X-Trace': 't1' },
            idempotencyKey: 'k1',
        });
    });
    it('非法服务键抛 CAPABILITY_VIOLATION（不静默放行、不发请求）', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        await expect(new ProbeModuleApi().get('unknown')).rejects.toMatchObject({
            code: ErrorCodes.CAPABILITY_VIOLATION,
        });
        expect(configs).toEqual([]);
    });
});
describe('模块请求能力 · 产品域通道（05-13 · Kiwi 2259）', () => {
    it('产品域取数：地址经寻址契约组装（模块不自拼前缀），无幂等键', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        const result = await new ProbeModuleApi().product('mdm', 'org').get('/posts', { deptId: '1' });
        expect(result).toEqual({ ok: true });
        expect(configs).toEqual([
            {
                method: 'GET',
                url: productUrl('mdm', 'org', '/posts'),
                params: { deptId: '1' },
                data: undefined,
                headers: undefined,
                idempotencyKey: undefined,
            },
        ]);
    });
    it('产品域写方法自动带幂等键（口径含「产品键:域」，与平台通道不冲突）', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        const scope = new ProbeModuleApi().product('mdm', 'org');
        await scope.post('/user-posts', { userId: '1' });
        await scope.put('/posts/p1', { name: '组长' });
        await scope.patch('/posts/p1', { enabled: false });
        expect(configs[0]).toMatchObject({
            method: 'POST',
            url: productUrl('mdm', 'org', '/user-posts'),
            data: { userId: '1' },
            idempotencyKey: 'probe:mdm:org:/user-posts',
        });
        expect(configs[1]).toMatchObject({ method: 'PUT', idempotencyKey: 'probe:mdm:org:/posts/p1' });
        expect(configs[2]).toMatchObject({ method: 'PATCH', idempotencyKey: 'probe:mdm:org:/posts/p1' });
    });
    it('产品域 del / request 逃生口口径与服务通道一致', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        const scope = new ProbeModuleApi().product('mdm', 'org');
        await scope.del('/role-depts', { roleId: 'r1' });
        await scope.request({ method: 'POST', path: '/role-depts', headers: { 'X-Trace': 't1' }, idempotencyKey: 'k1' });
        expect(configs[0]).toMatchObject({
            method: 'DELETE',
            url: productUrl('mdm', 'org', '/role-depts'),
            params: { roleId: 'r1' },
        });
        expect(configs[0]?.idempotencyKey).toBeUndefined();
        expect(configs[1]).toMatchObject({
            method: 'POST',
            url: productUrl('mdm', 'org', '/role-depts'),
            headers: { 'X-Trace': 't1' },
            idempotencyKey: 'k1',
        });
    });
    it('缺省路径取产品域前缀本身', async () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        await new ProbeModuleApi().product('mdm', 'org').get();
        expect(configs[0]?.url).toBe('/api/mdm/v1/org');
    });
    it('未登记产品键 / 非法域段：立即抛 CAPABILITY_VIOLATION 且零请求', () => {
        const { configs, adapter } = recordingAdapter();
        configureRequestAdapter(adapter);
        const api = new ProbeModuleApi();
        const calls = [() => api.product('biz', 'org'), () => api.product('mdm', 'ORG'), () => api.product('mdm', '')];
        for (const call of calls) {
            expect(call).toThrowError();
            try {
                call();
            }
            catch (error) {
                expect(error.code).toBe(ErrorCodes.CAPABILITY_VIOLATION);
            }
        }
        expect(configs).toEqual([]);
    });
});
