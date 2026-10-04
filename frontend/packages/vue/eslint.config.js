import js from '@eslint/js'
import skipFormatting from '@vue/eslint-config-prettier/skip-formatting'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  { name: 'vue/files-to-lint', files: ['**/*.{ts,mts}'] },
  { name: 'vue/files-to-ignore', ignores: ['**/coverage/**', '**/node_modules/**'] },
  {
    // 显式锚定 TS 配置根（monorepo 多包各一份配置，工具工作目录不确定时会报「多个候选 TSConfigRootDirs」）
    name: 'vue/tsconfig-root',
    files: ['**/*.{ts,mts}'],
    languageOptions: { parserOptions: { tsconfigRootDir: import.meta.dirname } },
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  skipFormatting,
)
