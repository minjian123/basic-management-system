/** 权限指令用例（Kiwi 719）：anyOf / .all / .not / 版本重评（双端同款）。 */

import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, h, nextTick, withDirectives, type DirectiveArguments } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'

import { configurePermissionChecker } from '@bms/ui-vant'

import { vPerm } from '@/directives/perm'
import { i18n } from '@/i18n'
import { usePermissionStore } from '@/stores/permission'

/** 宿主：单按钮 + v-perm（值 / 修饰符可配） */
const Host = defineComponent({
  props: {
    permValue: { type: [String, Array] as unknown as () => string | string[], default: 'a' },
    permModifiers: { type: Object as unknown as () => Record<string, boolean>, default: () => ({}) },
  },
  setup(props) {
    return () =>
      withDirectives(h('button', { class: 'target', type: 'button' }, '按钮'), [
        [vPerm, props.permValue, '', props.permModifiers],
      ] as DirectiveArguments)
  },
})

async function settle(): Promise<void> {
  await nextTick()
  await nextTick()
}

/** 挂载到 document.body（断言真实 DOM 移除 / 回插；不依赖组件根引用） */
function mountHost(codes: string[], permValue: string | string[] = 'a', modifiers: Record<string, boolean> = {}) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const store = usePermissionStore()
  // 指令经 ui-vant 注入点判定；接权限 store 语义
  configurePermissionChecker((list, mode) =>
    mode === 'all' ? store.hasAll([...list]) : store.hasAny([...list]),
  )
  store.setCodes(codes)
  const container = document.createElement('div')
  document.body.appendChild(container)
  const wrapper = mount(Host, {
    props: { permValue, permModifiers: modifiers },
    attachTo: container,
    global: { plugins: [pinia, i18n] },
  })
  return { wrapper, store, container }
}

afterEach(() => {
  document.body.innerHTML = ''
})

describe('权限指令（Kiwi 719）', () => {
  it('① 有权限保留、无权限移除 DOM', () => {
    const granted = mountHost(['a'])
    expect(document.querySelector('.target')).not.toBeNull()
    granted.wrapper.unmount()

    const denied = mountHost([])
    expect(document.querySelector('.target')).toBeNull()
    denied.wrapper.unmount()
  })

  it('② 数组默认 anyOf；③ .all 需全部满足', async () => {
    const anyOf = mountHost(['a'], ['a', 'b'])
    expect(document.querySelector('.target')).not.toBeNull()
    await anyOf.wrapper.setProps({ permValue: ['c', 'd'] })
    expect(document.querySelector('.target')).toBeNull()
    anyOf.wrapper.unmount()

    const all = mountHost(['a', 'b'], ['a', 'b'], { all: true })
    expect(document.querySelector('.target')).not.toBeNull()
    await all.wrapper.setProps({ permValue: ['a', 'c'] })
    expect(document.querySelector('.target')).toBeNull()
    all.wrapper.unmount()
  })

  it('④ .not 取反；⑤ 空值 / 空数组不限制', async () => {
    const notHost = mountHost(['notice:update'], 'notice:update', { not: true })
    expect(document.querySelector('.target')).toBeNull()
    await notHost.wrapper.setProps({ permValue: 'notice:remove' })
    expect(document.querySelector('.target')).not.toBeNull()
    notHost.wrapper.unmount()

    const empty = mountHost([], '')
    expect(document.querySelector('.target')).not.toBeNull()
    await empty.wrapper.setProps({ permValue: [] })
    expect(document.querySelector('.target')).not.toBeNull()
    empty.wrapper.unmount()
  })

  it('⑥ 权限版本变更触发重评：恢复回插 / 收回再移除', async () => {
    const { wrapper, store } = mountHost([], 'a')
    expect(document.querySelector('.target')).toBeNull()

    store.setCodes(['a'])
    await settle()
    expect(document.querySelector('.target')).not.toBeNull()

    store.setCodes(['b'])
    await settle()
    expect(document.querySelector('.target')).toBeNull()
    wrapper.unmount()
  })

  it('⑦ updated 值变化重评', async () => {
    const { wrapper } = mountHost(['a'])
    expect(document.querySelector('.target')).not.toBeNull()
    await wrapper.setProps({ permValue: 'b' })
    expect(document.querySelector('.target')).toBeNull()
    await wrapper.setProps({ permValue: 'a' })
    expect(document.querySelector('.target')).not.toBeNull()
    wrapper.unmount()
  })

  it('⑧ 卸载清理（监听停止、无残留报错）', async () => {
    const { wrapper, store } = mountHost([], 'a')
    wrapper.unmount()
    expect(() => {
      store.setCodes(['a'])
    }).not.toThrow()
    await nextTick()
  })
})
