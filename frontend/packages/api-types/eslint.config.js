import js from '@eslint/js'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { name: 'api-types/files-to-lint', files: ['**/*.{ts,mts}'] },
  // src/** 为生成产物（openapi-typescript 输出），不纳入人工 lint；零漂移由 gen:check 保证
  { name: 'api-types/files-to-ignore', ignores: ['src/**', '**/node_modules/**'] },
  {
    // 显式锚定 TS 配置根（monorepo 多包各一份配置，工具工作目录不确定时会报「多个候选 TSConfigRootDirs」）
    name: 'api-types/tsconfig-root',
    files: ['**/*.{ts,mts}'],
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    name: 'api-types/scripts-node-globals',
    files: ['scripts/**/*.mjs'],
    languageOptions: { globals: { process: 'readonly', console: 'readonly' } },
  },
  skipFormatting,
)
