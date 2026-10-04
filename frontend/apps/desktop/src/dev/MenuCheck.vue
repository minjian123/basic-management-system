<script setup lang="ts">
// 开发态核对页（07_03_01 菜单/表单/按钮/字段挂接与动态菜单）：真实消费动态菜单接口
// （菜单树 → 侧栏、权限码 → 按钮显隐、字段权限矩阵），作为《原型审查规范》实现侧对照载体；
// 本页不进构建产物，MVP 页面本体的接入随各页面任务。
import { SideMenu } from '@bms/ui-ep'
import { ElButton } from 'element-plus'
import { computed, onMounted } from 'vue'

import { useMenuExpanded } from '@/composables/useMenuExpanded'
import { useMenuStore } from '@/stores/menu'

const menuStore = useMenuStore()
const menuExpanded = useMenuExpanded()

/** 菜单树（动态菜单 store；装载完成后自动更新）。 */
const menu = computed(() => menuStore.tree)

/** 表单元数据清单（按菜单路径列示：可见按钮码 + 字段权限）。 */
const formRows = computed(() =>
  Object.entries(menuStore.formIdByPath).map(([path, formId]) => {
    const form = menuStore.forms[formId]
    return {
      path,
      businessCode: form?.businessCode ?? '',
      buttonCodes: form?.visibleButtonCodes ?? [],
      fields: Object.entries(form?.fieldPerms ?? {}).map(([key, perm]) => ({
        key,
        visible: perm.visible === true,
        editable: perm.editable === true,
      })),
    }
  }),
)

/** 示例按钮权限码（取前若干个权限码，验证 `v-perm` 显隐）。 */
const sampleCodes = computed(() => menuStore.permissions.slice(0, 6))

onMounted(() => {
  void menuStore.load()
})

function reload(): void {
  void menuStore.reload()
}
</script>

<template>
  <div class="menu-check">
    <header class="menu-check__bar">
      <h1 class="menu-check__title">动态菜单核对页</h1>
      <span class="menu-check__meta" data-test="menu-check-meta">
        locale={{ menuStore.locale }} · version={{ menuStore.version }} · loaded={{ menuStore.loaded }} · 权限码
        {{ menuStore.permissions.length }} 项
      </span>
      <el-button data-test="menu-check-reload" @click="reload">重新装载</el-button>
      <el-button data-test="menu-check-reset-expanded" @click="menuExpanded.reset()">清空展开态</el-button>
    </header>

    <p v-if="menuStore.error !== null" class="menu-check__error" data-test="menu-check-error">
      装载失败：{{ menuStore.error }}
    </p>

    <div class="menu-check__body">
      <aside class="menu-check__side">
        <side-menu
          :menu="menu"
          active-path="/"
          :unique-opened="false"
          :default-openeds="menuExpanded.expandedKeys.value"
          :searchable="false"
          @open="menuExpanded.toggleOpen($event, true)"
          @close="menuExpanded.toggleOpen($event, false)"
        />
      </aside>

      <main class="menu-check__main">
        <section class="menu-check__card">
          <h2 class="menu-check__h2">按钮权限（`v-perm`，按权限码显隐）</h2>
          <div class="menu-check__row">
            <el-button v-for="code in sampleCodes" :key="code" v-perm="code">{{ code }}</el-button>
            <span v-if="sampleCodes.length === 0" class="menu-check__meta">无权限码（未装载或未授予）</span>
          </div>
          <div class="menu-check__row">
            <el-button v-perm="'menu:create'">示例：需 menu:create</el-button>
            <el-button v-perm="'menu:delete'">示例：需 menu:delete</el-button>
          </div>
        </section>

        <section class="menu-check__card">
          <h2 class="menu-check__h2">表单元数据（挂接链 + 字段权限）</h2>
          <p v-if="formRows.length === 0" class="menu-check__meta">无表单元数据</p>
          <div v-for="row in formRows" :key="row.path" class="menu-check__form" data-test="menu-check-form">
            <div class="menu-check__form-head">
              <strong>{{ row.path }}</strong>
              <span class="menu-check__meta">业务码 {{ row.businessCode }}</span>
              <span class="menu-check__meta">可见按钮 {{ row.buttonCodes.length }} 个</span>
            </div>
            <ul class="menu-check__fields">
              <li v-for="field in row.fields" :key="field.key">
                {{ field.key }} — 可见 {{ field.visible ? '是' : '否' }} · 可编辑
                {{ field.editable ? '是' : '否' }}
              </li>
              <li v-if="row.fields.length === 0" class="menu-check__meta">无字段元数据</li>
            </ul>
          </div>
        </section>
      </main>
    </div>
  </div>
</template>

<style scoped>
.menu-check {
  box-sizing: border-box;
  min-height: 100vh;
  padding: var(--bms-space-4);
  background: var(--bms-color-bg-page);
}

.menu-check__bar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-4);
}

.menu-check__title {
  margin: 0;
  font-size: var(--bms-font-size-lg);
  color: var(--bms-color-text);
}

.menu-check__meta {
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}

.menu-check__error {
  padding: var(--bms-space-2) var(--bms-space-3);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text);
  background: var(--bms-color-fill);
  border-radius: var(--bms-radius-md);
}

.menu-check__body {
  display: flex;
  gap: var(--bms-space-4);
  align-items: flex-start;
}

.menu-check__side {
  display: flex;
  flex: none;
  width: var(--bms-layout-sidebar-width);
  height: 70vh;
  overflow: hidden;
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.menu-check__main {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: var(--bms-space-4);
  min-width: 0;
}

.menu-check__card {
  padding: var(--bms-space-3) var(--bms-space-4);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.menu-check__h2 {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size);
  color: var(--bms-color-text);
}

.menu-check__row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bms-space-2);
  margin-bottom: var(--bms-space-2);
}

.menu-check__form + .menu-check__form {
  margin-top: var(--bms-space-3);
}

.menu-check__form-head {
  display: flex;
  gap: var(--bms-space-3);
  align-items: baseline;
  color: var(--bms-color-text);
}

.menu-check__fields {
  margin: var(--bms-space-2) 0 0;
  padding-left: var(--bms-space-6);
  font-size: var(--bms-font-size-sm);
  color: var(--bms-color-text-secondary);
}
</style>
