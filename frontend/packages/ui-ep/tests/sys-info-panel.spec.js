/** 系统信息面板件用例（02_03 角色管理）：字段呈现与缺失占位。 */
import { mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { SysInfoPanel } from '../src';
const ElDescriptions = {
    name: 'ElDescriptions',
    props: ['column', 'border', 'size'],
    template: '<div class="el-descriptions"><slot /></div>',
};
const ElDescriptionsItem = {
    name: 'ElDescriptionsItem',
    props: ['label'],
    template: '<div class="el-descriptions-item"><span class="label">{{ label }}</span><slot /></div>',
};
const stubs = { ElDescriptions, ElDescriptionsItem };
describe('SysInfoPanel（02_03）', () => {
    it('按固定顺序呈现主键 / 版本 / 表单 / 审计字段', () => {
        const wrapper = mount(SysInfoPanel, {
            props: {
                info: {
                    id: '1001',
                    version: 3,
                    createdBy: '1001',
                    createdAt: '2026-10-07 09:30',
                    updatedBy: '1002',
                    updatedAt: '2026-10-07 11:20',
                    formKey: 'role_form',
                    formLabel: '角色管理',
                },
            },
            global: { stubs },
        });
        expect(wrapper.find('[data-test="sys-info-主键"]').text()).toBe('1001');
        expect(wrapper.find('[data-test="sys-info-版本"]').text()).toBe('3');
        expect(wrapper.find('[data-test="sys-info-表单"]').text()).toBe('角色管理');
        expect(wrapper.find('[data-test="sys-info-创建时间"]').text()).toBe('2026-10-07 09:30');
        expect(wrapper.find('[data-test="sys-info-更新时间"]').text()).toBe('2026-10-07 11:20');
    });
    it('缺失值以占位符呈现；表单回落 `formKey`；标题可关', () => {
        const wrapper = mount(SysInfoPanel, {
            props: { info: { id: 1, version: null, formKey: 'role_form' }, title: '' },
            global: { stubs },
        });
        expect(wrapper.find('[data-test="sys-info-版本"]').text()).toBe('—');
        expect(wrapper.find('[data-test="sys-info-创建人"]').text()).toBe('—');
        expect(wrapper.find('[data-test="sys-info-表单"]').text()).toBe('role_form');
        expect(wrapper.find('.bms-sys-info__title').exists()).toBe(false);
    });
});
