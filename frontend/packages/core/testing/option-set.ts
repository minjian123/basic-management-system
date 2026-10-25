/**
 * 选项集解析器契约（`@bms/core/testing`）。
 *
 * 选项集随表单元数据下发、运行期只读、零请求；各端（PC `ui-ep` / 移动端 `ui_vant` / 自定义实现）
 * 把各自的解析器传入本套件跑同一套断言——「同接口多实现」的机器保障。
 *
 * 契约面为结构化接口（非具体基类）：`resolve(optionSetKey)` 返回**解析后**条目
 * （`sort` 升序 → `value` 去重保留首个 → `labelKey` 翻译、缺翻译回退 `label`）。
 */

import { describe, expect, it } from 'vitest'

import type { OptionSetItem, OptionSetSnapshot } from '../src'

/** 契约快照：一组乱序 + 重复值 + labelKey 的选项集。 */
export const OPTION_SET_CONTRACT_SNAPSHOTS: readonly OptionSetSnapshot[] = [
  {
    optionSetKey: 'bms.demo.level',
    items: [
      { value: 'high', label: '高', sort: 3, color: 'danger' },
      { value: 'low', label: '低', sort: 1, disabled: true },
      { value: 'high', label: '高（重复）', sort: 4 },
      { value: 'mid', label: '', labelKey: 'option.mid', sort: 2 },
    ],
  },
]

/** 契约翻译：只登记 `option.mid`（其余 key 回退 `label`）。 */
export const OPTION_SET_CONTRACT_TRANSLATE = (labelKey: string): string | undefined =>
  labelKey === 'option.mid' ? '中' : undefined

/** 选项集解析器契约面。 */
export interface OptionSetResolverContractTarget {
  /** 解析选项集（未登记返回 `undefined`）。 */
  resolve(optionSetKey: string): readonly OptionSetItem[] | undefined
}

/**
 * 选项集解析器契约。
 *
 * 目标约定：快照集取 `OPTION_SET_CONTRACT_SNAPSHOTS`、翻译取 `OPTION_SET_CONTRACT_TRANSLATE`。
 *
 * @param name 契约名。
 * @param create 解析器工厂。
 */
export function describeOptionSetResolverContract(
  name: string,
  create: () => OptionSetResolverContractTarget,
): void {
  describe(name, () => {
    it('已知标识：sort 升序、同值去重保留首个、labelKey 翻译、颜色与禁用保留', () => {
      const items = create().resolve('bms.demo.level')
      expect(items).toBeDefined()
      expect(items?.map((item) => item.value)).toEqual(['low', 'mid', 'high'])
      expect(items?.map((item) => item.label)).toEqual(['低', '中', '高'])
      expect(items?.find((item) => item.value === 'low')?.disabled).toBe(true)
      expect(items?.find((item) => item.value === 'high')?.color).toBe('danger')
      expect(items?.find((item) => item.value === 'mid')?.labelKey).toBe('option.mid')
    })

    it('未登记标识返回 undefined（件层据此空态降级）', () => {
      expect(create().resolve('bms.demo.absent')).toBeUndefined()
    })

    it('同一标识稳定返回（同输入同输出）', () => {
      const target = create()
      expect(target.resolve('bms.demo.level')).toEqual(target.resolve('bms.demo.level'))
    })
  })
}
