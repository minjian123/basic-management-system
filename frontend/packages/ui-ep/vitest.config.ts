import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

export default defineConfig({
  plugins: [vue()],
  test: {
    environment: 'jsdom',
    // 交互用例（jsdom + Element Plus 过渡）在 CI 容器负载下会逼近缺省 5s 上限（2026-10-18 两次实测超时）
    // ⇒ 包级放宽到 20s（通过用例不受影响，仅在真挂起时晚一点失败）
    testTimeout: 20_000,
    include: ['tests/**/*.spec.ts'],
    server: {
      deps: {
        inline: ['element-plus'],
      },
    },
  },
})
