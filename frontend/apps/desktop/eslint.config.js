import js from '@eslint/js'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { name: 'app/files-to-lint', files: ['**/*.{ts,mts,tsx,vue}'] },
  {
    name: 'app/files-to-ignore',
    // `@mf-types`：Module Federation 生成的远端类型声明（已 gitignore、随构建再生）——不参与 lint，
    // 否则「构建过运行时模块」的本地工作区会因生成物内的 `any` 直接 lint 失败（与 CI 空检出不一致）。
    ignores: ['**/dist/**', '**/coverage/**', '**/node_modules/**', '**/@mf-types/**'],
  },
  {
    // 显式锚定 TS 配置根：monorepo（宿主 / 组件库 / 运行时模块各一份配置）下工具工作目录不确定
    // （IDE ESLint 扩展未指定 workingDirectories、或从仓库根起跑）时，解析器会因「多个候选
    // TSConfigRootDirs」直接报解析错误；锚到本配置所在目录 = 本包唯一根（与 `.vscode/settings.json`
    // 的 `eslint.workingDirectories: [{ mode: 'auto' }]` 双保险）。
    name: 'app/tsconfig-root',
    files: ['**/*.{ts,mts,tsx,vue}'],
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    name: 'app/vue-parser',
    files: ['**/*.vue'],
    languageOptions: { parserOptions: { parser: tseslint.parser } },
  },
  {
    name: 'app/vue-no-undef',
    files: ['**/*.vue'],
    rules: { 'no-undef': 'off' },
  },
  {
    name: 'app/tests',
    files: ['tests/**/*.{ts,mts,tsx}'],
    rules: { 'vue/one-component-per-file': 'off' },
  },
  {
    name: 'app/node-scripts',
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: { console: 'readonly', URL: 'readonly' } },
  },
  skipFormatting,
)
