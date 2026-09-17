/** 护栏 AST 辅助：SFC / TS 解析（零新依赖：`@vue/compiler-sfc` + `typescript`）。 */

import { parse as parseSfc } from '@vue/compiler-sfc'
import * as ts from 'typescript'

/** 护栏扫描的文件（相对仓库根路径 + 源码） */
export interface GuardFile {
  path: string
  source: string
}

/** 护栏问题（违规输出） */
export interface GuardProblem {
  file: string
  rule: string
  message: string
}

/** 取文件脚本源码：SFC 合并 `script` / `scriptSetup`；其余原样返回 */
export function scriptOf(file: GuardFile): string {
  if (!file.path.endsWith('.vue')) {
    return file.source
  }
  const { descriptor } = parseSfc(file.source, { filename: file.path })
  return [descriptor.script?.content ?? '', descriptor.scriptSetup?.content ?? ''].join('\n')
}

/** 解析为 TypeScript SourceFile */
export function parseTs(source: string, fileName: string): ts.SourceFile {
  return ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
}

/** 深度优先访问全部节点 */
export function visit(node: ts.Node, visitFn: (node: ts.Node) => void): void {
  visitFn(node)
  node.forEachChild((child) => {
    visit(child, visitFn)
  })
}

/** 类声明信息：名称与父类名（无父类为 `undefined`） */
export interface ClassInfo {
  name: string
  base: string | undefined
}

/** 收集类声明（名称 + `extends` 父类标识符） */
export function classInfos(sourceFile: ts.SourceFile): ClassInfo[] {
  const result: ClassInfo[] = []
  visit(sourceFile, (node) => {
    if (!ts.isClassDeclaration(node) || !node.name) {
      return
    }
    const heritage = node.heritageClauses?.find((clause) => clause.token === ts.SyntaxKind.ExtendsKeyword)
    const base = heritage?.types[0]?.expression.getText(sourceFile)
    result.push({ name: node.name.text, base })
  })
  return result
}

/** 调用表达式信息：调用名与首个字符串字面量参数 */
export interface CallInfo {
  name: string
  firstString: string | undefined
}

/** 收集调用表达式（`foo(...)` / `obj.foo(...)`；首个字符串字面量参数） */
export function callInfos(sourceFile: ts.SourceFile): CallInfo[] {
  const result: CallInfo[] = []
  visit(sourceFile, (node) => {
    if (!ts.isCallExpression(node)) {
      return
    }
    const expression = node.expression
    const name = ts.isIdentifier(expression)
      ? expression.text
      : ts.isPropertyAccessExpression(expression)
        ? expression.name.text
        : undefined
    if (!name) {
      return
    }
    const first = node.arguments[0]
    const firstString = first && ts.isStringLiteralLike(first) ? first.text : undefined
    result.push({ name, firstString })
  })
  return result
}

/** 收集静态 import 说明符（`import ... from '...'`） */
export function importSpecifiers(sourceFile: ts.SourceFile): string[] {
  const result: string[] = []
  visit(sourceFile, (node) => {
    if (ts.isImportDeclaration(node) && ts.isStringLiteralLike(node.moduleSpecifier)) {
      result.push(node.moduleSpecifier.text)
    }
  })
  return result
}
