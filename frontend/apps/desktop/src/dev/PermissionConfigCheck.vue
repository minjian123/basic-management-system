<script setup lang="ts">
// 开发态核对页（08_04_02）：授权总容器（四类页签 + 全量覆盖提交）与五件实例 + 12 项自检上屏（本页不进构建产物）。
import {
  BaseAccess,
  type DataScopeRow,
  type FieldPermRow,
  type PermissionJobs,
  type PermissionSnapshot,
  type PermissionSubject,
  type PermissionTab,
} from '@bms/core'
import { DataScopePanel, FieldPermMatrix, PermissionConfig, PermissionTree, SubjectBinding } from '@bms/ui-ep'
import { nextTick, onMounted, ref } from 'vue'

/** 权限上下文（保存成功后经取码处理函数刷新）。 */
class DemoAccess extends BaseAccess {}

const access = new DemoAccess()
access.setCodes(['role:grant'])

/** 样例授权快照（角色 `r1`；含挂接缺失菜单）。 */
const snapshot: PermissionSnapshot = {
  roleId: 'r1',
  nodes: [
    {
      key: 'menu:user',
      label: '用户管理',
      type: 'menu',
      icon: 'el:User',
      children: [
        {
          key: 'form:user',
          label: '用户表单',
          type: 'form',
          children: [
            { key: 'biz:user', label: '用户业务', type: 'business' },
            { key: 'act:user:create', label: '新增用户', type: 'action' },
            { key: 'act:user:update', label: '编辑用户', type: 'action' },
          ],
        },
      ],
    },
    { key: 'menu:orphan', label: '未挂接菜单', type: 'menu', detached: true },
  ],
  fieldPerms: [
    {
      formKey: 'form:user',
      formLabel: '用户表单',
      fields: [
        { key: 'name', label: '姓名' },
        { key: 'salary', label: '薪资' },
        { key: 'idcard', label: '证件号' },
      ],
    },
  ],
  dataScopes: [{ actionKey: 'act:user:list', actionLabel: '查询', expression: '' }],
  subjects: [],
}

/** 字段权限矩阵（运行态口径，供单独复用示例）。 */
const fieldRows: FieldPermRow[] = [
  {
    formKey: 'form:user',
    formLabel: '用户表单',
    fields: [
      { key: 'name', label: '姓名', visible: true, editable: true },
      { key: 'salary', label: '薪资', visible: true, editable: true },
      { key: 'idcard', label: '证件号', visible: true, editable: true },
    ],
  },
]

/** 数据范围行（运行态口径，供单独复用示例）。 */
const scopeRows: DataScopeRow[] = [{ actionKey: 'act:user:list', actionLabel: '查询', expression: '' }]

/** 主体候选。 */
const candidates: PermissionSubject[] = [
  { id: 'u1', type: 'user', name: '张三' },
  { id: 'u2', type: 'user', name: '李四' },
  { id: 'p1', type: 'position', name: '财务主管' },
  { id: 'd1', type: 'dept', name: '研发部' },
]

/** 数据范围预置变量。 */
const scopeVariables = [
  { key: 'current_user', label: '@current_user', insert: '@current_user' },
  { key: 'current_dept', label: '@current_dept', insert: '@current_dept' },
  { key: 'current_dept_tree', label: '@current_dept_tree', insert: '@current_dept_tree' },
  { key: 'tenant', label: '@tenant', insert: '@tenant' },
]

/** 数据范围已注册字段。 */
const scopeFields = [
  { key: 'dept_id', label: 'dept_id', insert: 'dept_id' },
  { key: 'created_by', label: 'created_by', insert: 'created_by' },
]

/** 常用范围模板。 */
const scopeTemplates = [
  { key: 'self', label: '仅本人', expression: 'created_by = @current_user' },
  { key: 'dept', label: '本部门', expression: 'dept_id = @current_dept' },
  { key: 'dept-tree', label: '本部门及下级', expression: 'dept_id IN @current_dept_tree' },
]

/** 提交携带的幂等键（核对幂等语义）。 */
const submittedKeys: string[] = []
/** 占位实例取数次数（应恒为 0）。 */
const placeholderLoadCalls = ref(0)
/** 下次提交是否失败（演示错误码定位）。 */
let failNext = false

/** 注入的处理函数集（真实 RBAC 接口由阶段七联调，此处为演示实现）。 */
const jobs: PermissionJobs = {
  load: async () => snapshot,
  submit: async (input) => {
    submittedKeys.push(input.idempotencyKey)
    if (failNext) {
      failNext = false
      throw Object.assign(new Error('规则表达式非法'), { code: 30047 })
    }
    return { recordVersion: submittedKeys.length }
  },
  loadPermissionCodes: async () => ['role:grant', 'user:create'],
}

/** 占位实例的处理函数（就绪前不得被调用）。 */
const placeholderJobs: PermissionJobs = {
  load: async () => {
    placeholderLoadCalls.value += 1
    return snapshot
  },
}

/** 当前页签（受控）。 */
const tab = ref<PermissionTab>('tree')
/** 容器实例。 */
const configRef = ref<InstanceType<typeof PermissionConfig>>()

/** 自检结果。 */
const checks = ref<{ label: string; pass: boolean }[]>([])

/**
 * 作用域内查询元素。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function q(scope: string, selector: string): Element | null {
  return document.querySelector(`[data-check-scope="${scope}"] ${selector}`)
}

/**
 * 作用域内取元素文本。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
function textOf(scope: string, selector: string): string {
  return q(scope, selector)?.textContent ?? ''
}

/** 等待渲染与微任务结算。 */
async function settle(): Promise<void> {
  await new Promise((resolve) => setTimeout(resolve, 0))
  await nextTick()
}

/**
 * 点击作用域内元素（不存在时跳过）。
 *
 * @param scope 作用域。
 * @param selector 选择器。
 */
async function click(scope: string, selector: string): Promise<void> {
  const target = q(scope, selector)
  if (target instanceof HTMLElement) {
    target.click()
    await settle()
  }
}

/**
 * 勾选 / 取消勾选树节点（受控：直接触发 change 事件）。
 *
 * @param scope 作用域。
 * @param key 节点键。
 */
async function toggleNode(scope: string, key: string): Promise<void> {
  const input = q(scope, `[data-test="node-check-${key}"]`)
  if (input instanceof HTMLInputElement) {
    input.click()
    await settle()
  }
}

/** 运行自检并上屏。 */
async function runChecks(): Promise<void> {
  const result: { label: string; pass: boolean }[] = []

  result.push({
    label: '① 未就绪占位：降级提示 + 不渲染页签 + 零请求',
    pass:
      q('placeholder', '[data-test="placeholder"]') !== null &&
      q('placeholder', '[data-test="tabs"]') === null &&
      placeholderLoadCalls.value === 0,
  })

  result.push({
    label: '② 四类页签装配（权限树 / 字段权限 / 数据范围 / 主体绑定）',
    pass:
      q('main', '[data-test="tab-tree"]') !== null &&
      q('main', '[data-test="tab-field"]') !== null &&
      q('main', '[data-test="tab-scope"]') !== null &&
      q('main', '[data-test="tab-subject"]') !== null,
  })

  await click('main', '[data-test="tab-field"]')
  const fieldRendered = q('main', '[data-test="panel-field"]') !== null
  await click('main', '[data-test="tab-tree"]')
  result.push({
    label: '③ 页签切换（切字段权限后挂载矩阵件）',
    pass: fieldRendered,
  })

  result.push({
    label: '④ 隐含推导只读标识（业务权限展示「推导」且无勾选入口）',
    pass:
      textOf('main', '[data-test="node-biz:user"] [data-test="derived"]') === '推导' &&
      (q('main', '[data-test="node-check-biz:user"]') as HTMLInputElement | null)?.disabled === true,
  })

  await toggleNode('main', 'form:user')
  result.push({
    label: '⑤ 三态半选（勾选表单后菜单半选）',
    pass: q('main', '[data-test="node-menu:user"]')?.getAttribute('data-state') === 'indeterminate',
  })

  await toggleNode('main', 'menu:user')
  result.push({
    label: '⑥ 动作默认全无（菜单勾选不联动动作）',
    pass:
      q('main', '[data-test="node-form:user"]')?.getAttribute('data-state') === 'checked' &&
      q('main', '[data-test="node-act:user:create"]')?.getAttribute('data-state') === 'unchecked',
  })

  await toggleNode('main', 'menu:user')
  result.push({
    label: '⑦ 取消菜单连带取消表单与动作',
    pass:
      q('main', '[data-test="node-form:user"]')?.getAttribute('data-state') === 'unchecked' &&
      q('main', '[data-test="node-act:user:create"]')?.getAttribute('data-state') === 'unchecked',
  })

  result.push({
    label: '⑧ 挂接缺失标记与禁用',
    pass:
      textOf('main', '[data-test="node-menu:orphan"] [data-test="detached"]') === '未挂接' &&
      (q('main', '[data-test="node-check-menu:orphan"]') as HTMLInputElement | null)?.disabled === true,
  })

  await click('main', '[data-test="tab-field"]')
  await click('main', '[data-test="field-form:user-salary"] input')
  result.push({
    label: '⑨ 字段权限默认全开与收窄（勾选后置为不可见）',
    pass:
      q('main', '[data-test="field-form:user-salary"] [data-test="field-perm-cell"]')?.getAttribute('data-visible') ===
        'false' && q('main', '[data-test="field-form:user-name"] [data-test="field-perm-cell"]') !== null,
  })

  await click('main', '[data-test="tab-scope"]')
  await click('main', '[data-test="scope-template-self"]')
  await settle()
  result.push({
    label: '⑩ 数据范围默认无与模板套用（仅本人）',
    pass: textOf('main', '[data-test="scope-summary"]').includes('created_by = @current_user'),
  })

  await click('main', '[data-test="tab-subject"]')
  await click('main', '[data-test="candidate-u1"] button')
  await click('main', '[data-test="candidate-u2"] button')
  result.push({
    label: '⑪ 主体绑定与上限提示（绑定 2 个达上限）',
    pass: textOf('main', '[data-test="subject-u1"]') === '张三' && q('main', '[data-test="subject-limit"]') !== null,
  })

  const beforeSave = submittedKeys.length
  await configRef.value?.save()
  await configRef.value?.save()
  await settle()
  failNext = true
  await configRef.value?.save()
  await settle()
  result.push({
    label: '⑫ 提交幂等 + 上下文刷新 + 错误码定位',
    pass:
      submittedKeys[beforeSave] === submittedKeys[beforeSave + 1] &&
      access.codes.includes('user:create') &&
      textOf('main', '[data-test="error-target"]').includes('scope'),
  })

  checks.value = result
}

onMounted(async () => {
  await nextTick()
  await settle()
  await runChecks()
})
</script>

<template>
  <main class="perm-check">
    <h1>开发态核对 · 权限配置（08_04_02）</h1>
    <p class="perm-check__note">
      授权总容器（四类页签 / 隐含推导 / 三态 / 全量覆盖提交与上下文刷新）、五件组件与占位语义；本页仅供开发态核对，
      `vite build` 不包含。
    </p>

    <section class="perm-check__section" data-check-scope="main">
      <h2>授权总容器（注入取数 / 提交 / 权限码取数）</h2>
      <PermissionConfig
        ref="configRef"
        :ready="true"
        :tab="tab"
        role-id="r1"
        :jobs="jobs"
        :access="access"
        :subject-candidates="candidates"
        :subject-limit="2"
        :scope-variables="scopeVariables"
        :scope-fields="scopeFields"
        :scope-templates="scopeTemplates"
        @update:tab="tab = $event"
      />
    </section>

    <section class="perm-check__section" data-check-scope="placeholder">
      <h2>占位（未就绪：降级 + 禁用 + 零请求）</h2>
      <PermissionConfig :ready="false" :jobs="placeholderJobs" />
    </section>

    <section class="perm-check__section">
      <h2>单独复用权限树</h2>
      <PermissionTree :nodes="snapshot.nodes" />
    </section>

    <section class="perm-check__section">
      <h2>单独复用字段权限矩阵</h2>
      <FieldPermMatrix :rows="fieldRows" />
    </section>

    <section class="perm-check__section">
      <h2>单独复用数据范围件</h2>
      <DataScopePanel :rows="scopeRows" :variables="scopeVariables" :fields="scopeFields" :templates="scopeTemplates" />
    </section>

    <section class="perm-check__section">
      <h2>单独复用主体绑定件</h2>
      <SubjectBinding :subjects="snapshot.subjects" :candidates="candidates" :limit="20" />
    </section>

    <section class="perm-check__section">
      <h2>自检（12 项）</h2>
      <button type="button" data-test="rerun" @click="runChecks">重新自检</button>
      <ol class="perm-check__list">
        <li v-for="item in checks" :key="item.label" :data-pass="item.pass ? 'true' : 'false'" :data-check="item.label">
          {{ item.pass ? '通过' : '未通过' }} · {{ item.label }}
        </li>
      </ol>
    </section>
  </main>
</template>

<style scoped>
.perm-check {
  padding: 16px;
  font-family: var(--bms-font-family);
  color: var(--bms-color-text);
}

.perm-check__note {
  color: var(--bms-color-text-secondary);
}

.perm-check__section {
  margin-bottom: 24px;
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
  padding: 12px;
}

.perm-check__list {
  padding-left: 20px;
}

.perm-check__list li[data-pass='false'] {
  color: var(--bms-color-danger);
}
</style>
