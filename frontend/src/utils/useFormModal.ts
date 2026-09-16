/**
 * 弹窗表单状态机：开关 / 三态 / 详情加载 / 校验 / 提交 / 脏数据基线 / 409 冲突。
 *
 * 契约见《组件设计 · 弹窗抽屉表单》§5 / §6 / §7：
 * - 三态 `openCreate` / `openEdit` / `openView`；打开时重置并重建脏数据基线（`stableStringify`）；
 * - 校验经 `el-form` 的 `validate()`（页面把表单 ref 绑定到返回的 `formRef`）；
 * - 提交由 `api.create` / `api.update` 注入（内部经 `useRequest`：loading / 竞态 / 取消），
 *   `edit` 携带 `version`（乐观锁）；成功关闭并回调 `onSuccess`；
 * - 409 冲突：提示「记录已被修改」后**重新拉详情覆盖**（不清空弹窗）；详情加载失败禁止提交。
 */

import type { FormInstance } from 'element-plus'
import { computed, ref, type ComputedRef, type Ref } from 'vue'

import { ApiError, CONFLICT_CODE } from '@/api/error'

import { stableStringify } from './serialize'
import { useRequest } from './useRequest'

/** 弹窗表单三态 */
export type FormModalMode = 'create' | 'edit' | 'view'

/** 提交接口注入（经请求封装实现；`edit` 提交携带 `version`） */
export interface FormModalApi<T extends Record<string, unknown>> {
  create?: (payload: T) => Promise<unknown>
  update?: (id: string | number, payload: T, version?: number) => Promise<unknown>
  detail?: (id: string | number) => Promise<T>
}

/** `useFormModal` 参数 */
export interface UseFormModalOptions<T extends Record<string, unknown>> {
  api: FormModalApi<T>
  /** 打开（create）默认值工厂 */
  defaultData?: () => Partial<T>
  /** 提交成功回调（页面刷新列表 / 局部更新） */
  onSuccess?: (data: unknown, mode: FormModalMode) => void
  /** 详情加载失败回调（缺省由请求层统一提示） */
  onDetailError?: (error: unknown) => void
}

/** `useFormModal` 返回值 */
export interface UseFormModalReturn<T extends Record<string, unknown>> {
  visible: Ref<boolean>
  mode: Ref<FormModalMode>
  /** 对象名（与容器「动作词 + 对象名」拼标题） */
  title: Ref<string | null>
  formData: Ref<T>
  /** 表单实例（页面把 ref 绑定到插槽内 `el-form`） */
  formRef: Ref<FormInstance | null>
  /** 记录 id（edit / view） */
  id: Ref<string | number | null>
  /** 记录版本号（乐观锁，详情返回时记录） */
  version: Ref<number | null>
  /** 脏数据（相对打开时基线） */
  dirty: ComputedRef<boolean>
  detailLoading: Ref<boolean>
  detailError: Ref<unknown>
  submitLoading: Ref<boolean>
  openCreate(defaultData?: Partial<T>, objectTitle?: string): void
  openEdit(id: string | number, objectTitle?: string): Promise<void>
  openView(id: string | number, objectTitle?: string): Promise<void>
  submit(): Promise<boolean>
  /** 直接注入 / 回填表单数据（保持插槽绑定响应） */
  setFormData(data: Partial<T>): void
  /** 重置表单与校验态（EP `resetFields`） */
  resetFields(): void
  /** 程序关闭（复位在途提交；用户交互关闭请走容器拦截链） */
  close(): void
}

/** 冲突判定：HTTP 409 或业务冲突码（`error.conflict`） */
function isConflict(error: unknown): boolean {
  return error instanceof ApiError && (error.httpStatus === 409 || error.code === CONFLICT_CODE)
}

/**
 * 获取弹窗表单能力。
 *
 * 用法：页面持 `modal`，模板绑定 `<FormDrawer v-model="modal.visible.value" :mode="modal.mode.value" :dirty="modal.dirty.value" @submit="modal.submit" />`，
 * 插槽内 `el-form :model="modal.formData"` 并以 `modal.formRef` 绑定。
 */
export function useFormModal<T extends Record<string, unknown>>(
  options: UseFormModalOptions<T>,
): UseFormModalReturn<T> {
  const visible = ref(false)
  const mode = ref<FormModalMode>('create')
  const title = ref<string | null>(null)
  const formData = ref({}) as Ref<T>
  const formRef = ref<FormInstance | null>(null)
  const id = ref<string | number | null>(null)
  const version = ref<number | null>(null)
  const detailError = ref<unknown>(null)

  const baseline = ref('')
  const baselineReady = ref(false)
  const dirty = computed(() => baselineReady.value && stableStringify(formData.value) !== baseline.value)

  function markBaseline(): void {
    baseline.value = stableStringify(formData.value)
    baselineReady.value = true
  }

  // 详情请求：fetcher 读 ref（支持连续 openEdit 的竞态保护——仅最新请求写回）
  const detailTargetId = ref<string | number | null>(null)
  const detailReq = useRequest<T>(async () => {
    const api = options.api.detail
    const target = detailTargetId.value
    if (!api || target === null) {
      throw new Error('useFormModal: detail 接口或 id 缺失')
    }
    return api(target)
  })

  // 提交请求：pending 读取（create / update 动态分支）
  let pendingSubmit: (() => Promise<unknown>) | null = null
  const submitReq = useRequest<unknown>(async () => {
    if (!pendingSubmit) {
      throw new Error('useFormModal: 提交未就绪')
    }
    return pendingSubmit()
  })

  function prepare(defaultValues?: Partial<T>): void {
    formData.value = { ...(options.defaultData?.() ?? {}), ...(defaultValues ?? {}) } as T
    baselineReady.value = false
    formRef.value?.resetFields()
    markBaseline()
  }

  function resetFields(): void {
    formRef.value?.resetFields()
  }

  function setFormData(data: Partial<T>): void {
    Object.assign(formData.value, data)
  }

  async function loadDetail(targetId: string | number): Promise<void> {
    detailTargetId.value = targetId
    detailError.value = null
    const result = await detailReq.run()
    if (detailTargetId.value !== targetId) {
      return
    }
    if (result !== null && detailReq.error.value === null) {
      formData.value = { ...result } as T
      version.value = typeof result.version === 'number' ? result.version : null
      return
    }
    if (detailReq.error.value) {
      detailError.value = detailReq.error.value
      options.onDetailError?.(detailReq.error.value)
    }
  }

  function openCreate(defaultValues?: Partial<T>, objectTitle?: string): void {
    mode.value = 'create'
    id.value = null
    version.value = null
    detailError.value = null
    if (objectTitle !== undefined) {
      title.value = objectTitle
    }
    prepare(defaultValues)
    visible.value = true
  }

  async function openEdit(targetId: string | number, objectTitle?: string): Promise<void> {
    mode.value = 'edit'
    id.value = targetId
    version.value = null
    detailError.value = null
    if (objectTitle !== undefined) {
      title.value = objectTitle
    }
    prepare()
    visible.value = true
    await loadDetail(targetId)
    markBaseline()
  }

  async function openView(targetId: string | number, objectTitle?: string): Promise<void> {
    mode.value = 'view'
    id.value = targetId
    version.value = null
    detailError.value = null
    if (objectTitle !== undefined) {
      title.value = objectTitle
    }
    prepare()
    visible.value = true
    await loadDetail(targetId)
    markBaseline()
  }

  async function submit(): Promise<boolean> {
    if (submitReq.loading.value) {
      return false
    }
    if (mode.value !== 'create' && options.api.detail && detailError.value) {
      // 详情加载失败：禁止空表单提交（保留弹窗与错误态）
      return false
    }
    if (formRef.value) {
      try {
        await formRef.value.validate()
      } catch {
        return false
      }
    }
    const payload = { ...formData.value } as T
    if (mode.value === 'edit' && options.api.update && id.value !== null) {
      const targetId = id.value
      const currentVersion = version.value
      pendingSubmit = () => options.api.update!(targetId, payload, currentVersion ?? undefined)
    } else if (mode.value === 'create' && options.api.create) {
      pendingSubmit = () => options.api.create!(payload)
    } else {
      return false
    }
    try {
      const result = await submitReq.run()
      if (submitReq.error.value) {
        if (isConflict(submitReq.error.value) && mode.value !== 'create' && id.value !== null) {
          await loadDetail(id.value)
          markBaseline()
        }
        return false
      }
      visible.value = false
      options.onSuccess?.(result, mode.value)
      return true
    } finally {
      pendingSubmit = null
    }
  }

  function close(): void {
    submitReq.cancel()
    visible.value = false
  }

  return {
    visible,
    mode,
    title,
    formData,
    formRef,
    id,
    version,
    dirty,
    detailLoading: detailReq.loading,
    detailError,
    submitLoading: submitReq.loading,
    openCreate,
    openEdit,
    openView,
    submit,
    setFormData,
    resetFields,
    close,
  }
}
