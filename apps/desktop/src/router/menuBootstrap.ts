/**
 * 菜单引导（应用装配）：占位 loader 注入 → 加载 → 菜单路由注册。
 *
 * 由 `main.ts` 动态导入调用（避免基座代码提升为应用入口静态依赖）；
 * 真实菜单接口随阶段七 ~ 八经 `configureMenuLoader` 注入替换占位。
 */

import type { Router } from 'vue-router'

import { PLACEHOLDER_MENU } from '@/config/placeholder-menu'
import { useMenuStore } from '@/stores/menu'

import { registerMenuRoutes } from './menuRoutes'

/** 引导菜单（幂等：已加载则只补注册） */
export async function bootstrapMenus(router: Router): Promise<void> {
  const store = useMenuStore()
  if (!store.loaded) {
    store.configureLoader({ load: async () => PLACEHOLDER_MENU })
    await store.load()
  }
  registerMenuRoutes(router, store.menus)
}
