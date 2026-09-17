/**
 * 表单页组合片段（`form-page`）：新增 / 编辑 / 详情三态、提交、脏数据与返回确认。
 *
 * 契约见《组件设计 · 表单页组合片段》：`loadDetail` / `submit` / `reset` / `isDirty` / `leave` + 三态判定
 * （与 `useListPage` / `useFormModal` 对称；请求能力归 `02_06` 请求封装，本片段只**消费注入的 api**）。
 * **占位先行**：未注入 `api`（后端接口未接入）时 `loadDetail` 返回空模型、`submit` 直接拒绝并标记占位。
 */

import { computed, ref, shallowRef, toValue, type MaybeRefOrGetter } from 'vue'

import { declareFragment } from '../fragments'

/** 表单页模式 */
export type FormPageMode = 'create' | 'edit' | 'detail'

/** 表单页接口适配（由请求层或具体页面注入） */
export interface FormPageApi<TModel extends Record<string, unknown> = Record<string, unknown>> {
  detail?: (id: string | number) => Promise<TModel>
  create?: (payload: TModel) => Promise<unknown>
  update?: (id: string | number, payload: TModel) => Promise<unknown>
}

/** 表单页组合片段参数 */
export interface UseFormPageOptions<TModel extends Record<string, unknown> = Record<string, unknown>> {
  /** 模式（缺省按 `id` 判定：有 id = edit） */
  mode?: MaybeRefOrGetter<FormPageMode | undefined>
  id?: MaybeRefOrGetter<string | number | undefined>
  /** 接口适配（缺省即占位） */
  api?: FormPageApi<TModel>
  /** 脏数据检查（默认开启） */
  dirtyCheck?: MaybeRefOrGetter<boolean>
  /** 离开前确认（默认开启） */
  leaveConfirm?: MaybeRefOrGetter<boolean>
  /** 初始模型（新增用） */
  defaultModel?: TModel
  /** 变更通知 */
  onSaved?: (result: unknown) => void
  onDirtyChange?: (dirty: boolean) => void
}

/** 表单页组合片段返回值 */
export interface UseFormPageReturn<TModel extends Record<string, unknown> = Record<string, unknown>> {
  readonly mode: FormPageMode
  readonly id: string | number | undefined
  readonly model: TModel
  readonly loading: boolean
  readonly saving: boolean
  readonly isDirty: boolean
  readonly isPlaceholder: boolean
  readonly saved: boolean
  /** 是否可编辑（详情态不可编辑） */
  readonly editable: boolean
  loadDetail: (id?: string | number) => Promise<TModel>
  /** 直接更新模型（**不**重置基线，`isDirty` 据此判定） */
  setModel: (value: TModel) => void
  submit: (payload?: TModel) => Promise<boolean>
  reset: () => void
  /** 标记已保存（提交成功后由外部调用或 submit 内自动） */
  markSaved: () => void
  /** 返回 / 离开：脏数据且需确认时返回 `false`（调用方弹确认框后再调 `leave(true)`） */
  leave: (force?: boolean) => boolean
}

/**
 * 获取表单页组合能力。
 *
 * 用法：`const page = useFormPage({ id, api })`；`page.isDirty` 驱动离开确认，`submit()` 处理新增 / 编辑分流。
 */
export function useFormPage<TModel extends Record<string, unknown> = Record<string, unknown>>(
  options: UseFormPageOptions<TModel> = {},
): UseFormPageReturn<TModel> {
  const capability = declareFragment('form-page')

  const loading = ref(false)
  const saving = ref(false)
  const saved = ref(false)
  const baseline = ref<string>('')
  // 泛型模型用 `shallowRef`：避免深度解包破坏业务对象形状
  const model = shallowRef<TModel>((options.defaultModel ?? {}) as TModel)
  const isPlaceholder = computed(() => options.api === undefined)

  const id = computed(() => toValue(options.id))
  const mode = computed<FormPageMode>(() => {
    const explicit = toValue(options.mode)
    if (explicit) {
      return explicit
    }
    return id.value === undefined ? 'create' : 'edit'
  })

  const serialize = (value: TModel): string => {
    try {
      return JSON.stringify(value)
    } catch {
      return String(value)
    }
  }

  const isDirty = computed(() => {
    if (!(toValue(options.dirtyCheck) ?? true)) {
      return false
    }
    return serialize(model.value) !== baseline.value
  })

  const editable = computed(() => mode.value !== 'detail')

  const setModel = (value: TModel, markBaseline = true): void => {
    model.value = value
    if (markBaseline) {
      baseline.value = serialize(value)
    }
    options.onDirtyChange?.(false)
  }

  const loadDetail = async (targetId?: string | number): Promise<TModel> => {
    const target = targetId ?? id.value
    if (target === undefined || !options.api?.detail) {
      capability.log('debug', 'form-page 占位：详情接口未接入，返回初始模型')
      setModel((options.defaultModel ?? {}) as TModel)
      return model.value
    }
    loading.value = true
    try {
      const detail = await options.api.detail(target)
      setModel({ ...(options.defaultModel ?? {}), ...detail } as TModel)
      return model.value
    } catch (error) {
      capability.reportError(error, { scope: 'form-page.loadDetail', id: target })
      return model.value
    } finally {
      loading.value = false
    }
  }

  const submit = async (payload?: TModel): Promise<boolean> => {
    const data = payload ?? model.value
    if (mode.value === 'detail') {
      return false
    }
    saving.value = true
    try {
      if (mode.value === 'create') {
        if (!options.api?.create) {
          capability.log('warn', 'form-page 占位：新增接口未接入，提交被拒绝')
          return false
        }
        const result = await options.api.create(data)
        options.onSaved?.(result)
      } else {
        if (!options.api?.update || id.value === undefined) {
          capability.log('warn', 'form-page 占位：更新接口未接入，提交被拒绝')
          return false
        }
        const result = await options.api.update(id.value, data)
        options.onSaved?.(result)
      }
      saved.value = true
      baseline.value = serialize(data)
      return true
    } catch (error) {
      capability.reportError(error, { scope: 'form-page.submit', mode: mode.value })
      return false
    } finally {
      saving.value = false
    }
  }

  return {
    get mode() {
      return mode.value
    },
    get id() {
      return id.value
    },
    get model() {
      return model.value
    },
    get loading() {
      return loading.value
    },
    get saving() {
      return saving.value
    },
    get isDirty() {
      return isDirty.value
    },
    get isPlaceholder() {
      return isPlaceholder.value
    },
    get saved() {
      return saved.value
    },
    get editable() {
      return editable.value
    },
    loadDetail,
    setModel: (value) => {
      model.value = value
    },
    submit,
    reset: () => {
      setModel((options.defaultModel ?? {}) as TModel)
      saved.value = false
    },
    markSaved: () => {
      saved.value = true
      baseline.value = serialize(model.value)
    },
    leave: (force = false) => {
      if (force || !(toValue(options.leaveConfirm) ?? true) || !isDirty.value) {
        return true
      }
      options.onDirtyChange?.(true)
      return false
    },
  }
}
