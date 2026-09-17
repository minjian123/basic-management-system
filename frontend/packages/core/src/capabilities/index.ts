/**
 * 能力层出口：导入即完成「已知能力登记（manifest）+ 能力注册」（不注册不可用）。
 *
 * S2：31 项全量（值·字段链 4 / 形态 7 / 复用 20），与《前端基类清单》能力片段节逐项对齐。
 */

import { registerCapability, type CapabilityRegistration } from './registry'
import { BaseValue } from './value'
import { BaseFieldShell } from './field-shell'
import { BaseFieldPerm } from './field-perm'
import { BaseField } from './field'
import { BaseInteractive } from './interactive'
import { BaseInputControl } from './input-control'
import { BaseDisplayControl } from './display-control'
import { BaseContainer } from './container'
import { BaseFormContainer } from './form-container'
import { BaseMedia } from './media'
import { BaseLayout } from './layout'
import { BaseTabs } from './tabs'
import { BasePersistedState } from './persisted-state'
import { BaseOptionSource } from './option-source'
import { BaseUploadEngine } from './upload-engine'
import { BaseAsyncTask } from './async-task'
import { BaseEditorKernel } from './editor-kernel'
import { BaseTreeData } from './tree-data'
import { BaseUserDisplay } from './user-display'
import { BaseDynamicRoutes } from './dynamic-routes'
import { BaseFormMeta } from './form-meta'
import { BasePresignedUrl } from './presigned-url'
import { BaseDragDrop } from './drag-drop'
import { BaseDesignToken } from './design-token'
import { BaseFormPage } from './form-page'
import { BaseLocale } from './locale'
import { BaseAccess } from './access'
import { BaseColumnConfig } from './column-config'
import { BaseQueryScheme } from './query-scheme'
import { BaseWatermark } from './watermark'
import { BaseModuleContext } from './module-context'

import './manifest'

const registrations: CapabilityRegistration[] = [
  {
    key: 'value',
    depends: [],
    describe: () => ({ key: 'value' }),
    create: (options) => new BaseValue(options as never),
  },
  {
    key: 'field-shell',
    depends: [],
    describe: () => ({ key: 'field-shell' }),
    create: (options) => new BaseFieldShell(options as never),
  },
  {
    key: 'field-perm',
    depends: [],
    describe: () => ({ key: 'field-perm' }),
    create: (options) => new BaseFieldPerm(options as never),
  },
  {
    key: 'field',
    depends: ['value', 'field-shell', 'field-perm'],
    describe: () => ({ key: 'field' }),
    create: (options) => new BaseField(options as never),
  },
  {
    key: 'interactive',
    depends: [],
    describe: () => ({ key: 'interactive' }),
    create: (options) => new BaseInteractive(options as never),
  },
  {
    key: 'input-control',
    depends: [],
    describe: () => ({ key: 'input-control' }),
    create: (options) => new BaseInputControl(options as never),
  },
  {
    key: 'display-control',
    depends: [],
    describe: () => ({ key: 'display-control' }),
    create: (options) => new BaseDisplayControl(options as never),
  },
  {
    key: 'container',
    depends: [],
    describe: () => ({ key: 'container' }),
    create: (options) => new BaseContainer(options as never),
  },
  {
    key: 'form-container',
    depends: [],
    describe: () => ({ key: 'form-container' }),
    create: (options) => new BaseFormContainer(options as never),
  },
  {
    key: 'media',
    depends: ['presigned-url'],
    describe: () => ({ key: 'media' }),
    create: (options) => new BaseMedia(options as never),
  },
  {
    key: 'layout',
    depends: ['design-token'],
    describe: () => ({ key: 'layout' }),
    create: (options) => new BaseLayout(options as never),
  },
  {
    key: 'tabs',
    depends: [],
    describe: () => ({ key: 'tabs' }),
    create: (options) => new BaseTabs(options as never),
  },
  {
    key: 'persisted-state',
    depends: [],
    describe: () => ({ key: 'persisted-state' }),
    create: (options) => new BasePersistedState(options as never),
  },
  {
    key: 'option-source',
    depends: ['value'],
    describe: () => ({ key: 'option-source' }),
    create: (options) => new BaseOptionSource(options as never),
  },
  {
    key: 'upload-engine',
    depends: ['presigned-url'],
    describe: () => ({ key: 'upload-engine' }),
    create: (options) => new BaseUploadEngine(options as never),
  },
  {
    key: 'async-task',
    depends: [],
    describe: () => ({ key: 'async-task' }),
    create: (options) => new BaseAsyncTask(options as never),
  },
  {
    key: 'editor-kernel',
    depends: [],
    describe: () => ({ key: 'editor-kernel' }),
    create: (options) => new BaseEditorKernel(options as never),
  },
  {
    key: 'tree-data',
    depends: [],
    describe: () => ({ key: 'tree-data' }),
    create: (options) => new BaseTreeData(options as never),
  },
  {
    key: 'user-display',
    depends: [],
    describe: () => ({ key: 'user-display' }),
    create: (options) => new BaseUserDisplay(options as never),
  },
  {
    key: 'dynamic-routes',
    depends: [],
    describe: () => ({ key: 'dynamic-routes' }),
    create: (options) => new BaseDynamicRoutes(options as never),
  },
  {
    key: 'form-meta',
    depends: [],
    describe: () => ({ key: 'form-meta' }),
    create: (options) => new BaseFormMeta(options as never),
  },
  {
    key: 'presigned-url',
    depends: [],
    describe: () => ({ key: 'presigned-url' }),
    create: (options) => new BasePresignedUrl(options as never),
  },
  {
    key: 'drag-drop',
    depends: [],
    describe: () => ({ key: 'drag-drop' }),
    create: (options) => new BaseDragDrop(options as never),
  },
  {
    key: 'design-token',
    depends: [],
    describe: () => ({ key: 'design-token' }),
    create: (options) => new BaseDesignToken(options as never),
  },
  {
    key: 'form-page',
    depends: [],
    describe: () => ({ key: 'form-page' }),
    create: (options) => new BaseFormPage(options as never),
  },
  {
    key: 'locale',
    depends: [],
    describe: () => ({ key: 'locale' }),
    create: (options) => new BaseLocale(options as never),
  },
  {
    key: 'access',
    depends: [],
    describe: () => ({ key: 'access' }),
    create: (options) => new BaseAccess(options as never),
  },
  {
    key: 'column-config',
    depends: ['persisted-state'],
    describe: () => ({ key: 'column-config' }),
    create: (options) => new BaseColumnConfig(options as never),
  },
  {
    key: 'query-scheme',
    depends: ['persisted-state'],
    describe: () => ({ key: 'query-scheme' }),
    create: (options) => new BaseQueryScheme(options as never),
  },
  {
    key: 'watermark',
    depends: [],
    describe: () => ({ key: 'watermark' }),
    create: (options) => new BaseWatermark(options as never),
  },
  {
    key: 'module-context',
    depends: [],
    describe: () => ({ key: 'module-context' }),
    create: (options) => new BaseModuleContext(options as never),
  },
]

for (const registration of registrations) {
  registerCapability(registration)
}

export * from './value'
export * from './field-shell'
export * from './field-perm'
export * from './field'
export * from './interactive'
export * from './input-control'
export * from './display-control'
export * from './container'
export * from './form-container'
export * from './media'
export * from './layout'
export * from './tabs'
export * from './persisted-state'
export * from './option-source'
export * from './upload-engine'
export * from './async-task'
export * from './editor-kernel'
export * from './tree-data'
export * from './user-display'
export * from './dynamic-routes'
export * from './form-meta'
export * from './presigned-url'
export * from './drag-drop'
export * from './design-token'
export * from './form-page'
export * from './locale'
export * from './access'
export * from './column-config'
export * from './query-scheme'
export * from './watermark'
export * from './module-context'
export {
  CapabilityRegistry,
  capabilityRegistry,
  createCapability,
  registerCapability,
  type CapabilityRegistration,
} from './registry'
export { capabilityManifest } from './manifest'
