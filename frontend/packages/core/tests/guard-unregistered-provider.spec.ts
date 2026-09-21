// kiwi_id: 976
/**
 * 护栏：「不注册不可用」——随包 / 随模块引入但未登记的扩展点不可解析、不参与渲染。
 *
 * 断言面：① 构造注册项不产生注册副作用（未登记即不可解析）；
 * ② 登记是生效的唯一通道（登记后方可解析）；③ fixture：模块声明未经装配不生效。
 */

import { describe, expect, it } from 'vitest'

import {
  ComponentProvider,
  I18nPackProvider,
  IconProvider,
  PageAreaProvider,
  ThemeTokenProvider,
  WorkbenchCardProvider,
  assembleRegistrations,
  createRegistries,
} from '../src'

/** 探针注册项（模拟「随包 / 随模块引入但未登记」）。 */
const probeComponent = new ComponentProvider('probe:panel', {})
/** 探针图标。 */
const probeIcon = new IconProvider('probe:sparkles', 'sparkles')
/** 探针工作台卡片。 */
const probeCard = new WorkbenchCardProvider('probe:summary', {}, '探针卡片')
/** 探针页面区域项。 */
const probeArea = new PageAreaProvider('probe:hero', 'layout.header', {})
/** 探针主题令牌。 */
const probeToken = new ThemeTokenProvider('probe:brand', { '--bms-color-primary': '#000000' })
/** 探针文案包。 */
const probePack = new I18nPackProvider('probe:zh-cn', { 'probe.title': '探针' })

describe('不注册不可用护栏（Kiwi 976）', () => {
  it('① 构造注册项不产生注册副作用——未登记即不可解析', () => {
    const registries = createRegistries()
    expect(registries.component.get(probeComponent.key)).toBeUndefined()
    expect(registries.icon.resolve(probeIcon.key)).toBeUndefined()
    expect(registries.workbenchCard.get(probeCard.key)).toBeUndefined()
    expect(registries.pageArea.get(probeArea.key)).toBeUndefined()
    expect(registries.pageArea.resolveByArea('layout.header')).toEqual([])
    expect(registries.themeToken.resolve(probeToken.key)).toBeUndefined()
    expect(registries.i18nPack.resolve(probePack.key)).toBeUndefined()
    expect(registries.i18nPack.byLocale('zh-cn')).toEqual([])
    expect(registries.component.keys()).toEqual([])
  })

  it('② 登记是生效的唯一通道——登记后方可解析', () => {
    const registries = createRegistries()
    registries.component.register(probeComponent)
    registries.icon.register(probeIcon)
    registries.workbenchCard.register(probeCard)
    registries.pageArea.register(probeArea)
    registries.themeToken.register(probeToken)
    registries.i18nPack.register(probePack)

    expect(registries.component.get('probe:panel')).toBe(probeComponent)
    expect(registries.icon.resolve('probe:sparkles')).toBe('sparkles')
    expect(registries.workbenchCard.get('probe:summary')?.title).toBe('探针卡片')
    expect(registries.pageArea.resolveByArea('layout.header').map((item) => item.key)).toEqual(['probe:hero'])
    expect(registries.themeToken.resolve('probe:brand')).toEqual({ '--bms-color-primary': '#000000' })
    expect(registries.i18nPack.byLocale('ZH-CN').map((item) => item.key)).toEqual(['probe:zh-cn'])
  })

  it('③ fixture：模块声明未经装配不生效，装配后生效', () => {
    const registries = createRegistries()
    const declaration = {
      components: { 'probe:panel': {} },
      regions: [{ key: 'probe:hero', area: 'layout.header', component: {} }],
      themeTokens: [{ key: 'probe:brand', tokens: { '--bms-color-primary': '#000000' } }],
      i18nPacks: [{ key: 'probe:zh-cn', messages: { 'probe.title': '探针' } }],
    }

    expect(registries.component.get('probe:panel')).toBeUndefined()
    const keys = assembleRegistrations(registries, 'probe', declaration)
    expect(keys).toHaveLength(4)
    expect(registries.component.get('probe:panel')).toBeDefined()
    expect(registries.pageArea.resolveByArea('layout.header')).toHaveLength(1)
    expect(registries.themeToken.resolve('probe:brand')).toBeDefined()
    expect(registries.i18nPack.resolve('probe:zh-cn')).toBeDefined()
  })
})
