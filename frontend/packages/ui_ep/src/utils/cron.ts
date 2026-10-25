/** cron 纯函数：5 段解析 / 人类可读描述 / 合法性校验 / 常用模板（前端轻校验，执行以后端为准）。 */

/** cron 五段。 */
export interface CronFields {
  /** 分。 */
  minute: string
  /** 时。 */
  hour: string
  /** 日。 */
  day: string
  /** 月。 */
  month: string
  /** 周。 */
  week: string
}

/** cron 模板。 */
export interface CronTemplate {
  /** 模板键。 */
  key: string
  /** 模板名。 */
  label: string
  /** 表达式。 */
  expression: string
}

/** cron 校验结果。 */
export interface CronValidateResult {
  /** 是否合法。 */
  valid: boolean
  /** 非法说明。 */
  message?: string
}

/** 常用模板。 */
export const CRON_TEMPLATES: CronTemplate[] = [
  { key: 'every-minute', label: '每分钟', expression: '* * * * *' },
  { key: 'hourly', label: '每小时', expression: '0 * * * *' },
  { key: 'daily', label: '每天 0 点', expression: '0 0 * * *' },
  { key: 'weekly-monday', label: '每周一 09:00', expression: '0 9 * * 1' },
  { key: 'monthly', label: '每月 1 日 0 点', expression: '0 0 1 * *' },
]

/** 段名。 */
const FIELD_LABELS = ['分', '时', '日', '月', '周']

/** 段取值范围（分 / 时 / 日 / 月 / 周）。 */
const FIELD_RANGES: [number, number][] = [
  [0, 59],
  [0, 23],
  [1, 31],
  [1, 12],
  [0, 7],
]

/** 周名。 */
const WEEK_NAMES = ['周日', '周一', '周二', '周三', '周四', '周五', '周六']

/**
 * 解析 5 段 cron（段数不符返回 `undefined`）。
 *
 * @param expression 表达式。
 */
export function parseCron(expression: string): CronFields | undefined {
  const parts = expression.trim().split(/\s+/)
  if (parts.length !== 5) {
    return undefined
  }
  return { minute: parts[0], hour: parts[1], day: parts[2], month: parts[3], week: parts[4] }
}

/**
 * 组装 5 段 cron。
 *
 * @param fields 五段。
 */
export function formatCron(fields: CronFields): string {
  return [fields.minute, fields.hour, fields.day, fields.month, fields.week].join(' ')
}

/** 校验单段（支持通配、单值、区间、枚举、步进）。 */
function isValidSegment(segment: string, min: number, max: number): boolean {
  if (segment === '') {
    return false
  }
  return segment.split(',').every((part) => {
    const [base, step, ...rest] = part.split('/')
    if (rest.length > 0) {
      return false
    }
    if (step !== undefined && (!/^\d+$/.test(step) || Number(step) <= 0)) {
      return false
    }
    if (base === '*') {
      return true
    }
    const range = base.split('-')
    if (range.length > 2) {
      return false
    }
    const numbers = range.map((item) => (/^\d+$/.test(item) ? Number(item) : Number.NaN))
    if (numbers.some((item) => Number.isNaN(item))) {
      return false
    }
    return numbers.every((item) => item >= min && item <= max)
  })
}

/**
 * 校验 5 段 cron。
 *
 * @param expression 表达式。
 */
export function validateCron(expression: string): CronValidateResult {
  const fields = parseCron(expression)
  if (!fields) {
    return { valid: false, message: '需为 5 段 cron（分 时 日 月 周）' }
  }
  const values = [fields.minute, fields.hour, fields.day, fields.month, fields.week]
  for (let index = 0; index < values.length; index += 1) {
    if (!isValidSegment(values[index], FIELD_RANGES[index][0], FIELD_RANGES[index][1])) {
      return { valid: false, message: `${FIELD_LABELS[index]}段非法` }
    }
  }
  return { valid: true }
}

/**
 * 生成人类可读描述（非法或无法归纳时返回原文）。
 *
 * @param expression 表达式。
 */
export function describeCron(expression: string): string {
  const fields = parseCron(expression)
  if (!fields) {
    return ''
  }
  const { minute, hour, day, month, week } = fields
  if (minute === '*' && hour === '*' && day === '*' && month === '*' && week === '*') {
    return '每分钟'
  }
  const hasTime = /^\d+$/.test(minute) && /^\d+$/.test(hour)
  const time = hasTime ? `${hour.padStart(2, '0')}:${minute.padStart(2, '0')}` : ''
  if (week !== '*') {
    const weekName = /^\d+$/.test(week) ? WEEK_NAMES[Number(week) % 7] : `周(${week})`
    return time ? `每${weekName} ${time}` : `每${weekName}`
  }
  if (day !== '*') {
    const dayName = /^\d+$/.test(day) ? `${day} 日` : day
    return time ? `每月 ${dayName} ${time}` : `每月 ${dayName}`
  }
  if (hasTime) {
    return `每天 ${time}`
  }
  if (minute === '0' && hour === '*') {
    return '每小时整点'
  }
  if (minute !== '*' && hour === '*') {
    return `每小时第 ${minute} 分`
  }
  return time ? `每天 ${time}` : expression
}
