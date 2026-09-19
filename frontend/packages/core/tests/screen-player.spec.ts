// kiwi_id: 777
/** 大屏播放能力基类用例（08-9-2）：契约套件 + 能力身份与依赖 + 装载 + 按组件取数。 */

import { describe, expect, it } from 'vitest'

import {
  BaseAccess,
  BaseScreenPlayer,
  SCREEN_VIEW_PERM,
  validateCapabilityGraph,
  type ScreenPlayerJobs,
} from '../src'
import {
  createScreenPlayerJobs,
  describeScreenPlayerContract,
  SCREEN_PLAY_CONTRACT_COMPONENTS,
  SCREEN_PLAY_CONTRACT_PAGES,
  type ScreenPlayerContractTarget,
} from '../testing'

/** 具体大屏播放（可实例化）。 */
class DemoPlayer extends BaseScreenPlayer {}

/** 具体权限上下文（可实例化）。 */
class DemoAccess extends BaseAccess {}

/** 构造持查看权限的权限上下文。 */
function granted(): DemoAccess {
  const access = new DemoAccess()
  access.setCodes([SCREEN_VIEW_PERM])
  return access
}

/** 契约目标工厂（适配器接核心基类）。 */
function makeTarget(): ScreenPlayerContractTarget {
  const player = new DemoPlayer()
  player.setAccess(granted())
  player.setReady(true)
  return {
    get ready() {
      return player.ready
    },
    get degraded() {
      return player.degraded
    },
    get busy() {
      return player.busy
    },
    get phase() {
      return player.phase
    },
    get requestCount() {
      return player.requestCount
    },
    get playing() {
      return player.playing
    },
    get interval() {
      return player.interval
    },
    pages: () => player.pages,
    activePageId: () => player.activePageId,
    components: () => player.currentComponents,
    data: () => player.data,
    setReady: (value) => player.setReady(value),
    setOperators: (input) => {
      if (input.codes === undefined) {
        player.setAccess(undefined)
        return
      }
      const access = new DemoAccess()
      access.setCodes(input.codes)
      player.setAccess(access)
    },
    setJobs: (jobs) => player.setJobs(jobs as ScreenPlayerJobs),
    setPages: (pages) => player.setPages(pages),
    setComponents: (componentsByPage) => player.setComponents(componentsByPage),
    selectPage: (pageId) => player.selectPage(pageId),
    next: () => player.next(),
    prev: () => player.prev(),
    toggle: (force) => player.toggle(force),
    setPlaying: (value) => player.setPlaying(value),
    setInterval: (value) => player.setInterval(value),
    load: (input) => player.load(input),
    queryComponent: (componentId, pageId) => player.queryComponent(componentId, pageId),
    refreshPage: (pageId) => player.refreshPage(pageId),
  }
}

describeScreenPlayerContract('大屏播放编排契约（BaseScreenPlayer）', makeTarget)

describe('能力身份与依赖', () => {
  it('能力键与依赖登记无环', () => {
    const player = new DemoPlayer()
    expect(player.identifier).toBe('screen-player')
    expect(player.depends).toEqual(['access', 'notice', 'data-state', 'async-task'])
    const problems = validateCapabilityGraph().filter(
      (problem) => problem.key === 'screen-player' || problem.detail.includes('screen-player'),
    )
    expect(problems).toEqual([])
  })
})

describe('装载与轮播', () => {
  it('装载后按默认页与单页时长生效', async () => {
    const player = new DemoPlayer()
    player.setAccess(granted())
    player.setReady(true)
    player.setJobs(createScreenPlayerJobs())
    await player.load()

    player.setPages(SCREEN_PLAY_CONTRACT_PAGES)
    player.setComponents(SCREEN_PLAY_CONTRACT_COMPONENTS)
    player.selectPage('p2')
    expect(player.currentInterval).toBe(3000)
    expect(player.pageCount).toBe(2)
    expect(player.hasNext).toBe(true)

    player.setInterval(200)
    expect(player.interval).toBe(1000)
  })

  it('markLoaded 仅就绪时计数', () => {
    const player = new DemoPlayer()
    player.markLoaded()
    expect(player.requestCount).toBe(0)
    player.setReady(true)
    player.markLoaded()
    expect(player.requestCount).toBe(1)
  })
})
