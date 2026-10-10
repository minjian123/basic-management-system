/** 路由守卫判定用例（04-1-1 / Kiwi 2191）：公开白名单 / 令牌 / 登录路径；05_03 / Kiwi 2231：决策矩阵 / 跳登录构造 / 站内回跳校验。 */
// kiwi_id: 2191, 2231
import { describe, expect, it } from 'vitest';
import { DEFAULT_FORBIDDEN_PATH, DEFAULT_HOME_PATH, DEFAULT_LOGIN_PATH, DEFAULT_PUBLIC_PATHS, buildLoginLocation, isPublicPath, resolveAuthGuard, resolveAuthRedirect, resolveSafeRedirect, } from '../src';
describe('resolveAuthRedirect（Kiwi 2191）', () => {
    it('已持令牌一律放行', () => {
        expect(resolveAuthRedirect({ hasToken: true, path: '/org/users' })).toBeNull();
    });
    it('无令牌且非公开路径 → 跳登录', () => {
        expect(resolveAuthRedirect({ hasToken: false, path: '/org/users' })).toBe(DEFAULT_LOGIN_PATH);
    });
    it('公开白名单精确与子路径均放行', () => {
        for (const path of DEFAULT_PUBLIC_PATHS) {
            expect(resolveAuthRedirect({ hasToken: false, path })).toBeNull();
        }
        expect(resolveAuthRedirect({ hasToken: false, path: '/login/callback' })).toBeNull();
    });
    it('白名单前缀不误伤同段前缀路径', () => {
        expect(resolveAuthRedirect({ hasToken: false, path: '/loginfo' })).toBe(DEFAULT_LOGIN_PATH);
    });
    it('支持自定义白名单与登录路径', () => {
        expect(resolveAuthRedirect({ hasToken: false, path: '/public', publicPaths: ['/public'] })).toBeNull();
        expect(resolveAuthRedirect({ hasToken: false, path: '/x', loginPath: '/signin' })).toBe('/signin');
    });
});
describe('resolveAuthGuard（Kiwi 2231）', () => {
    it('未登录：公开页放行、受保护路径跳登录', () => {
        expect(resolveAuthGuard({ hasToken: false, path: '/login' })).toBe('allow');
        expect(resolveAuthGuard({ hasToken: false, path: '/org/users' })).toBe('login');
    });
    it('路由声明为公开页（meta.public）时未登录也放行', () => {
        expect(resolveAuthGuard({ hasToken: false, path: '/sso/callback', isPublicRoute: true })).toBe('allow');
    });
    it('已登录未声明权限码 → 放行（零判定开销）', () => {
        expect(resolveAuthGuard({ hasToken: true, path: '/org/users' })).toBe('allow');
    });
    it('已登录：权限未装载 → 占位放行（RBAC 就绪前的口径）', () => {
        const input = { hasToken: true, path: '/org/users', requiredPermissions: ['user:query'] };
        expect(resolveAuthGuard({ ...input, permissions: [], permissionsLoaded: false })).toBe('allow');
        expect(resolveAuthGuard({ ...input, permissionsLoaded: undefined })).toBe('allow');
    });
    it('已登录：权限已装载按「任一满足」判定，不满足 → forbidden', () => {
        const input = { hasToken: true, path: '/org/users', requiredPermissions: ['user:query'], permissionsLoaded: true };
        expect(resolveAuthGuard({ ...input, permissions: ['user:query'] })).toBe('allow');
        expect(resolveAuthGuard({ ...input, permissions: ['user:query', 'user:edit'] })).toBe('allow');
        expect(resolveAuthGuard({ ...input, permissions: ['user:edit'] })).toBe('forbidden');
        expect(resolveAuthGuard({ ...input, permissions: [] })).toBe('forbidden');
    });
    it('已登录：空权限码数组视为未声明 → 放行', () => {
        expect(resolveAuthGuard({ hasToken: true, path: '/org/users', requiredPermissions: [], permissionsLoaded: true })).toBe('allow');
    });
    it('未登录且已声明权限码 → 仍先跳登录', () => {
        expect(resolveAuthGuard({
            hasToken: false,
            path: '/org/users',
            requiredPermissions: ['user:query'],
            permissionsLoaded: true,
        })).toBe('login');
    });
    it('无权限路径常量为 /403', () => {
        expect(DEFAULT_FORBIDDEN_PATH).toBe('/403');
    });
    it('公开白名单可自定义', () => {
        expect(resolveAuthGuard({ hasToken: false, path: '/public', publicPaths: ['/public'] })).toBe('allow');
    });
});
describe('isPublicPath（Kiwi 2231）', () => {
    it('常量逐项精确命中', () => {
        for (const path of DEFAULT_PUBLIC_PATHS) {
            expect(isPublicPath(path)).toBe(true);
        }
    });
    it('子路径命中、同段前缀不误伤', () => {
        expect(isPublicPath('/login/callback')).toBe(true);
        expect(isPublicPath('/403/detail')).toBe(true);
        expect(isPublicPath('/loginfo')).toBe(false);
        expect(isPublicPath('/')).toBe(false);
    });
});
describe('buildLoginLocation（Kiwi 2231）', () => {
    it('受保护路径回带 redirect（原 fullPath 原样，含查询串与片段）', () => {
        expect(buildLoginLocation('/org/users?page=2#row-3')).toEqual({
            path: DEFAULT_LOGIN_PATH,
            query: { redirect: '/org/users?page=2#row-3' },
        });
    });
    it('公开路径与登录页自身不回带 redirect', () => {
        expect(buildLoginLocation('/500')).toEqual({ path: DEFAULT_LOGIN_PATH });
        expect(buildLoginLocation('/login')).toEqual({ path: DEFAULT_LOGIN_PATH });
        expect(buildLoginLocation('')).toEqual({ path: DEFAULT_LOGIN_PATH });
    });
    it('支持自定义登录路径与白名单', () => {
        expect(buildLoginLocation('/x', { loginPath: '/signin', publicPaths: ['/public'] })).toEqual({
            path: '/signin',
            query: { redirect: '/x' },
        });
        expect(buildLoginLocation('/public', { loginPath: '/signin', publicPaths: ['/public'] })).toEqual({
            path: '/signin',
        });
    });
});
describe('resolveSafeRedirect（Kiwi 2231）', () => {
    it('合法站内相对路径原样返回（含查询串与片段）', () => {
        expect(resolveSafeRedirect('/org/users')).toBe('/org/users');
        expect(resolveSafeRedirect('/org/users?page=2#row-3')).toBe('/org/users?page=2#row-3');
    });
    it('外链 / 协议相对 / 危险协议一律回落', () => {
        expect(resolveSafeRedirect('https://evil.example.com/x')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('http://evil.example.com')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('//evil.example.com')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('javascript:alert(1)')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('org/users')).toBe(DEFAULT_HOME_PATH);
    });
    it('反斜杠 / 控制字符 / 空值与非法类型回落', () => {
        expect(resolveSafeRedirect('\\\\evil\\x')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('/org\u0000users')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('   ')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect(null)).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect(undefined)).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect({ path: '/org/users' })).toBe(DEFAULT_HOME_PATH);
    });
    it('命中公开白名单回落（防回跳循环；按路径判定、忽略查询串）', () => {
        expect(resolveSafeRedirect('/login')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('/login?redirect=/x')).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('/500#err')).toBe(DEFAULT_HOME_PATH);
    });
    it('支持自定义 fallback 与白名单', () => {
        expect(resolveSafeRedirect('https://evil.example.com', { fallback: '/home' })).toBe('/home');
        expect(resolveSafeRedirect('/public/x', { publicPaths: ['/public'] })).toBe(DEFAULT_HOME_PATH);
        expect(resolveSafeRedirect('/public/x', { publicPaths: [] })).toBe('/public/x');
    });
});
