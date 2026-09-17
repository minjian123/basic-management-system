/**
 * 占位菜单树（对齐占位语义）：后端 `GET /menus/my` 未接入前的驱动数据。
 *
 * 真实菜单树（含权限过滤与 i18n 文案）随阶段七 ~ 八下发后，由宿主经
 * `configureMenuLoader` 注入替换；本文件只作占位演示（无徽标、含外链与隐藏项演示）。
 */

import type { MenuItem } from '@bms/ui-ep'

export const PLACEHOLDER_MENU: MenuItem[] = [
  { name: '工作台', path: '/', component: 'HomeView', icon: 'dashboard', sort: 1 },
  {
    name: '系统管理',
    icon: 'setting',
    sort: 10,
    children: [
      { name: '用户管理', path: '/system/user', component: 'PlaceholderView', sort: 1 },
      { name: '角色管理', path: '/system/role', component: 'PlaceholderView', sort: 2 },
      { name: '菜单管理', path: '/system/menu', component: 'PlaceholderView', sort: 3 },
    ],
  },
  {
    name: '内容管理',
    icon: 'document',
    sort: 20,
    children: [
      { name: '文章管理', path: '/content/article', component: 'PlaceholderView', sort: 1 },
      { name: '分类管理', path: '/content/category', component: 'PlaceholderView', sort: 2 },
    ],
  },
  { name: '平台文档', path: 'https://example.com/docs', icon: 'link', external: true, sort: 90 },
  { name: '隐藏页面', path: '/hidden/demo', component: 'PlaceholderView', hidden: true, sort: 100 },
]
