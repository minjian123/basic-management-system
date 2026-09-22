/**
 * 样例占位数据服务（模块内自包含；真实接口随后续窗口联调时替换本实现）。
 *
 * 本地 fixture + 模拟延迟 + 统一分页响应签名（对齐 `{ list, total, page, size }`）；写操作改内存集，
 * 会话内生效、刷新复位。**不使用任何持久化 API**（隔离约定，见任务 03_01 R2）。
 */

import { BaseError, ErrorCodes } from '@bms/core'

import type { SampleCategory, SampleInput, SamplePage, SamplePriority, SampleQuery, SampleRecord, SampleStatus } from '../domain'

/** 服务选项。 */
export interface SampleServiceOptions {
  /** 模拟延迟（毫秒；测试注入 0）。 */
  delayMs?: number
  /** 是否注入种子数据（缺省 true；测试可关闭）。 */
  seed?: boolean
}

/** 种子数据（名称 / 分类 / 优先级 / 金额 / 状态 / 负责人）。 */
const SEED: readonly [string, SampleCategory, SamplePriority, number, SampleStatus, string][] = [
  ['服务器采购', 'hardware', 'high', 128000, 'active', '张三'],
  ['办公软件授权', 'software', 'normal', 32000, 'active', '李四'],
  ['设备维保服务', 'service', 'normal', 15600, 'pending', '王五'],
  ['网络交换机扩容', 'hardware', 'urgent', 88000, 'pending', '张三'],
  ['数据库审计工具', 'software', 'high', 46000, 'draft', '赵六'],
  ['机房空调改造', 'hardware', 'normal', 23000, 'closed', '李四'],
  ['安全巡检服务', 'service', 'low', 9800, 'active', '王五'],
  ['打印机耗材', 'other', 'low', 2400, 'closed', '赵六'],
  ['远程桌面授权', 'software', 'normal', 18000, 'active', '张三'],
  ['等保测评服务', 'service', 'urgent', 76000, 'pending', '李四'],
  ['存储阵列扩容', 'hardware', 'high', 210000, 'draft', '王五'],
  ['邮件网关续费', 'software', 'low', 6800, 'active', '赵六'],
  ['监控大屏安装', 'hardware', 'normal', 54000, 'active', '张三'],
  ['桌面运维外包', 'service', 'normal', 96000, 'pending', '李四'],
  ['键盘鼠标套装', 'other', 'low', 3600, 'closed', '王五'],
  ['备份一体机', 'hardware', 'high', 143000, 'active', '赵六'],
  ['漏洞扫描服务', 'service', 'high', 42000, 'draft', '张三'],
  ['正版字体授权', 'software', 'normal', 12000, 'closed', '李四'],
  ['UPS 电源采购', 'hardware', 'urgent', 68000, 'pending', '王五'],
  ['日志分析平台', 'software', 'high', 158000, 'active', '赵六'],
  ['视频会议服务', 'service', 'normal', 26000, 'active', '张三'],
  ['硬盘扩容件', 'other', 'normal', 7200, 'closed', '李四'],
  ['灾备演练服务', 'service', 'urgent', 52000, 'draft', '王五'],
]

/**
 * 构造种子记录（确定性，便于用例断言）。
 *
 * @returns 记录清单。
 */
function createSeedRecords(): SampleRecord[] {
  const base = Date.parse('2026-09-01T08:00:00.000Z')
  return SEED.map((item, index) => {
    const [name, category, priority, amount, status, owner] = item
    const seq = index + 1
    const createdAt = new Date(base + index * 3_600_000).toISOString()
    return {
      id: `s${String(seq).padStart(3, '0')}`,
      code: `SP-${String(seq).padStart(4, '0')}`,
      name,
      category,
      priority,
      amount,
      status,
      owner,
      createdAt,
      updatedAt: createdAt,
      remark: `${name}（样例占位数据）`,
    }
  })
}

/** 样例占位数据服务。 */
export class SampleDataService {
  /** 内存记录集。 */
  #records: SampleRecord[]
  /** 模拟延迟（毫秒）。 */
  #delayMs: number
  /** 主键序号。 */
  #seq: number

  /**
   * 构造服务。
   *
   * @param options 选项。
   */
  constructor(options: SampleServiceOptions = {}) {
    this.#delayMs = options.delayMs ?? 200
    this.#records = options.seed === false ? [] : createSeedRecords()
    this.#seq = this.#records.length
  }

  /** 模拟延迟（测试注入 0 时不阻塞）。 */
  async #delay(): Promise<void> {
    if (this.#delayMs <= 0) {
      return
    }
    await new Promise<void>((resolve) => {
      setTimeout(resolve, this.#delayMs)
    })
  }

  /**
   * 列表查询（关键词 + 分类 + 状态筛选，内存分页）。
   *
   * @param query 查询入参。
   * @returns 分页结果。
   */
  async list(query: SampleQuery): Promise<SamplePage> {
    await this.#delay()
    const keyword = query.keyword?.trim().toLowerCase() ?? ''
    const filtered = this.#records.filter((record) => {
      const hitKeyword = keyword === '' || record.code.toLowerCase().includes(keyword) || record.name.toLowerCase().includes(keyword)
      const hitCategory = query.category === undefined || record.category === query.category
      const hitStatus = query.status === undefined || record.status === query.status
      return hitKeyword && hitCategory && hitStatus
    })
    const total = filtered.length
    const start = (query.page - 1) * query.size
    const list = filtered.slice(start, start + query.size)
    return { list, total, page: query.page, size: query.size }
  }

  /**
   * 按主键取详情。
   *
   * @param id 主键。
   * @returns 记录。
   * @throws BaseError 记录不存在（`PROVIDER_NOT_REGISTERED`）。
   */
  async get(id: string): Promise<SampleRecord> {
    await this.#delay()
    const record = this.#records.find((item) => item.id === id)
    if (record === undefined) {
      throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `记录不存在：${id}`)
    }
    return { ...record }
  }

  /**
   * 新建记录。
   *
   * @param input 入参。
   * @returns 新建记录。
   */
  async create(input: SampleInput): Promise<SampleRecord> {
    await this.#delay()
    this.#seq += 1
    const seq = this.#seq
    const now = new Date().toISOString()
    const record: SampleRecord = {
      ...input,
      id: `s${String(seq).padStart(3, '0')}`,
      code: `SP-${String(seq).padStart(4, '0')}`,
      createdAt: now,
      updatedAt: now,
    }
    this.#records.push(record)
    return { ...record }
  }

  /**
   * 更新记录。
   *
   * @param id 主键。
   * @param input 入参。
   * @returns 更新后记录。
   * @throws BaseError 记录不存在（`PROVIDER_NOT_REGISTERED`）。
   */
  async update(id: string, input: SampleInput): Promise<SampleRecord> {
    await this.#delay()
    const index = this.#records.findIndex((item) => item.id === id)
    if (index < 0) {
      throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `记录不存在：${id}`)
    }
    const next: SampleRecord = { ...this.#records[index], ...input, updatedAt: new Date().toISOString() }
    this.#records[index] = next
    return { ...next }
  }

  /**
   * 删除记录。
   *
   * @param id 主键。
   * @throws BaseError 记录不存在（`PROVIDER_NOT_REGISTERED`）。
   */
  async remove(id: string): Promise<void> {
    await this.#delay()
    const index = this.#records.findIndex((item) => item.id === id)
    if (index < 0) {
      throw new BaseError(ErrorCodes.PROVIDER_NOT_REGISTERED, `记录不存在：${id}`)
    }
    this.#records.splice(index, 1)
  }
}

/** 模块单例服务（视图直接消费；真实接口替换点）。 */
export const sampleService = new SampleDataService()
