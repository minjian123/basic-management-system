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

export {
  BaseAsyncTask,
  type TaskExecutor,
  type TaskPollOutcome,
  type TaskPoller,
  type TaskProgress,
  type TaskStatus,
  type TaskSubmitter,
} from './capabilities/async-task'
export { BaseUploadEngine, type UploadProgressReporter, type Uploader } from './capabilities/upload-engine'
export {
  BaseFileDownload,
  DOWNLOAD_PLACEHOLDER_TEXT,
  type DownloadFetcher,
  type DownloadPhase,
  type DownloadRequest,
  type DownloadResult,
  type DownloadSource,
  type DownloadTrigger,
} from './capabilities/file-download'
export {
  BaseImportFlow,
  type ImportAbortSignal,
  type ImportDownloadHandler,
  type ImportDownloadInput,
  type ImportExecuteHandler,
  type ImportJobs,
  type ImportPhase,
  type ImportStep,
} from './capabilities/import-flow'
export {
  BaseExportFlow,
  type ExportHandler,
  type ExportJobs,
  type ExportPhase,
  type ExportPollHandler,
  type ExportRequest,
  type ExportResult,
} from './capabilities/export-flow'
export {
  BaseFormDesigner,
  type DesignerBlockAction,
  type DesignerDropInput,
  type DesignerExtFieldResult,
  type DesignerJobs,
  type DesignerPhase,
  type DesignerSaveResult,
  type DesignerSnapshot,
} from './capabilities/form-designer'
export {
  BaseFormRenderer,
  type FormRendererJobs,
  type RecordSnapshot,
  type RendererPhase,
  type SubmitResult,
} from './capabilities/form-renderer'
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
  formatCompactTimestamp,
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
  normalizeDataScopes,
  normalizeFieldPerms,
  payloadKey,
  resolveCheckState,
  resolveErrorCode,
  resolveErrorTarget,
  setDataScope,
  setFieldPerm,
  unbindSubject,
  type DataScopeEntry,
  type DataScopeInputRow,
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
  IMPORT_ACCEPT,
  IMPORT_DEFAULT_MAX_SIZE,
  IMPORT_ERROR_DISPLAY_LIMIT,
  IMPORT_ERROR_PAGE_SIZE,
  IMPORT_FILE_ERROR_RANGE,
  IMPORT_PERM,
  IMPORT_PLACEHOLDER_TEXT,
  checkImportFile,
  deriveImportKey,
  errorReportFileName,
  fileExtension,
  isFileLevelError,
  normalizeAccept,
  normalizeImportResult,
  paginateImportErrors,
  resolveImportErrorText,
  resolveImportSummary,
  templateFileName,
  type ImportErrorPage,
  type ImportErrorRow,
  type ImportErrorText,
  type ImportFailReason,
  type ImportFileCheck,
  type ImportFileMeta,
  type ImportResult,
  type ImportResultInput,
  type ImportSummaryState,
} from './domain/import'
export {
  EXPORT_EMPTY_TEXT,
  EXPORT_FILE_EXT,
  EXPORT_PERM,
  EXPORT_PLACEHOLDER_TEXT,
  EXPORT_PLAIN_PERM,
  EXPORT_QUEUED_TEXT,
  canExportPlain,
  exportErrorMessage,
  exportFileName,
  normalizeExportParams,
  normalizeSelectedIds,
  resolveExportDecision,
  resolveExportMode,
  type ExportDecision,
  type ExportDecisionInput,
  type ExportMode,
  type ExportQueryParams,
  type ExportScope,
} from './domain/export'

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
export {
  DEFAULT_LABEL_WIDTH,
  DEFAULT_LAYOUT_COLUMNS,
  DEFAULT_SECTION_KEY,
  DESIGNER_EMPTY_HINT,
  DESIGNER_PLACEHOLDER_TEXT,
  DETAIL_WIDTH_RANGE,
  EXT_COLUMN_PREFIX,
  EXT_FIELD_TYPES,
  EXT_OPTION_TYPES,
  FORMDESIGN_PERM,
  FORMDESIGN_VIEW_PERM,
  LABEL_WIDTH_RANGE,
  SECTION_COLUMNS,
  SECTION_FIELD_HINT,
  SECTION_KEY_PREFIX,
  addSection,
  canDragField,
  checkExtField,
  collectFieldKeys,
  countLayoutFields,
  defaultLayout,
  emptyLayout,
  extColumnName,
  extFieldNeedsOptions,
  findDisabledFields,
  findDuplicateFields,
  findSection,
  findUnknownFields,
  hasField,
  insertField,
  isLayoutDirty,
  isLayoutEmpty,
  layoutEqual,
  locateField,
  moveField,
  newSectionKey,
  normalizeColumns,
  normalizeFieldRef,
  normalizeFieldRefs,
  normalizeLayout,
  normalizeSelection,
  removeField,
  removeSection,
  renameSection,
  resolveEffectiveLayout,
  resolveExtDdlStatus,
  resolveLayoutForLevel,
  resolveLevelReadOnly,
  resolveRestoreTarget,
  setDetailColumns,
  setLabelPosition,
  setLabelWidth,
  setQueryFields,
  setSectionColumns,
  toRenderMetadata,
  toggleColSpan,
  validateLayout,
  type DesignerLevel,
  type DesignerSelection,
  type ExtDdlStatus,
  type ExtFieldCheck,
  type ExtFieldDraft,
  type ExtFieldOption,
  type FieldGroup,
  type FieldRenderAttrs,
  type FieldRule,
  type FieldStatus,
  type FormField,
  type FormLayout,
  type FormLayoutInput,
  type FormLayoutLevels,
  type LayoutDetailColumnInput,
  type LayoutFieldRefInput,
  type LayoutGroupInput,
  type LayoutLabelPosition,
  type LayoutSectionInput,
  type LayoutDictAdvanced,
  type LayoutDetail,
  type LayoutDetailColumn,
  type LayoutEffective,
  type LayoutFieldRef,
  type LayoutGroup,
  type LayoutIssueKind,
  type LayoutMain,
  type LayoutQuery,
  type LayoutRestoreTarget,
  type LayoutSection,
  type LayoutValidationIssue,
  type LayoutValidationResult,
  type SectionColumns,
} from './domain/form-layout'
export {
  DEFAULT_DETAIL_COLUMNS,
  DEFAULT_DETAIL_PAGE_SIZE,
  EMPTY_TEXT,
  FIELD_WIDGETS,
  FIELD_WIDGET_MAP,
  FORM_RENDER_PERM,
  MASK_TEXT,
  RENDERER_EMPTY_HINT,
  RENDERER_FALLBACK_HINT,
  RENDERER_PLACEHOLDER_TEXT,
  RENDERER_UNKNOWN_TYPE_HINT,
  buildFieldPlan,
  buildRenderPlan,
  buildSubmitPayload,
  compileFieldRules,
  countPlanFields,
  displayFieldText,
  fallbackDetailColumns,
  isKnownFieldType,
  isSectionColumnsValid,
  isSubmitAllowed,
  maskFieldText,
  mkFieldRules,
  normalizeDetailRows,
  normalizeDetailSet,
  normalizeField,
  normalizeFieldOverrides,
  normalizeRenderMetadata,
  normalizeRenderMode,
  resolveBaselineEditable,
  resolveFieldRenderState,
  resolveFieldWidget,
  sectionSpan,
  validateDetailRows,
  validateDetails,
  validateFieldValue,
  validateFormData,
  visibleFields,
  type DetailDataSet,
  type DetailRenderError,
  type DetailValidationResult,
  type FieldRenderOverride,
  type FieldRenderState,
  type FormFieldInput,
  type FormRenderError,
  type FormRenderMode,
  type FormValidationResult,
  type FormWidget,
  type RenderDetailColumn,
  type RenderFieldPlan,
  type RenderGroupPlan,
  type RenderMetadataInput,
  type RenderPlan,
  type RenderSectionPlan,
  type SubmitPayload,
} from './domain/form-render'
export { fnv1aHex, stableStringify } from './domain/serialize'
