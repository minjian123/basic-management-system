// kiwi_id: 2233
/** 扫码登录领域纯函数用例（05_04）：可扫码源过滤 / 退避 / 终态 / 文案 / 契约归一。 */
import { describe, expect, it } from 'vitest';
import { isScannableIdpType, isSsoQrTerminal, nextSsoQrPollDelay, normalizeSsoQrAuthorizeInfo, normalizeSsoQrPollResult, resolveSsoQrStatusText, selectScannableProviders, SSO_QR_CONFIRMED_TEXT, SSO_QR_EMPTY_TEXT, SSO_QR_EXPIRED_TEXT, SSO_QR_FAILED_TEXT, SSO_QR_PENDING_TEXT, SSO_QR_POLL_BASE, SSO_QR_POLL_MAX, SSO_QR_SCANNED_TEXT, } from '../src';
describe('扫码登录领域 · 可扫码身份源', () => {
    it('isScannableIdpType 仅 wecom / dingtalk 为真', () => {
        expect(isScannableIdpType('wecom')).toBe(true);
        expect(isScannableIdpType('dingtalk')).toBe(true);
        expect(isScannableIdpType('oidc')).toBe(false);
        expect(isScannableIdpType('cas')).toBe(false);
        expect(isScannableIdpType('')).toBe(false);
    });
    it('selectScannableProviders 过滤并按 sort 升序（不修改入参）', () => {
        const input = [
            { idp_key: 'w2', type: 'wecom', sort: 20 },
            { idp_key: 'o1', type: 'oidc', sort: 1 },
            { idp_key: 'd1', type: 'dingtalk', sort: 10 },
        ];
        const result = selectScannableProviders(input);
        expect(result.map((item) => item.idp_key)).toEqual(['d1', 'w2']);
        expect(input.map((item) => item.idp_key)).toEqual(['w2', 'o1', 'd1']);
    });
    it('selectScannableProviders 无 sort 时保持原序', () => {
        const result = selectScannableProviders([
            { idp_key: 'a', type: 'wecom' },
            { idp_key: 'b', type: 'dingtalk' },
        ]);
        expect(result.map((item) => item.idp_key)).toEqual(['a', 'b']);
    });
});
describe('扫码登录领域 · 退避与终态', () => {
    it('nextSsoQrPollDelay 指数退避并封顶', () => {
        expect(nextSsoQrPollDelay(1)).toBe(SSO_QR_POLL_BASE);
        expect(nextSsoQrPollDelay(2)).toBe(4000);
        expect(nextSsoQrPollDelay(3)).toBe(8000);
        expect(nextSsoQrPollDelay(4)).toBe(16000);
        expect(nextSsoQrPollDelay(5)).toBe(SSO_QR_POLL_MAX);
        expect(nextSsoQrPollDelay(9)).toBe(SSO_QR_POLL_MAX);
    });
    it('nextSsoQrPollDelay 支持自定义基数与上限', () => {
        expect(nextSsoQrPollDelay(1, { base: 100, max: 250 })).toBe(100);
        expect(nextSsoQrPollDelay(2, { base: 100, max: 250 })).toBe(200);
        expect(nextSsoQrPollDelay(3, { base: 100, max: 250 })).toBe(250);
    });
    it('isSsoQrTerminal 判终态', () => {
        expect(isSsoQrTerminal('pending')).toBe(false);
        expect(isSsoQrTerminal('scanned')).toBe(false);
        expect(isSsoQrTerminal('confirmed')).toBe(true);
        expect(isSsoQrTerminal('expired')).toBe(true);
        expect(isSsoQrTerminal('failed')).toBe(true);
    });
    it('resolveSsoQrStatusText 逐相位文案', () => {
        expect(resolveSsoQrStatusText('pending')).toBe(SSO_QR_PENDING_TEXT);
        expect(resolveSsoQrStatusText('scanned')).toBe(SSO_QR_SCANNED_TEXT);
        expect(resolveSsoQrStatusText('confirmed')).toBe(SSO_QR_CONFIRMED_TEXT);
        expect(resolveSsoQrStatusText('expired')).toBe(SSO_QR_EXPIRED_TEXT);
        expect(resolveSsoQrStatusText('failed')).toBe(SSO_QR_FAILED_TEXT);
        expect(SSO_QR_EMPTY_TEXT).not.toBe('');
    });
});
describe('扫码登录领域 · 契约归一', () => {
    it('normalizeSsoQrAuthorizeInfo 归一后端字段', () => {
        expect(normalizeSsoQrAuthorizeInfo({ authorize_url: 'https://x', state: 's', expires_in: 60 })).toEqual({
            authorizeUrl: 'https://x',
            state: 's',
            expiresIn: 60,
        });
    });
    it('normalizeSsoQrAuthorizeInfo 非法入参回落缺省且不抛错', () => {
        expect(normalizeSsoQrAuthorizeInfo(undefined)).toEqual({ authorizeUrl: '', state: '', expiresIn: 0 });
        expect(normalizeSsoQrAuthorizeInfo({ expires_in: -3 })).toEqual({ authorizeUrl: '', state: '', expiresIn: 0 });
        expect(normalizeSsoQrAuthorizeInfo({ authorize_url: 1, state: null })).toEqual({
            authorizeUrl: '',
            state: '',
            expiresIn: 0,
        });
    });
    it('normalizeSsoQrPollResult 未知状态回落 pending、非法 redirect 丢弃', () => {
        expect(normalizeSsoQrPollResult({ status: 'confirmed', redirect: '/done' })).toEqual({
            status: 'confirmed',
            redirect: '/done',
        });
        expect(normalizeSsoQrPollResult({ status: 'something' })).toEqual({ status: 'pending' });
        expect(normalizeSsoQrPollResult({ status: 'confirmed', redirect: '' })).toEqual({ status: 'confirmed' });
        expect(normalizeSsoQrPollResult({ status: 'confirmed', redirect: 1 })).toEqual({ status: 'confirmed' });
        expect(normalizeSsoQrPollResult(null)).toEqual({ status: 'pending' });
    });
});
