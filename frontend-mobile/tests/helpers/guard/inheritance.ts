/**
 * 继承护栏扫描（纯函数，可注入 fixture）：
 * 基类链 / 片段声明 / 域基类组合面 / 组件包装（AST）。
 */

import { callInfos, classInfos, parseTs, scriptOf, type GuardFile, type GuardProblem } from './ast'

/** 机制层类的期望父类（`undefined` 表示不得有父类） */
const BASE_PARENTS: Record<string, string | undefined> = {
  BaseFrontend: undefined,
  BaseComponent: 'BaseFrontend',
  BaseCapability: 'BaseComponent',
  BasePlaceholder: 'BaseComponent',
  BaseAsyncResource: 'BaseComponent',
  BaseRegistry: 'BaseComponent',
  BaseSubscription: 'BaseComponent',
  BaseError: 'Error',
}

/** 域基类包装 → 同域组合式 */
const DOMAIN_WRAPPERS: Record<string, string> = {
  'BaseInput.vue': 'useInputBase',
  'BaseDisplay.vue': 'useDisplayBase',
  'BaseTree.vue': 'useTreeBase',
  'BaseEditor.vue': 'useEditorBase',
}

/** 非片段的 `useXxx` 文件（上下文机制等，不要求 `declareFragment`） */
const DEFAULT_NON_FRAGMENTS = ['useFieldContext.ts']

/**
 * 扫描继承护栏：
 * ① `src/base/*.ts` 机制层类父类链；② 片段实现 `declareFragment('key')`；
 * ③ 域基类组合式（组合面齐备、不声明片段）；④ `BaseXxx.vue` 包装调用组件根与域组合式。
 */
export function scanInheritance(
  files: GuardFile[],
  fragmentKeys: string[],
  nonFragmentFiles: string[] = DEFAULT_NON_FRAGMENTS,
): GuardProblem[] {
  const problems: GuardProblem[] = []
  for (const file of files) {
    const source = parseTs(scriptOf(file), file.path)
    const classes = classInfos(source)
    const calls = callInfos(source)
    const fileName = file.path.split('/').pop() ?? ''

    if (file.path.startsWith('src/base/') && file.path.endsWith('.ts')) {
      for (const info of classes) {
        if (!(info.name in BASE_PARENTS)) {
          continue
        }
        const expected = BASE_PARENTS[info.name]
        if (expected === undefined) {
          if (info.base) {
            problems.push({
              file: file.path,
              rule: 'inheritance.base-parent',
              message: `${info.name} 不应继承 ${info.base}`,
            })
          }
        } else if (info.base !== expected) {
          problems.push({
            file: file.path,
            rule: 'inheritance.base-parent',
            message: `${info.name} 应继承 ${expected}，实际 ${info.base ?? '无父类'}`,
          })
        }
      }
    }

    if (file.path.startsWith('src/components/base/') && file.path.endsWith('.ts') && /^use[A-Z]/.test(fileName)) {
      const self = fileName.replace(/\.ts$/, '')
      const declared = calls.filter((call) => call.name === 'declareFragment' || call.name === 'useCapabilityBase')
      if (/Base$/.test(self)) {
        const composed = calls.filter((call) => /^use[A-Z]/.test(call.name) && call.name !== self)
        if (declared.length > 0) {
          problems.push({
            file: file.path,
            rule: 'inheritance.domain-declare',
            message: `${self} 是域基类组合式，不应声明片段`,
          })
        }
        if (composed.length === 0) {
          problems.push({
            file: file.path,
            rule: 'inheritance.domain-compose',
            message: `${self} 应组合至少一个片段或上下文机制`,
          })
        }
      } else if (!nonFragmentFiles.includes(fileName)) {
        const declaration = declared.find((call) => call.name === 'declareFragment')
        if (!declaration || !declaration.firstString) {
          problems.push({
            file: file.path,
            rule: 'inheritance.fragment-declare',
            message: `${fileName} 缺少 declareFragment('key') 声明`,
          })
        } else if (!fragmentKeys.includes(declaration.firstString)) {
          problems.push({
            file: file.path,
            rule: 'inheritance.fragment-declare',
            message: `片段 key「${declaration.firstString}」不在 fragments.ts 登记表内`,
          })
        }
      }
    }

    if (file.path.endsWith('.vue')) {
      const expectedComposable = DOMAIN_WRAPPERS[fileName]
      if (expectedComposable) {
        if (!calls.some((call) => call.name === 'useComponentBase')) {
          problems.push({
            file: file.path,
            rule: 'inheritance.wrapper-root',
            message: `${fileName} 必须调用 useComponentBase（组件根）`,
          })
        }
        if (!calls.some((call) => call.name === expectedComposable)) {
          problems.push({
            file: file.path,
            rule: 'inheritance.wrapper-domain',
            message: `${fileName} 必须调用 ${expectedComposable}`,
          })
        }
      }
    }
  }
  return problems
}
