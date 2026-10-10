/**
 * 状态语义色契约（`@bms/core/testing`）。
 *
 * 状态标签（`07_05`）/ 描述列表 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 三层取色优先级与兜底、非法值回落、布尔归一、令牌名前缀、未知值回退原值文本。
 */
import { describe, expect, it } from 'vitest';
/**
 * 状态语义色契约（`07_05` 冻结）。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeStatusContract(name, create) {
    describe(name, () => {
        it('取色三层优先级与兜底', () => {
            const target = create();
            expect(target.describe('enabled').semantic).toBe('success');
            expect(target.describe('pending').semantic).toBe('warning');
            expect(target.describe('locked').semantic).toBe('danger');
            expect(target.describe('draft').semantic).toBe('info');
            expect(target.describe('enabled', { sourceColor: 'danger' }).semantic).toBe('danger');
            expect(target.describe('enabled', { sourceColor: 'danger', semantic: 'primary' }).semantic).toBe('primary');
            expect(target.describe('custom_value', { colorMap: { custom_value: 'warning' } }).semantic).toBe('warning');
            expect(target.describe('unknown_value').semantic).toBe('info');
        });
        it('非法值回落下一层（来源色 / 映射值必须为五档语义色）', () => {
            const target = create();
            expect(target.describe('enabled', { sourceColor: '#ff0000' }).semantic).toBe('success');
            expect(target.describe('enabled', { colorMap: { enabled: '#ff0000' } }).semantic).toBe('success');
            expect(target.describe('enabled', { sourceColor: '#ff0000', colorMap: { enabled: 'danger' } }).semantic).toBe('danger');
        });
        it('布尔归一：真为 success、假为 info', () => {
            const target = create();
            expect(target.describe(true).semantic).toBe('success');
            expect(target.describe(false).semantic).toBe('info');
        });
        it('令牌名前缀与未知值文案回退', () => {
            const target = create();
            expect(target.describe('enabled').token.startsWith('--bms-')).toBe(true);
            expect(target.describe('enabled').known).toBe(true);
            const unknown = target.describe('未定义状态');
            expect(unknown.known).toBe(false);
            expect(unknown.text).toBe('未定义状态');
            expect(unknown.semantic).toBe('info');
            expect(target.describe('enabled', { text: '启用中' }).text).toBe('启用中');
        });
    });
}
