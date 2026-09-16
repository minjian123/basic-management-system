/** IntersectionObserver / ResizeObserver 测试 stub（jsdom 缺失；容器件用例共享）。 */

export interface IOEntry {
  target: Element
  isIntersecting: boolean
}

export type IOCallback = (entries: IOEntry[]) => void

export interface IOOptions {
  root?: Element | null
  rootMargin?: string
  threshold?: number
}

export class IOStub {
  static instances: IOStub[] = []
  callback: IOCallback
  options: IOOptions | undefined
  observed: Element[] = []

  constructor(callback: IOCallback, options?: IOOptions) {
    this.callback = callback
    this.options = options
    IOStub.instances.push(this)
  }

  observe(el: Element): void {
    this.observed.push(el)
  }

  unobserve(): void {}

  disconnect(): void {}

  takeRecords(): IOEntry[] {
    return []
  }
}

export interface ROEntry {
  target: Element
  borderBoxSize?: { blockSize: number }[]
}

export type ROCallback = (entries: ROEntry[]) => void

export class ROStub {
  static instances: ROStub[] = []
  callback: ROCallback
  observed: Element[] = []

  constructor(callback: ROCallback) {
    this.callback = callback
    ROStub.instances.push(this)
  }

  observe(el: Element): void {
    if (!this.observed.includes(el)) {
      this.observed.push(el)
    }
  }

  unobserve(): void {}

  disconnect(): void {}
}
