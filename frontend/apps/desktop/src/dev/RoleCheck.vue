<script setup lang="ts">
// 开发态核对页（02_03 角色管理）：表单框架（列表 Tab + 记录 Tab）+ 记录页三子页签 + 系统信息面板
// 的真实组装，作为《原型审查规范》实现侧截图对照载体（数据为本地样例，不调后端）；本页不进构建产物。
import { EmptyState, FormFrame, SysInfoPanel, type FormFrameTab } from '@bms/ui-ep'
import { computed, ref } from 'vue'

/** 页签（列表固定 + 两条记录）。 */
const tabs: FormFrameTab[] = [
  { key: 'list', title: '角色管理', type: 'list' },
  { key: 'r1', title: '运维管理员（ops_admin）', type: 'record', dirty: true },
  { key: 'r2', title: '只读角色（readonly）', type: 'record' },
]

/** 当前激活页签。 */
const active = ref('list')
/** 当前记录页签子页签。 */
const section = ref<'detail' | 'permission' | 'sys'>('detail')
/** 权限配置内层页签（缺省菜单权限：渲染「待返工」空态）。 */
const permTab = ref('menu')
/** 样例角色行。 */
const rows = [
  { code: 'ops_admin', name: '运维管理员', builtin: false, subjectCount: 2, status: 'enabled' },
  { code: 'audit_admin', name: '审计管理员', builtin: true, subjectCount: 1, status: 'enabled' },
  { code: 'readonly', name: '只读角色', builtin: false, subjectCount: 0, status: 'disabled' },
]
/** 样例系统信息。 */
const sysInfo = computed(() => ({
  id: '802553432413044736',
  version: 3,
  createdBy: '1001',
  createdAt: '2026-10-06 09:30',
  updatedBy: '1002',
  updatedAt: '2026-10-07 11:20',
  formKey: 'role_form',
  formLabel: '角色管理',
}))

/**
 * 页签关闭（核对页不拦截）。
 *
 * @param key 页签键。
 */
function onClose(key: string): void {
  if (key === active.value) {
    active.value = 'list'
  }
}
</script>

<template>
  <div class="role-check" data-test="role-check">
    <div class="role-check__bar">
      <strong>开发态核对 · 角色管理（02_03）</strong>
      <span class="role-check__hint" data-test="check-state">激活页签：{{ active }}</span>
    </div>

    <div class="role-check__body">
      <form-frame
        :model-value="active"
        :tabs="tabs"
        open-text="新增"
        @update:model-value="(key: string) => (active = key)"
        @close="onClose"
      >
        <template #list>
          <div class="role-check__toolbar">
            <el-button type="primary">新增</el-button>
            <el-button disabled>批量删除</el-button>
          </div>
          <div class="role-check__filter">
            <el-input class="role-check__kw" placeholder="角色码 / 名称" clearable />
            <el-select class="role-check__status" model-value="" placeholder="状态">
              <el-option label="启用" value="enabled" />
              <el-option label="停用" value="disabled" />
            </el-select>
            <el-button>查询</el-button>
          </div>
          <el-table :data="rows" border size="small" data-test="check-role-table">
            <el-table-column prop="code" label="角色码" min-width="140" />
            <el-table-column prop="name" label="角色名" min-width="160" />
            <el-table-column label="内置" width="90">
              <template #default="{ row }">
                <el-tag v-if="row.builtin" type="warning" size="small">内置</el-tag>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column prop="subjectCount" label="主体数" width="100" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.status === 'enabled' ? 'success' : 'info'" size="small">
                  {{ row.status === 'enabled' ? '启用' : '停用' }}
                </el-tag>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template #record="{ tab }">
          <div class="role-check__record">
            <div class="role-check__toolbar">
              <el-button type="primary">保存</el-button>
              <el-button>关闭</el-button>
              <span class="role-check__hint">记录页签：{{ tab?.title }}</span>
            </div>

            <el-tabs v-model="section" data-test="check-record-tabs">
              <el-tab-pane label="详细信息" name="detail">
                <el-form label-position="top">
                  <el-row :gutter="16">
                    <el-col :span="8">
                      <el-form-item label="角色码" required>
                        <el-input model-value="ops_admin" disabled />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="角色名" required>
                        <el-input model-value="运维管理员" />
                      </el-form-item>
                    </el-col>
                    <el-col :span="8">
                      <el-form-item label="状态">
                        <el-select model-value="enabled">
                          <el-option label="启用" value="enabled" />
                          <el-option label="停用" value="disabled" />
                        </el-select>
                      </el-form-item>
                    </el-col>
                  </el-row>
                </el-form>
              </el-tab-pane>

              <el-tab-pane label="权限配置" name="permission">
                <el-tabs v-model="permTab" data-test="check-perm-tabs">
                  <el-tab-pane label="菜单权限" name="menu">
                    <empty-state
                      type="unselected"
                      title="权限配置组件待组件库 08_04 返工"
                      description="菜单权限树接入位已预留（roleId / readonly / 元数据）。"
                    />
                  </el-tab-pane>
                  <el-tab-pane label="表单权限" name="form">
                    <empty-state type="unselected" title="权限配置组件待组件库 08_04 返工" description="表单权限面板返工中。" />
                  </el-tab-pane>
                  <el-tab-pane label="数据权限" name="data">
                    <empty-state type="unselected" title="权限配置组件待组件库 08_04 返工" description="数据权限只选不编面板返工中。" />
                  </el-tab-pane>
                  <el-tab-pane label="角色分配" name="assign">
                    <p class="role-check__hint" data-test="check-assign-hint">
                      用户分配内建（选择用户弹窗 + 已分配列表，随宿主保存）；岗位 / 部门分配由 mdm 插件插入，插件缺失即隐藏。
                    </p>
                  </el-tab-pane>
                </el-tabs>
              </el-tab-pane>

              <el-tab-pane label="系统信息" name="sys">
                <sys-info-panel :info="sysInfo" />
              </el-tab-pane>
            </el-tabs>
          </div>
        </template>
      </form-frame>
    </div>
  </div>
</template>

<style scoped>
.role-check {
  display: flex;
  flex-direction: column;
  box-sizing: border-box;
  height: 100vh;
  padding: var(--bms-space-4);
  background: var(--bms-color-bg-page);
}

.role-check__bar {
  display: flex;
  flex: none;
  gap: 12px;
  align-items: center;
  padding-bottom: var(--bms-space-3);
}

.role-check__hint {
  font-size: 12px;
  color: var(--bms-color-text-secondary);
}

.role-check__body {
  flex: 1;
  min-height: 0;
}

.role-check__record {
  display: flex;
  flex-direction: column;
  gap: var(--bms-space-3);
}

.role-check__toolbar {
  display: flex;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.role-check__filter {
  display: flex;
  gap: var(--bms-space-2);
  align-items: center;
  margin-bottom: var(--bms-space-3);
}

.role-check__kw {
  width: 220px;
}

.role-check__status {
  width: 140px;
}
</style>
