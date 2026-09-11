/** 通用实体状态（启用/停用）与 i18n 展示映射。 */

export const EntityStatus = {
  Disabled: 0,
  Enabled: 1,
} as const

export type EntityStatusValue = (typeof EntityStatus)[keyof typeof EntityStatus]

export function entityStatusI18nKey(status: number): string {
  return status === EntityStatus.Enabled ? 'common.enabled' : 'common.disabled'
}
