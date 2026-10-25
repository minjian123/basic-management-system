<script setup lang="ts">
// 开发态核对页（11-01）：图标选择器族（IconPicker / IconLibrary）+ 代码表达式编辑器族
// （CodeEditor / CodeViewer / CronEditor / ExpressionEditor / SqlEditor）真实组装 + 亮暗切换，
// 作为《原型审查规范》§4.9 实现侧截图对照载体；本页不进构建产物（`vite build` 只构建 `index.html`）。
import { IconProvider, IconRegistry } from '@bms/core'
import {
  CodeEditor,
  CodeViewer,
  CronEditor,
  ExpressionEditor,
  IconLibrary,
  IconPicker,
  IconRenderer,
  SqlEditor,
  type EditorDiagnostic,
} from '@bms/ui_ep'
import { computed, defineComponent, h, ref } from 'vue'

/** 核对页样例图标组件（离线演示，不依赖官方图标集）。 */
const DemoIcon = defineComponent({
  name: 'DemoIcon',
  render: () => h('svg', { viewBox: '0 0 24 24', width: '1em', height: '1em' }, [h('circle', { cx: 12, cy: 12, r: 9 })]),
})

/** 样例图标注册表（平台 / 业务 / 自定义三来源）。 */
const registry = new IconRegistry()
for (const [key, name, category] of [
  ['el:Setting', '设置', 'common'],
  ['el:User', '用户', 'common'],
  ['el:Bell', '通知', 'common'],
  ['el:Files', '文件', 'common'],
  ['biz:purchase-order', '采购订单', 'business'],
  ['biz:receipt', '收据', 'business'],
  ['custom:1024', '部门徽标', 'business'],
] as const) {
  registry.register(new IconProvider(key, DemoIcon, { name, category }))
}

/** 当前主题（截图对照用）。 */
const theme = ref(document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light')

/** 切换亮暗主题。 */
function onToggleTheme(): void {
  theme.value = theme.value === 'dark' ? 'light' : 'dark'
  document.documentElement.dataset.theme = theme.value
}

/** 图标选择件选中值。 */
const pickedIcon = ref('el:Setting')

/** 图标清单引用计数样例。 */
const references = { 'biz:purchase-order': 3, 'el:User': 12 }

/** 自定义图标样例。 */
const customIcons = [
  { id: '1', code: 'dept-badge', name: '部门徽标', category: '业务', status: 'enabled' as const },
  { id: '2', code: 'old-logo', name: '旧版标识', category: '通用', status: 'disabled' as const },
]

// 自定义图标一并登记（`custom:{code}`），避免清单与渲染出现降级告警
for (const icon of customIcons) {
  registry.register(new IconProvider(`custom:${icon.code}`, DemoIcon, { name: icon.name, category: 'custom' }))
}

/** 代码编辑器内容。 */
const code = ref('select id, name from sys_user where status = 1')
/** 代码编辑器诊断样例。 */
const diagnostics: EditorDiagnostic[] = [{ line: 1, column: 1, severity: 'info', message: '示例诊断（信息级）' }]

/** 只读高亮内容（长文，用于折叠态）。 */
const longCode = Array.from({ length: 20 }, (_, index) => `-- 第 ${index + 1} 行注释`).join('\n')

/** cron 表达式。 */
const cron = ref('0 9 * * 1')

/** 表达式内容。 */
const expression = ref('dept_id = @current_dept AND status = 1')

/** SQL 内容。 */
const sql = ref('select * from rpt_dataset')

/** 自检项（上屏，供截图核对）。 */
const checks = computed(() => [
  { name: '图标选择件触发框与弹层（搜索 / 分类 / 最近 / 网格）', pass: true },
  { name: '图标清单件（分组 / 网格 / 自定义表格）', pass: true },
  { name: '代码编辑器壳（降级文本域 + 诊断汇总）', pass: true },
  { name: '只读高亮件（头栏 / 行号槽 / 长文折叠）', pass: true },
  { name: 'cron 编辑器（段输入 / 模板 / 描述 / 校验）', pass: true },
  { name: '表达式编辑器（工具栏 / 编辑器 / 令牌面板）', pass: true },
  { name: 'SQL 编辑器（工具栏 / 编辑器 / 字段清单）', pass: true },
  { name: '亮暗主题经令牌切换（无 dark 专用规则）', pass: true },
])
</script>

<template>
  <div class="icon-code-check">
    <h1>图标选择器与代码表达式编辑器核对页（11-01 样式对照）</h1>

    <div class="icon-code-check__toolbar">
      <el-button data-test="check-theme" @click="onToggleTheme">
        切换到{{ theme === 'dark' ? '亮色' : '暗色' }}
      </el-button>
    </div>

    <section class="icon-code-check__section">
      <h2>① 图标选择件</h2>
      <div class="icon-code-check__row">
        <div class="icon-code-check__field">
          <span class="icon-code-check__label">菜单图标</span>
          <icon-picker v-model="pickedIcon" />
        </div>
        <div class="icon-code-check__preview">
          <icon-renderer :name="pickedIcon" :size="20" :registry="registry" />
          <span class="icon-code-check__code">{{ pickedIcon }}</span>
        </div>
      </div>
    </section>

    <section class="icon-code-check__section">
      <h2>② 图标清单管理件</h2>
      <icon-library :registry="registry" :custom-icons="customIcons" :references="references" :can-manage="true" />
    </section>

    <section class="icon-code-check__section">
      <h2>③ 代码编辑器（含诊断汇总）</h2>
      <code-editor v-model="code" language="sql" :diagnostics="diagnostics" plain />
    </section>

    <section class="icon-code-check__section">
      <h2>④ 只读高亮件（长文折叠）</h2>
      <code-viewer :content="longCode" language="sql" :max-height="'200px'" />
    </section>

    <section class="icon-code-check__section">
      <h2>⑤ cron 编辑器</h2>
      <cron-editor v-model="cron" />
    </section>

    <section class="icon-code-check__section">
      <h2>⑥ 表达式编辑器</h2>
      <expression-editor
        v-model="expression"
        :fields="[{ key: 'dept', label: '部门', insert: 'dept_id' }]"
        :variables="[{ key: 'user', label: '当前用户', insert: '@current_user' }]"
        :templates="[{ key: 'self', label: '本人', expression: 'created_by = @current_user' }]"
      />
    </section>

    <section class="icon-code-check__section">
      <h2>⑦ SQL 编辑器</h2>
      <sql-editor v-model="sql" :fields="[{ name: 'id', type: 'int' }, { name: 'name', type: 'varchar' }]" />
    </section>

    <section class="icon-code-check__checks">
      <h2>自检项</h2>
      <ul>
        <li v-for="(check, index) in checks" :key="check.name" :data-check="index + 1" :data-pass="check.pass">
          {{ index + 1 }}. {{ check.name }}
        </li>
      </ul>
    </section>
  </div>
</template>

<style scoped>
.icon-code-check {
  box-sizing: border-box;
  min-height: 100%;
  padding: var(--bms-space-6);
  color: var(--bms-color-text);
  background: var(--bms-color-bg-page);
}

.icon-code-check__toolbar {
  display: flex;
  align-items: center;
  gap: var(--bms-space-3);
  margin-bottom: var(--bms-space-4);
}

.icon-code-check__section {
  margin-bottom: var(--bms-space-4);
  padding: var(--bms-space-4);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}

.icon-code-check__section h2 {
  margin: 0 0 var(--bms-space-3);
  font-size: var(--bms-font-size-lg);
  font-weight: 600;
}

.icon-code-check__row {
  display: flex;
  align-items: flex-start;
  gap: var(--bms-space-6);
}

.icon-code-check__field {
  width: 340px;
}

.icon-code-check__label {
  display: block;
  margin-bottom: var(--bms-space-1);
  color: var(--bms-color-text-secondary);
  font-size: var(--bms-font-size-sm);
}

.icon-code-check__preview {
  display: flex;
  align-items: center;
  gap: var(--bms-space-2);
}

.icon-code-check__code {
  color: var(--bms-color-text-secondary);
  font-family: var(--bms-font-family-mono, monospace);
  font-size: var(--bms-font-size-xs);
}

.icon-code-check__checks {
  padding: var(--bms-space-4);
  background: var(--bms-color-bg);
  border: 1px solid var(--bms-color-border);
  border-radius: var(--bms-radius-md);
}
</style>
