<script setup lang="ts">
// 开发态核对页（07_06_01 前端主框架布局样式）：布局族真实组装（主框架壳 + 导航 / 容器 / 分栏族）+
// 亮暗主题与断点切换，作为《原型审查规范》§4.9 实现侧截图对照载体；本页不进构建产物。
import type { MenuNode } from '@bms/core'
import {
  CollapsePanel,
  CollapsePanelGroup,
  ContentTabs,
  DualTabs,
  FormLayoutShell,
  GridItem,
  GridLayout,
  LayoutCard,
  MainLayout,
  PageContainer,
  SpacingDivider,
  TreeMasterDetail,
  useResponsive,
  type MasterTreeNode,
  type TabNavItem,
} from '@bms/ui-ep'
import { ref } from 'vue'

/** 侧边菜单（一级配图标、二级纯文字；含三级与搜索过滤）。 */
const menu: MenuNode[] = [
  { path: '/home', title: '工作台', icon: 'el:HomeFilled' },
  {
    path: '/sys',
    title: '系统管理',
    icon: 'el:Setting',
    children: [
      { path: '/sys/users', title: '用户管理' },
      { path: '/sys/roles', title: '角色管理' },
      { path: '/sys/menus', title: '菜单管理' },
    ],
  },
  {
    path: '/biz',
    title: '业务管理',
    icon: 'el:Files',
    children: [
      {
        path: '/biz/orders',
        title: '业务单据',
        children: [{ path: '/biz/orders/list', title: '单据列表' }],
      },
    ],
  },
]

/** 当前激活路径。 */
const activePath = ref('/sys/users')
/** 多标签页（首个为固定工作台，不可关闭）。 */
const tabs: TabNavItem[] = [
  { key: '/home', title: '工作台', path: '/home', closable: false },
  { key: '/sys/users', title: '用户管理', path: '/sys/users' },
  { key: '/sys/roles', title: '角色管理', path: '/sys/roles' },
  { key: '/sys/menus', title: '菜单管理', path: '/sys/menus' },
  { key: '/biz/orders/list', title: '单据列表', path: '/biz/orders/list' },
]
/** 当前激活标签键。 */
const activeTabKey = ref('/sys/users')

/** 当前主题（切换 `data-theme` 令牌作用域）。 */
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')
/** 当前断点（与 `useResponsive` 同一来源，核对用）。 */
const { breakpoint } = useResponsive()

/** 折叠面板展开项。 */
const opened = ref<string | string[]>(['a'])
/** 内容页签激活键。 */
const contentTab = ref('t1')
/** 内容页签项。 */
const contentTabItems = [
  { key: 't1', title: '页签一' },
  { key: 't2', title: '页签二' },
]
/** 双层页签上层 / 下层。 */
const dualPrimary: TabNavItem[] = [
  { key: 'p1', title: '分组一', path: '/p1' },
  { key: 'p2', title: '分组二', path: '/p2' },
]
const dualSecondary: TabNavItem[] = [{ key: 's1', title: '明细一', path: '/s1' }]
/** 树形主从数据。 */
const treeData: MasterTreeNode[] = [
  { key: 'n1', label: '研发中心', children: [{ key: 'n2', label: '前端组' }] },
  { key: 'n3', label: '市场部' },
]

/**
 * 菜单选择（仅切换高亮，核对导航态）。
 *
 * @param path 菜单路径。
 */
function onMenuSelect(path: string): void {
  activePath.value = path
}

/**
 * 标签选择。
 *
 * @param key 标签键。
 */
function onTabSelect(key: string): void {
  activeTabKey.value = key
}

/**
 * 标签关闭（固定标签不可关闭）。
 *
 * @param key 标签键。
 */
function onTabClose(key: string): void {
  activeTabKey.value = key
}

/** 切换亮 / 暗主题（写入根元素令牌属性）。 */
function toggleTheme(): void {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
}
</script>

<template>
  <div class="layout-check" data-test="layout-check">
    <div class="layout-check__bar">
      <strong>开发态核对 · 前端主框架布局（07-06_01）</strong>
      <span class="layout-check__hint" data-test="check-state">断点：{{ breakpoint }}｜主题：{{ theme }}</span>
      <el-button size="small" data-test="check-theme" @click="toggleTheme">切换亮 / 暗主题</el-button>
    </div>

    <main-layout
      class="layout-check__shell"
      :menu="menu"
      :active-path="activePath"
      :tabs="tabs"
      :active-tab-key="activeTabKey"
      app-title="BMS"
      storage-key="bms:layout-check"
      @menu-select="onMenuSelect"
      @tab-select="onTabSelect"
      @tab-close="onTabClose"
    >
      <template #header-right>
        <span class="layout-check__hint">顶栏右侧插槽（业务项由宿主装配）</span>
      </template>

      <page-container title="工作台" description="布局族容器 / 导航 / 分栏族核对样例">
        <template #extra>
          <el-button size="small" type="primary">主操作</el-button>
        </template>

        <grid-layout :gutter="16">
          <grid-item :span="12">
            <layout-card title="卡片（可折叠）" collapsible>
              <collapse-panel-group v-model="opened">
                <collapse-panel name="a" title="面板一">折叠面板内容一</collapse-panel>
                <collapse-panel name="b" title="面板二">折叠面板内容二</collapse-panel>
              </collapse-panel-group>
            </layout-card>
          </grid-item>
          <grid-item :span="12">
            <layout-card title="双层页签与内容页签">
              <dual-tabs :primary="dualPrimary" primary-key="p1" :secondary="dualSecondary" secondary-key="s1" />
              <spacing-divider size="sm">分隔</spacing-divider>
              <content-tabs v-model="contentTab" :tabs="contentTabItems">
                <template #t1>内容页签一</template>
                <template #t2>内容页签二</template>
              </content-tabs>
            </layout-card>
          </grid-item>
        </grid-layout>

        <spacing-divider size="lg">树形主从 / 表单框架壳</spacing-divider>

        <div class="layout-check__split">
          <tree-master-detail :tree-data="treeData" selected-key="n2">
            <form-layout-shell
              :list-tab="{ key: 'list', title: '列表', path: '/list' }"
              :detail-tabs="[{ key: 'd1', title: '详情一', path: '/d1' }]"
              active-detail-key="list"
            >
              <template #list>
                <p>列表内容（FormLayoutShell）</p>
              </template>
              <template #detail>
                <p>详情内容</p>
              </template>
            </form-layout-shell>
          </tree-master-detail>
        </div>
      </page-container>
    </main-layout>
  </div>
</template>

<style scoped>
.layout-check {
  display: flex;
  flex-direction: column;
  height: 100vh;
}

.layout-check__bar {
  display: flex;
  align-items: center;
  flex: none;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--bms-color-border);
}

.layout-check__hint {
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}

.layout-check__shell {
  flex: 1;
  min-height: 0;
}

.layout-check__split {
  height: 260px;
}
</style>
