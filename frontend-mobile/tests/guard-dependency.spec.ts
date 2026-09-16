/** 依赖边界用例（Kiwi 714）：反向依赖 / UI 库 / 片段单向与循环 / 横切库（双端同款）。 */

import { describe, expect, it } from 'vitest'

import { scanDependency } from './helpers/guard/dependency'
import { buildRepoIndex } from './helpers/guard/repo'

const repo = buildRepoIndex()

describe('依赖边界（Kiwi 714）', () => {
  it('① 机制层 / 基类层依赖全绿（当前仓库）', () => {
    expect(scanDependency(repo.files, repo.fragmentDepends)).toEqual([])
  })

  it('② 片段依赖图无环（depends 权威表）', () => {
    expect(scanDependency([], repo.fragmentDepends)).toEqual([])
  })

  it('③ 反向依赖 fixture 被拦截（机制层 import 片段层）', () => {
    const problems = scanDependency([
      {
        path: 'src/base/probe.ts',
        source: "import { BaseInput } from '@/components/base/input'\nexport const probe = BaseInput",
      },
    ])
    expect(problems.map((problem) => problem.rule)).toContain('dependency.reverse-components')
  })

  it('④ UI 库与上层目录 fixture 被拦截', () => {
    const problems = scanDependency([
      {
        path: 'src/components/base/probe/useProbe.ts',
        source: "import 'element-plus'\nexport function useProbe() {\n  return 1\n}",
      },
      {
        path: 'src/components/base/probe/BaseProbe.vue',
        source:
          '<script setup lang="ts">\nimport HomeView from "@/views/home/HomeView.vue"\nconst view = HomeView\n</script>\n<template><div /></template>\n',
      },
    ])
    const rules = problems.map((problem) => problem.rule)
    expect(rules).toContain('dependency.ui-lib')
    expect(rules).toContain('dependency.upper-layer')
  })

  it('⑤ 未登记片段依赖与循环 fixture 被拦截', () => {
    const unregistered = scanDependency(
      [
        {
          path: 'src/components/base/probe/useProbe.ts',
          source: "import { useValue } from '../value/useValue'\nexport function useProbe() {\n  return useValue\n}",
        },
      ],
      repo.fragmentDepends,
    )
    expect(unregistered.map((problem) => problem.rule)).toContain('dependency.fragment-unregistered')

    const cyclic = scanDependency([], { alpha: ['beta'], beta: ['alpha'] })
    expect(cyclic.map((problem) => problem.rule)).toContain('dependency.fragment-cycle')
  })

  it('⑥ 横切库重复实现 fixture 被拦截', () => {
    const problems = scanDependency([
      {
        path: 'src/components/base/probe/useProbe.ts',
        source: "import axios from 'axios'\nexport const probe = axios",
      },
    ])
    expect(problems.map((problem) => problem.rule)).toContain('dependency.cross-lib')
  })
})
