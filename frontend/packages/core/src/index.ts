/**
 * `@bms/core`：前端框架无关核心运行时入口。
 *
 * 纯 TS，不依赖 Vue / UI 库 / 插件 / 宿主（护栏 `tests/guard-core-framework-agnostic.spec.ts`）。
 * 基类与能力导出随 `02_01` ~ `02_06` 就位后在本入口追加。
 */

export {
  BaseObject,
  configureBase,
  getBaseSinks,
  resetBaseSinks,
  type BaseConfigSource,
  type BaseLoggerSink,
  type BaseReporterSink,
  type BaseSinks,
  type LogLevel,
} from './base/BaseObject'
export { withBaseObject, type BaseObjectSurface } from './base/mixin'
export {
  BaseComponent,
  type ComponentProps,
  type DensityToken,
  type LifecycleEvent,
  type LifecycleListener,
  type LifecyclePayload,
  type SizeToken,
} from './base/BaseComponent'

export { ErrorCodes, FRONTEND_RESERVED_SEGMENT, isFrontendReservedCode, type ErrorCode } from './mechanisms/error-codes'
export { BaseCapability } from './mechanisms/capability'
export { BasePluggable, DEFAULT_CONTRACT_VERSION } from './mechanisms/pluggable'
export { BaseError, type BaseErrorOptions } from './mechanisms/error'
export { BaseProviderRegistry, CapabilityRegistry } from './mechanisms/registry'
export { BaseProvider } from './mechanisms/provider'
export { BaseFactory } from './mechanisms/factory'
export { BaseAsyncResource, type Disposable } from './mechanisms/resource'
export { BaseSubscription } from './mechanisms/subscription'
export { BaseNullObject, BasePlaceholder, BaseStub, type PlaceholderReason } from './mechanisms/placeholder'

export { BaseValue, type ValueListener } from './capabilities/value'
export { BaseField, type FieldTrigger } from './capabilities/field'
export { BaseSized } from './capabilities/sized'
export { BaseDataState, type DataStateListener, type DataStateName, type SettleState } from './capabilities/data-state'
export { BaseOverlay, type OverlayListener } from './capabilities/overlay'
export { BaseNotice, type NoticeItem, type NoticeType } from './capabilities/notice'
export { BaseLabeled, type LabelPosition } from './capabilities/labeled'
export { BaseValidatable, type Validator } from './capabilities/validatable'
export {
  assertCapabilityGraph,
  CAPABILITY_MANIFEST,
  validateCapabilityGraph,
  type CapabilityProblem,
  type CapabilityProblemKind,
} from './capabilities/manifest'

export { BasePersistedState, type PersistedRemoteSaver, type PersistedStorage } from './capabilities/persisted-state'
export {
  BaseWizard,
  type WizardResult,
  type WizardStep,
  type WizardValidation,
  type WizardValidatorResult,
} from './capabilities/wizard'
export { BaseSelection, type SelectionKey, type SelectionMode, type SelectionSummary } from './capabilities/selection'
export {
  BaseBulkAction,
  type BulkActionContext,
  type BulkActionDef,
  type BulkActionPhase,
  type BulkActionProgress,
  type BulkActionResult,
} from './capabilities/bulk-action'
export { BaseTheme, type BrandConfig, type ResolvedTheme, type ThemeMode } from './capabilities/theme'
export { BaseTenant, type TenantSummary, type TenantSwitchPhase, type TenantSwitchSteps } from './capabilities/tenant'
export { BasePrintTemplate, type PrintBrand, type PrintContext } from './capabilities/print-template'
export {
  BasePrint,
  PRINT_JOB_PLACEHOLDER,
  type PrintBatchMode,
  type PrintJobHandler,
  type PrintJobPayload,
  type PrintJobResult,
  type PrintJobs,
  type PrintPhase,
  type PrintProgress,
} from './capabilities/print'
export {
  BasePermissionConfig,
  type PermissionCodesHandler,
  type PermissionJobs,
  type PermissionLoadHandler,
  type PermissionPhase,
  type PermissionSubmitHandler,
  type PermissionSubmitResult,
} from './capabilities/permission-config'
export { BaseMounted, type MountListener } from './capabilities/mounted'
export { BaseDesignToken, type DesignTokens, type ThemeListener } from './capabilities/design-token'
export { BaseClickable } from './capabilities/interactive'
export { BaseDragDrop, type DragListener, type DragPayload, type DragPhase } from './capabilities/drag-drop'
export { BaseTabs, type TabItem } from './capabilities/tabs'
export { BaseLocale, type LocaleFormatContext } from './capabilities/locale'
export { BaseAccess } from './capabilities/access'
export { BaseModuleContext, type ModuleContext, type ModuleContextKey } from './capabilities/module-context'

export { BaseAsyncTask, type TaskExecutor, type TaskProgress, type TaskStatus } from './capabilities/async-task'
export { BaseUploadEngine, type Uploader } from './capabilities/upload-engine'
export { BaseEditorKernel, type EditorMode } from './capabilities/editor-kernel'
export { BaseOptionSource, type OptionItem } from './capabilities/option-source'
export { BasePresignedUrl, type PresignedResult } from './capabilities/presigned-url'
export { BaseWatermark } from './capabilities/watermark'
export { BaseUserDisplay, type UserDisplayInfo, type UserStatus } from './capabilities/user-display'
export { BaseDynamicRoutes, type RouteNode } from './capabilities/dynamic-routes'
export { BaseFormMeta } from './capabilities/form-meta'
export { BaseFormPage, type FormMode } from './capabilities/form-page'

export { BaseInput } from './capabilities/input'
export { BaseDisplay } from './capabilities/display'
export { BaseTable, type SortSpec } from './capabilities/table'
export { BaseList } from './capabilities/list'
export { BaseTreeData, type TreeNode } from './capabilities/tree-data'
export { BaseModalShell } from './capabilities/modal-shell'
export { BaseFormContainer } from './capabilities/form-container'
export { BaseContainer } from './capabilities/container'
export { BaseLayout } from './capabilities/layout'
export { BaseMediaContent, type MediaState } from './capabilities/media'
export { BaseFeedback, type FeedbackState } from './capabilities/feedback'
export { BaseNotification, type NotificationItem } from './capabilities/notification'
export { BaseColumnConfig, type ColumnState } from './capabilities/column-config'
export { BaseQueryScheme, type QueryCondition, type QueryScheme } from './capabilities/query-scheme'
export { BaseFieldShell } from './capabilities/field-shell'
export { BaseFieldPerm, type FieldPermission } from './capabilities/field-perm'

export {
  EMPTY_PLACEHOLDER,
  formatAmount,
  formatDate,
  formatDateTime,
  formatDuration,
  formatFileSize,
  formatNumber,
  formatPercent,
  formatRelativeTime,
  mask,
  type FormatContext,
} from './domain/format'
export { amount, codePattern, email, lengthRange, numberRange, phone, required, url } from './domain/validators'
export { evaluatePermission, type PermissionMode } from './domain/permission'
export {
  PERMISSION_ERROR_TARGETS,
  PERMISSION_GRANT_CODE,
  PERMISSION_PLACEHOLDER_TEXT,
  PERMISSION_SUBJECT_LIMIT,
  PERMISSION_TABS,
  applyPermissionCheck,
  bindSubject,
  collectDataScopes,
  collectFieldEntries,
  collectPayload,
  deriveGranted,
  deriveIdempotencyKey,
  findFieldMismatch,
  findFieldPerm,
  findPermissionNode,
  flattenPermissionTree,
  isGrantable,
  normalizeFieldPerms,
  payloadKey,
  resolveCheckState,
  resolveErrorCode,
  resolveErrorTarget,
  setDataScope,
  setFieldPerm,
  unbindSubject,
  type DataScopeEntry,
  type DataScopeRow,
  type FieldPermCell,
  type FieldPermEntry,
  type FieldPermInputCell,
  type FieldPermInputRow,
  type FieldPermRow,
  type FlatPermissionNode,
  type PermissionCheckState,
  type PermissionErrorTarget,
  type PermissionGranted,
  type PermissionNode,
  type PermissionNodeType,
  type PermissionPayload,
  type PermissionSnapshot,
  type PermissionSubject,
  type PermissionSubjectType,
  type PermissionTab,
  type SubjectBindResult,
} from './domain/permission-config'
export { resolveToken } from './domain/token'
export {
  DEFAULT_BRAND_PRIMARY,
  darken,
  deriveBrandTokens,
  isValidColor,
  lighten,
  luminance,
  mixColor,
  normalizeBrand,
  parseColor,
  resolveThemeMode,
  toHex,
  type BrandTokenMap,
  type RgbColor,
  type ThemeResolveInput,
} from './domain/brand'
export {
  MAX_DECIMAL_PRECISION,
  compareDecimal,
  fromMinorUnits,
  isDecimal,
  isDecimalInRange,
  normalizeDecimal,
  sanitizePrecision,
  toMinorUnits,
  type DecimalRangeOptions,
} from './domain/decimal'
export { computeVirtualRange, type VirtualRange, type VirtualRangeOptions } from './domain/virtual-range'
export {
  PLACEHOLDER_MENU,
  filterMenuByKeyword,
  filterMenuByPermission,
  findMenuByPath,
  flattenMenu,
  toRouteNodes,
  type MenuNode,
} from './domain/menu'
export {
  PREFERENCE_DEFAULTS,
  PREFERENCE_KEYS,
  applyPreferenceDefaults,
  diffPreferences,
  isPreferenceEnabled,
  isPreferenceVisible,
  mergePreferences,
  readPreferenceValue,
  resolvePreferenceDefaults,
  sanitizePreferences,
  writePreferenceValue,
  type PreferenceKey,
  type PreferencePolicy,
  type PreferencePolicyMap,
  type PreferenceValues,
} from './domain/preference'

export {
  PAPER_SIZES,
  PRINT_MISSING_TEXT,
  PRINT_STYLE_VARS,
  buildPrintPages,
  computeRowsPerPage,
  distributeFields,
  formatCellValue,
  formatPageFooter,
  paginateRows,
  resolvePaperSize,
  resolvePrintTone,
  resolveRowsPerPage,
  sumNumeric,
  type BuildPagesInput,
  type PageFooterInput,
  type PaperName,
  type PaperOrientation,
  type PaperSize,
  type PrintCellFormat,
  type PrintColumnDef,
  type PrintData,
  type PrintFieldDef,
  type PrintPage,
  type PrintRowData,
  type PrintStyleVar,
  type PrintTemplateDef,
  type PrintTone,
  type PrintToneResolve,
  type RowCapacityInput,
} from './domain/print'

export {
  type LoadedModule,
  type ModuleDefinition,
  type ModuleHostContext,
  type ModuleLoader,
  type ModuleManifest,
  type ModuleRegistration,
  type ModuleRouteDeclaration,
} from './module/types'
export { MODULE_NAME_PATTERN, defineModule } from './module/define'

export {
  ComponentProvider,
  ComponentRegistry,
  FieldRendererProvider,
  FieldRendererRegistry,
  IconProvider,
  IconRegistry,
  ICON_KEY_PATTERN,
  REGISTRY_KEY_PATTERN,
  RouteMenuProvider,
  RouteMenuRegistry,
  WorkbenchCardProvider,
  WorkbenchCardRegistry,
  assertIconKey,
  assertNamespacedKey,
  createRegistries,
  schemaError,
  type FrontendRegistries,
  type IconProviderOptions,
} from './registries'
export { LocalModuleLoader } from './module/loader'

export { BaseApi, type HttpMethod } from './contracts/api'
export {
  configureRequestAdapter,
  getRequestAdapter,
  request,
  type ApiResponse,
  type PageResponse,
  type RequestAdapter,
  type RequestConfig,
} from './contracts/request'
export { BaseDataObject } from './contracts/data-object'
export { BaseEntity } from './contracts/entity'
export { BasePageQuery, type SortOrder } from './contracts/page-query'
export { stableStringify } from './domain/serialize'
