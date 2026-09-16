/** 继承护栏用例（Kiwi 713）：基类链 / 组件包装 / 片段声明（AST，双端同款）。 */

import { describe, expect, it } from 'vitest'

import { scanInheritance } from './helpers/guard/inheritance'
import { buildRepoIndex } from './helpers/guard/repo'

const repo = buildRepoIndex()

describe('继承护栏（Kiwi 713）', () => {
  it('① 机制层基类链全绿（src/base）', () => {
    const problems = scanInheritance(
      repo.files.filter((file) => file.path.startsWith('src/base/')),
      repo.fragmentKeys,
    )
    expect(problems).toEqual([])
  })

  it('② 片段声明与域基类组合面全绿（src/components/base）', () => {
    const problems = scanInheritance(
      repo.files.filter((file) => file.path.startsWith('src/components/base/')),
      repo.fragmentKeys,
    )
    expect(problems).toEqual([])
  })

  it('③ 组件包装调用组件根与域组合式全绿（BaseXxx.vue）', () => {
    const problems = scanInheritance(
      repo.files.filter((file) => file.path.endsWith('.vue')),
      repo.fragmentKeys,
    )
    expect(problems).toEqual([])
  })

  it('④ 违规继承 / 未声明片段 / 包装缺调用 fixture 被拦截', () => {
    const problems = scanInheritance(
      [
        { path: 'src/base/probe.ts', source: 'export class BaseComponent extends Object {}' },
        {
          path: 'src/components/base/probe/useProbe.ts',
          source: 'export function useProbe() {\n  return 1\n}',
        },
        {
          path: 'src/components/base/input/BaseInput.vue',
          source: '<script setup lang="ts">\nconst base = 1\n</script>\n<template><div /></template>\n',
        },
      ],
      repo.fragmentKeys,
    )
    const rules = problems.map((problem) => problem.rule)
    expect(rules).toContain('inheritance.base-parent')
    expect(rules).toContain('inheritance.fragment-declare')
    expect(rules).toContain('inheritance.wrapper-root')
    expect(rules).toContain('inheritance.wrapper-domain')
  })

  it('⑤ 未登记片段 key 与域组合式缺组合面 fixture 被拦截', () => {
    const problems = scanInheritance(
      [
        {
          path: 'src/components/base/probe/useProbe.ts',
          source:
            "import { declareFragment } from '../fragments'\nexport function useProbe() {\n  declareFragment('ghost')\n}",
        },
        {
          path: 'src/components/base/probe/useProbeBase.ts',
          source: 'export function useProbeBase() {\n  return 1\n}',
        },
      ],
      repo.fragmentKeys,
    )
    const rules = problems.map((problem) => problem.rule)
    expect(rules).toContain('inheritance.fragment-declare')
    expect(rules).toContain('inheritance.domain-compose')
  })

  it('⑥ 问题结构稳定（文件 / 规则 / 说明齐备）', () => {
    const [problem] = scanInheritance(
      [{ path: 'src/base/probe.ts', source: 'export class BaseComponent extends Object {}' }],
      repo.fragmentKeys,
    )
    expect(problem).toMatchObject({
      file: 'src/base/probe.ts',
      rule: 'inheritance.base-parent',
    })
    expect(problem?.message).toContain('BaseComponent')
  })
})
