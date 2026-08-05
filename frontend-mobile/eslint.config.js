import pluginVue from 'eslint-plugin-vue'
import eslintConfigPrettier from 'eslint-config-prettier'
import tsParser from '@typescript-eslint/parser'
import globals from 'globals'

export default [
  {
    ignores: ['dist/**', 'coverage/**', 'node_modules/**', 'src/components.d.ts'],
  },
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['**/*.{js,mjs,cjs,ts,vue}'],
    languageOptions: {
      globals: { ...globals.browser, ...globals.node },
      ecmaVersion: 'latest',
      sourceType: 'module',
    },
    rules: {
      // .ts / .vue 中 TS 类型引用由 vue-tsc 检查，此处关闭 no-undef 避免误报
      'no-undef': 'off',
      // 页面/组件文件名允许单词命名（如 Home.vue）
      'vue/multi-word-component-names': 'off',
      // Vant / vue-router 组件由 unplugin-vue-components 与 vue-router 全局注册
      'vue/no-undef-components': ['error', { ignorePatterns: ['van-*', 'router-*'] }],
    },
  },
  {
    files: ['**/*.ts'],
    languageOptions: {
      parser: tsParser,
    },
  },
  {
    files: ['**/*.vue'],
    languageOptions: {
      // <script lang="ts"> 交给 @typescript-eslint/parser 解析
      parserOptions: { parser: tsParser },
    },
  },
  eslintConfigPrettier,
]
