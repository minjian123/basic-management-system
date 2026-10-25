<script setup lang="ts">
// 菜单记录页「详细信息」：父级 / 类型 / 路径 / 视图组件 / 排序（只读）/ 侧栏显示 / 图标 / 多语言名称 / 状态。
// 对照原型《10_菜单管理/03_菜单表单页.html》详细信息页签；排序由菜单维护页拖拽调整，本页只读。
defineOptions({ name: 'MenuDetailSection' })

import { IconPicker, MultilingualNameField } from '@bms/ui_ep'
import { computed } from 'vue'

import { ENABLED_LOCALES } from '../metaLocale'
import type { MenuDraft } from './menuDraft'
import type { MenuTreeOption } from './menuTree'

const props = defineProps<{
  /** 父级下拉选项（已排除自身子树）。 */
  parentOptions: MenuTreeOption[]
  /** 当前登录用户语言（必填语言）。 */
  userLocale: string
  /** 是否编辑态。 */
  editing: boolean
}>()

/** 菜单本体草稿（与记录页双向绑定）。 */
const form = defineModel<MenuDraft>('form', { required: true })

/** 菜单类型（由视图组件是否为空派生）。 */
const menuType = computed<'directory' | 'menu'>({
  get: () => (form.value.component.trim() === '' ? 'directory' : 'menu'),
  set: (value) => {
    if (value === 'directory') {
      form.value.component = ''
    }
  },
})

/** 侧边栏是否显示（`hidden` 取反）。 */
const visible = computed<boolean>({
  get: () => !form.value.hidden,
  set: (value) => {
    form.value.hidden = !value
  },
})

/** 是否启用。 */
const enabled = computed<boolean>({
  get: () => form.value.status === 'enabled',
  set: (value) => {
    form.value.status = value ? 'enabled' : 'disabled'
  },
})

/**
 * 回写多语言名称（内容相同不回写，避免受控件同步回环）。
 *
 * @param next 多语言映射。
 */
function applyNames(next: Record<string, string>): void {
  const keys = new Set([...Object.keys(next), ...Object.keys(form.value.i18n)])
  for (const key of keys) {
    if ((next[key] ?? '') !== (form.value.i18n[key] ?? '')) {
      form.value.i18n = { ...next }
      return
    }
  }
}
</script>

<template>
  <el-row :gutter="16">
    <el-col :span="8">
      <el-form-item label="父级菜单">
        <el-tree-select
          v-model="form.parent_id"
          :data="props.parentOptions"
          node-key="id"
          check-strictly
          :render-after-expand="false"
          style="width: 100%"
          data-test="menu-parent"
        />
      </el-form-item>
    </el-col>
    <el-col :span="8">
      <el-form-item label="菜单类型">
        <el-select v-model="menuType" style="width: 100%" data-test="menu-type">
          <el-option label="目录" value="directory" />
          <el-option label="菜单" value="menu" />
        </el-select>
        <div class="menu-detail__hint">按钮为独立实体（挂表单 / 权限码），在「挂接配置 · 按钮维护」维护</div>
      </el-form-item>
    </el-col>
    <el-col :span="8">
      <el-form-item label="路由路径" required>
        <el-input v-model="form.path" placeholder="/sys/menus" data-test="menu-path" />
      </el-form-item>
    </el-col>
  </el-row>

  <el-row :gutter="16">
    <el-col :span="8">
      <el-form-item label="视图组件">
        <el-input
          v-model="form.component"
          :disabled="menuType === 'directory'"
          placeholder="目录节点留空；菜单填视图组件标识"
          data-test="menu-component"
        />
      </el-form-item>
    </el-col>
    <el-col :span="8">
      <el-form-item label="排序">
        <el-input :model-value="String(form.sort)" readonly data-test="menu-sort" />
        <div class="menu-detail__hint">排序在菜单维护页用拖拽调整（唯一排序方式），本页只读</div>
      </el-form-item>
    </el-col>
    <el-col :span="8">
      <el-form-item label="侧边栏显示">
        <el-switch v-model="visible" active-text="显示" inactive-text="隐藏" data-test="menu-visible" />
        <div class="menu-detail__hint">隐藏仅隐藏侧边栏入口，权限仍生效（路由可直达）</div>
      </el-form-item>
    </el-col>
  </el-row>

  <el-row :gutter="16">
    <el-col :span="24">
      <el-form-item label="图标">
        <icon-picker
          v-model="form.icon"
          placeholder="未选择"
          :disabled="!props.editing"
          include-custom
          data-test="menu-icon"
        />
        <div class="menu-detail__hint">图标键口径：<code>el:</code> 平台官方 / <code>biz:</code> 业务自绘 / <code>custom:</code> 租户自定义</div>
      </el-form-item>
    </el-col>
  </el-row>

  <el-row :gutter="16">
    <el-col :span="24">
      <el-form-item label="名称" required>
        <multilingual-name-field
          :model-value="form.i18n"
          :locales="ENABLED_LOCALES"
          :user-locale="props.userLocale"
          required
          data-test="menu-name"
          @change="applyNames"
        />
        <div class="menu-detail__hint">语言由启用语言清单驱动；必填语言＝当前登录用户语言，其余可缺省回退</div>
      </el-form-item>
    </el-col>
  </el-row>

  <el-row :gutter="16">
    <el-col :span="8">
      <el-form-item label="状态">
        <el-switch v-model="enabled" active-text="启用" inactive-text="停用" data-test="menu-status" />
      </el-form-item>
    </el-col>
    <el-col :span="16">
      <el-form-item label="说明">
        <span class="menu-detail__hint">路径 / 组件冲突或格式非法将拒绝保存（40203）；名称按 locale 存多语言附表</span>
      </el-form-item>
    </el-col>
  </el-row>
</template>

<style scoped>
.menu-detail__hint {
  margin-top: var(--bms-space-1);
  font-size: var(--bms-font-size-xs);
  line-height: var(--bms-line-height);
  color: var(--bms-color-text-secondary);
}
</style>
