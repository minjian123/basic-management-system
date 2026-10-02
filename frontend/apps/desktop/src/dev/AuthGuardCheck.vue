<script setup lang="ts">
// 开发态核对页（05_03 路由守卫）：五组自检程序化跑一遍并上屏；本页不进构建产物。
import {
  DEFAULT_FORBIDDEN_PATH,
  DEFAULT_HOME_PATH,
  DEFAULT_LOGIN_PATH,
  DEFAULT_PUBLIC_PATHS,
  buildLoginLocation,
  isPublicPath,
  resolveAuthGuard,
  resolveSafeRedirect,
} from '@bms/core'
import { computed } from 'vue'

import { DEV_PUBLIC_PATHS, isAuthGuardEnabled, resolvePublicPaths } from '@/router/guard'

/** 自检项。 */
interface CheckItem {
  /** 序号。 */
  no: number
  /** 说明。 */
  label: string
  /** 是否通过。 */
  ok: boolean
}

/** 自检分组。 */
interface CheckGroup {
  /** 分组标题。 */
  title: string
  /** 分组自检项。 */
  items: CheckItem[]
}

/** 判定结果快照（便于人工核对）。 */
const decisionLogin = resolveAuthGuard({ hasToken: false, path: '/org/users' })
const decisionPublic = resolveAuthGuard({ hasToken: false, path: '/500' })
const decisionPublicRoute = resolveAuthGuard({ hasToken: false, path: '/sso/callback', isPublicRoute: true })
const locationProtected = buildLoginLocation('/org/users?page=2#row-3')
const locationPublic = buildLoginLocation('/500')
const safeInternal = resolveSafeRedirect('/org/users?page=2#row-3')
const safeExternal = resolveSafeRedirect('https://evil.example.com/x')
const safeProtocolRelative = resolveSafeRedirect('//evil.example.com')
const safeScript = resolveSafeRedirect('javascript:alert(1)')
const safeBackslash = resolveSafeRedirect('/org\\users')
const safeControl = resolveSafeRedirect('/org\u0000users')
const safeEmpty = resolveSafeRedirect('')
const safeNonString = resolveSafeRedirect({ path: '/org/users' })
const safePublic = resolveSafeRedirect('/login?redirect=/x')
const permUndeclared = resolveAuthGuard({ hasToken: true, path: '/org/users' })
const permNotLoaded = resolveAuthGuard({
  hasToken: true,
  path: '/org/users',
  requiredPermissions: ['user:query'],
  permissionsLoaded: false,
})
const permGranted = resolveAuthGuard({
  hasToken: true,
  path: '/org/users',
  requiredPermissions: ['user:query'],
  permissions: ['user:query'],
  permissionsLoaded: true,
})
const permDenied = resolveAuthGuard({
  hasToken: true,
  path: '/org/users',
  requiredPermissions: ['user:query'],
  permissions: ['user:edit'],
  permissionsLoaded: true,
})
const devPublicPaths = resolvePublicPaths(true)
const prodPublicPaths = resolvePublicPaths(false)

/** 自检分组清单。 */
const groups = computed<CheckGroup[]>(() => {
  let no = 0
  const next = (label: string, ok: boolean): CheckItem => {
    no += 1
    return { no, label, ok }
  }
  return [
    {
      title: '一、拦截与回跳',
      items: [
        next(`无令牌访问受保护路径 /org/users → 决策 login（实得 ${decisionLogin}）`, decisionLogin === 'login'),
        next(
          `跳登录带 redirect（实得 ${locationProtected.path} · redirect=${locationProtected.query?.redirect ?? '无'}）`,
          locationProtected.path === DEFAULT_LOGIN_PATH && locationProtected.query?.redirect === '/org/users?page=2#row-3',
        ),
        next(
          `公开路径 ${locationPublic.path} 跳登录不回带 redirect`,
          locationPublic.path === DEFAULT_LOGIN_PATH && locationPublic.query === undefined,
        ),
        next(`公开页 /500 → 决策 allow（实得 ${decisionPublic}）`, decisionPublic === 'allow'),
      ],
    },
    {
      title: '二、白名单放行',
      items: [
        next(
          `核心常量逐项放行（${DEFAULT_PUBLIC_PATHS.join(' / ')}）`,
          DEFAULT_PUBLIC_PATHS.every((path) => isPublicPath(path)),
        ),
        next('子路径放行（/login/callback）', isPublicPath('/login/callback')),
        next('同段前缀不误伤（/loginfo 不受拦）', !isPublicPath('/loginfo')),
        next(`路由声明公开页（meta.public）放行（实得 ${decisionPublicRoute}）`, decisionPublicRoute === 'allow'),
      ],
    },
    {
      title: '三、回跳安全校验（站内）',
      items: [
        next(`站内相对路径原样（含查询串与片段，实得 ${safeInternal}）`, safeInternal === '/org/users?page=2#row-3'),
        next(
          `外链 / 协议相对 / 危险协议回落首页（${safeExternal} / ${safeProtocolRelative} / ${safeScript}）`,
          safeExternal === DEFAULT_HOME_PATH && safeProtocolRelative === DEFAULT_HOME_PATH && safeScript === DEFAULT_HOME_PATH,
        ),
        next(
          `反斜杠 / 控制字符回落首页（${safeBackslash} / ${safeControl}）`,
          safeBackslash === DEFAULT_HOME_PATH && safeControl === DEFAULT_HOME_PATH,
        ),
        next(
          `空值 / 非字符串回落首页（${safeEmpty} / ${safeNonString}）`,
          safeEmpty === DEFAULT_HOME_PATH && safeNonString === DEFAULT_HOME_PATH,
        ),
        next(
          `命中公开白名单回落首页（${safePublic}，防回跳循环）`,
          safePublic === DEFAULT_HOME_PATH,
        ),
      ],
    },
    {
      title: '四、权限占位（RBAC 就绪前）',
      items: [
        next(`未声明 meta.perm → 放行（实得 ${permUndeclared}）`, permUndeclared === 'allow'),
        next(`声明但权限未装载 → 占位放行（实得 ${permNotLoaded}）`, permNotLoaded === 'allow'),
        next(`已装载且满足 → 放行（实得 ${permGranted}）`, permGranted === 'allow'),
        next(
          `已装载且不满足 → 跳 ${DEFAULT_FORBIDDEN_PATH}（实得 ${permDenied}）`,
          permDenied === 'forbidden' && DEFAULT_FORBIDDEN_PATH === '/403',
        ),
      ],
    },
    {
      title: '五、开关与 DEV 白名单',
      items: [
        next(`守卫缺省开启（VITE_AUTH_GUARD 未设 off，实得 ${String(isAuthGuardEnabled())}）`, isAuthGuardEnabled()),
        next(
          `DEV 白名单含观测面板（${DEV_PUBLIC_PATHS.join(' / ')}）`,
          DEV_PUBLIC_PATHS.every((path) => devPublicPaths.includes(path)),
        ),
        next(
          `生产白名单不含 DEV 路由（${prodPublicPaths.join(' / ')}）`,
          DEV_PUBLIC_PATHS.every((path) => !prodPublicPaths.includes(path)),
        ),
      ],
    },
  ]
})

/** 全部自检项。 */
const items = computed(() => groups.value.flatMap((group) => group.items))

/** 通过项数。 */
const passed = computed(() => items.value.filter((item) => item.ok).length)
</script>

<template>
  <main class="check-page">
    <h1>路由守卫核对页（05_03 路由守卫默认开启与登录回跳）</h1>

    <section>
      <h2>自检清单</h2>
      <p>
        共 {{ items.length }} 项，通过
        <strong data-check-passed>{{ passed }}</strong>
        项。
      </p>
      <div v-for="group in groups" :key="group.title">
        <h3>{{ group.title }}</h3>
        <ol class="check-list" :data-check-group="group.title">
          <li
            v-for="item in group.items"
            :key="item.no"
            :data-check="item.no"
            :data-ok="item.ok ? 'true' : 'false'"
          >
            第 {{ item.no }} 项 · {{ item.label }} —— {{ item.ok ? '通过' : '未通过' }}
          </li>
        </ol>
      </div>
    </section>

    <section>
      <h2>等待态说明（刷新不闪登录页）</h2>
      <ul class="check-list">
        <li>守卫在受保护路径与登录页判定前 <code>await</code> 单例会话就绪；续期期间导航挂起，不跳登录页。</li>
        <li>会话就绪前应用根渲染骨架屏（<code>data-test="app-skeleton"</code>），等待期间不白屏、不闪登录页。</li>
        <li>该体验由宿主用例锁定（<code>tests/auth-guard.spec.ts</code> 不闪登录页用例 + <code>tests/session-readiness.spec.ts</code> 单例续期用例）。</li>
      </ul>
    </section>

    <section>
      <h2>守卫接线口径</h2>
      <ul class="check-list">
        <li>判定纯函数落核心 <code>domain/route-guard</code>；跳登录构造与站内回跳校验共用同一来源。</li>
        <li>动态路由：会话就绪后幂等装载菜单路由，会话清理（登出 / 失效）时卸载；装载后按新路由表重解析当前地址。</li>
        <li>观测：每次判定记一条（决策 / 路径 / 原因），见开发态观测面板「守卫决策（平台）」区块。</li>
      </ul>
    </section>
  </main>
</template>

<style scoped>
.check-page {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-lg);
  padding: var(--bms-spacing-lg);
  font-family: var(--bms-font-family);
}

.check-page section {
  display: flex;
  flex-direction: column;
  gap: var(--bms-spacing-md);
}

.check-list {
  margin: 0;
  padding-left: var(--bms-spacing-lg);
}

.check-list [data-ok='false'] {
  color: var(--bms-color-danger);
}

.check-list [data-ok='true'] {
  color: var(--bms-color-success);
}
</style>
