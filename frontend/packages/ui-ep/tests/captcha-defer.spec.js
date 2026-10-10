// kiwi_id: 2232
/** 验证码件族「延迟提交」模式用例（05_01）：defer 零校验请求 + 凭证上抛；verify 缺省模式行为不变。 */
import { createCaptchaSourceStub } from '@bms/core/testing';
import { flushPromises, mount } from '@vue/test-utils';
import { describe, expect, it } from 'vitest';
import { CaptchaField, ImageCaptcha, SliderCaptcha, SmsCaptcha } from '../src';
describe('验证码件族延迟提交模式（Kiwi 2232）', () => {
    it('图形件 defer：初始出题触发 loaded、输入上抛 credential 且零校验请求', async () => {
        const source = createCaptchaSourceStub();
        const wrapper = mount(ImageCaptcha, {
            props: { ready: true, source: source.source, submitMode: 'defer' },
        });
        await flushPromises();
        expect(source.calls).toEqual(['challenge']);
        const loadedId = wrapper.emitted('loaded')?.[0]?.[0];
        expect(loadedId).toBeTruthy();
        await wrapper.find('[data-test="captcha-input"]').setValue('ab12');
        const credential = wrapper.emitted('credential')?.at(-1)?.[0];
        expect(credential).toMatchObject({
            kind: 'image',
            captchaId: loadedId,
            code: 'ab12',
        });
        await wrapper.find('[data-test="captcha-input"]').trigger('keyup.enter');
        await flushPromises();
        expect(source.calls.filter((call) => call === 'verify')).toHaveLength(0);
        expect(wrapper.emitted('pass')).toBeUndefined();
    });
    it('图形件 verify（缺省）：回车仍自行校验并上抛 pass', async () => {
        const source = createCaptchaSourceStub();
        const wrapper = mount(ImageCaptcha, {
            props: { ready: true, source: source.source },
        });
        await flushPromises();
        expect(wrapper.find('[data-test="image-captcha"]').exists()).toBe(true);
        const input = wrapper.find('[data-test="captcha-input"]');
        await input.setValue('ab12');
        await input.trigger('keyup.enter');
        await flushPromises();
        expect(source.calls).toContain('verify');
        expect(wrapper.emitted('pass')).toHaveLength(1);
        expect(wrapper.emitted('credential')).toBeUndefined();
    });
    it('滑块件 defer：松手零校验请求并上抛轨迹凭证', async () => {
        const source = createCaptchaSourceStub();
        const wrapper = mount(SliderCaptcha, {
            props: { ready: true, source: source.source, submitMode: 'defer' },
        });
        await flushPromises();
        expect(source.calls).toEqual(['challenge']);
        const handle = wrapper.find('[data-test="captcha-slider-handle"]');
        handle.element.dispatchEvent(new MouseEvent('pointerdown', { clientX: 0, bubbles: true }));
        window.dispatchEvent(new MouseEvent('pointermove', { clientX: 100 }));
        window.dispatchEvent(new MouseEvent('pointerup', { clientX: 100 }));
        await flushPromises();
        expect(source.calls.filter((call) => call === 'verify')).toHaveLength(0);
        const credential = wrapper.emitted('credential')?.at(-1)?.[0];
        expect(credential.kind).toBe('slider');
        expect(credential.captchaId).toBeTruthy();
        expect((credential.trace ?? []).length).toBeGreaterThanOrEqual(2);
        wrapper.unmount();
    });
    it('滑块件 defer：键盘提交同样只上抛凭证；未拖动零上抛', async () => {
        const source = createCaptchaSourceStub();
        const wrapper = mount(SliderCaptcha, {
            props: { ready: true, source: source.source, submitMode: 'defer' },
        });
        await flushPromises();
        const handle = wrapper.find('[data-test="captcha-slider-handle"]');
        await handle.trigger('keydown', { key: 'Enter' });
        await flushPromises();
        expect(wrapper.emitted('credential')).toBeUndefined();
        await handle.trigger('keydown', { key: 'ArrowRight' });
        await handle.trigger('keydown', { key: 'ArrowRight' });
        await handle.trigger('keydown', { key: 'Enter' });
        await flushPromises();
        expect(source.calls.filter((call) => call === 'verify')).toHaveLength(0);
        expect(wrapper.emitted('credential')?.length).toBeGreaterThan(0);
        wrapper.unmount();
    });
    it('短信件 defer：发送出题触发 loaded、输入上抛 credential 且零校验请求', async () => {
        const source = createCaptchaSourceStub();
        const wrapper = mount(SmsCaptcha, {
            props: {
                ready: true,
                source: source.source,
                phone: '13800005678',
                submitMode: 'defer',
            },
        });
        await flushPromises();
        await wrapper.find('[data-test="captcha-send"]').trigger('click');
        await flushPromises();
        expect(wrapper.emitted('loaded')?.at(-1)?.[0]).toBe('s1');
        await wrapper.find('[data-test="captcha-input"]').setValue('123456');
        const credential = wrapper.emitted('credential')?.at(-1)?.[0];
        expect(credential).toMatchObject({
            kind: 'sms',
            captchaId: 's1',
            code: '123456',
        });
        await wrapper.find('[data-test="captcha-input"]').trigger('keyup.enter');
        await flushPromises();
        expect(source.calls.filter((call) => call === 'verify')).toHaveLength(0);
        wrapper.unmount();
    });
    it('分发壳透传 submitMode 与 credential / loaded 事件', async () => {
        const source = createCaptchaSourceStub();
        const wrapper = mount(CaptchaField, {
            props: {
                modelValue: '',
                ready: true,
                kind: 'slider',
                source: source.source,
                submitMode: 'defer',
            },
        });
        await flushPromises();
        const handle = wrapper.find('[data-test="captcha-slider-handle"]');
        handle.element.dispatchEvent(new MouseEvent('pointerdown', { clientX: 0, bubbles: true }));
        window.dispatchEvent(new MouseEvent('pointermove', { clientX: 100 }));
        window.dispatchEvent(new MouseEvent('pointerup', { clientX: 100 }));
        await flushPromises();
        expect(source.calls.filter((call) => call === 'verify')).toHaveLength(0);
        expect(wrapper.emitted('loaded')?.length).toBeGreaterThan(0);
        expect(wrapper.emitted('credential')?.length).toBeGreaterThan(0);
        wrapper.unmount();
    });
});
