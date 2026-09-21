/**
 * 搜索族组件基类：在搜索编排能力基类之上承载搜索族身份骨架与展示语义
 * （域标签 / 命中稳定键 / 跳转目标 / 命中语义色 / 可见分组）。
 *
 * 全链：`BaseComponent → BasePlaceholderState → BaseGlobalSearch → BaseSearch → 具体件`。
 */

import { domainLabelOf, hitKey as hitKeyOf, hitRouteTarget, type SearchGroup, type SearchHit } from '../domain/search'
import type { StatusSemantic } from '../domain/status'
import { BaseGlobalSearch } from './global-search'

/** 搜索族组件基类（抽象）。 */
export abstract class BaseSearch extends BaseGlobalSearch {
  /** 能力键（组件基类身份）。 */
  override readonly identifier: string = 'search'
  /** 依赖登记。 */
  override readonly depends: readonly string[] = ['global-search']

  /**
   * 域展示名（未登记回落键名）。
   *
   * @param key 域标识。
   * @returns 域名称。
   */
  domainLabel(key: string): string {
    return domainLabelOf(this.domains, key)
  }

  /**
   * 命中稳定键（`${docType}:${bizId}`）。
   *
   * @param hit 命中项。
   * @returns 稳定键。
   */
  hitKey(hit: SearchHit): string {
    return hitKeyOf(hit)
  }

  /**
   * 命中跳转目标（路由映射归宿主）。
   *
   * @param hit 命中项。
   * @returns 跳转目标。
   */
  hitTarget(hit: SearchHit): { docType: string; bizId: string } {
    return hitRouteTarget(hit)
  }

  /**
   * 命中语义色（审计 / 文件用 `info`，主数据用 `primary`）。
   *
   * @param hit 命中项。
   * @returns 语义色。
   */
  hitSemantic(hit: SearchHit): StatusSemantic {
    return hit.docType === 'log' || hit.docType === 'file_meta' ? 'info' : 'primary'
  }

  /**
   * 「全部」页签下的可见分组（按可检索域过滤，且只保留有命中的域）。
   *
   * @returns 可见分组。
   */
  visibleGroups(): SearchGroup[] {
    const allowed = new Set(this.accessibleDomains.map((domain) => domain.key))
    return this.groups
      .filter((group) => allowed.has(group.key) && group.items.length > 0)
      .map((group) => ({ ...group, items: group.items.map((item) => ({ ...item })) }))
  }
}
