/**
 * `@bms/ui-ep`：PC 渲染插件入口（Element Plus 组件实现）。
 *
 * 具体组件按族分目录（`src/components/<族>/`）；组合式落 `src/composables/`。
 */

export { default as EmptyState, type EmptyStateType } from './components/feedback/EmptyState.vue'
export { default as ErrorPage, type ErrorPageCode } from './components/feedback/ErrorPage.vue'
export { default as LoadingMask } from './components/feedback/LoadingMask.vue'
export { default as SkeletonBlock, type SkeletonBlockVariant } from './components/feedback/SkeletonBlock.vue'
export { default as AspectRatioContainer } from './components/container/AspectRatioContainer.vue'
export { default as AutoHeightContainer } from './components/container/AutoHeightContainer.vue'
export { default as FullscreenContainer } from './components/container/FullscreenContainer.vue'
export { default as LazyContainer } from './components/container/LazyContainer.vue'
export { default as ScrollContainer } from './components/container/ScrollContainer.vue'
export { default as StatusContainer, type StatusContainerState } from './components/container/StatusContainer.vue'
export { default as VirtualListContainer } from './components/container/VirtualListContainer.vue'
export { default as SectionContainer } from './components/container/SectionContainer.vue'
export {
  default as AuditDiff,
  type AuditChainStatus,
  type AuditFieldDiff,
  type AuditRecord,
} from './components/display/AuditDiff.vue'
export { default as ChartRenderer } from './components/chart/ChartRenderer.vue'
export { default as ChartCard, type ChartType } from './components/chart/ChartCard.vue'
export {
  default as DataTable,
  type DataTableCellChange,
  type DataTableColumn,
  type DataTableSort,
} from './components/data/DataTable.vue'
export {
  default as QueryFilter,
  type QueryFilterSearchPayload,
} from './components/data/QueryFilter.vue'
export {
  default as StatusTag,
  type StatusTagSemantic,
  type StatusTagShape,
} from './components/data/StatusTag.vue'
export { default as DescriptionList, type DescGroup, type DescItem, type DescItemType } from './components/data/DescriptionList.vue'
export { default as MetricCard } from './components/data/MetricCard.vue'
export {
  default as FilePreview,
  type PreviewErrorReason,
  type PreviewFile,
  type PreviewKind,
} from './components/display/FilePreview.vue'
export { default as GlobalSearch } from './components/search/GlobalSearch.vue'
// 搜索对外类型经核心领域模块统一导出（保持既有公开名）。
export { type SearchDomain, type SearchGroup, type SearchHit } from '@bms/core'
export { default as SearchEntry } from './components/search/SearchEntry.vue'
export { default as SearchPalette } from './components/search/SearchPalette.vue'
export { default as SearchHitItem } from './components/search/SearchHitItem.vue'
export { default as SearchLogTab } from './components/search/SearchLogTab.vue'
export { default as SearchFileTab } from './components/search/SearchFileTab.vue'
export { default as NoticeList, type NoticeItem, type NoticeType } from './components/notice/NoticeList.vue'
export { default as NoticeMessageItem } from './components/notice/NoticeMessageItem.vue'
export { default as NoticeBell } from './components/notice/NoticeBell.vue'
export { default as NoticeDetail } from './components/notice/NoticeDetail.vue'
export { default as QrCode, type QrLevel, type QrStatus } from './components/display/QrCode.vue'
export { default as QuickEntry, type QuickEntryItem } from './components/display/QuickEntry.vue'
export { default as UserAvatar, type AvatarSize } from './components/display/UserAvatar.vue'
export { default as UserInfo } from './components/display/UserInfo.vue'
export { default as WatermarkOverlay } from './components/display/WatermarkOverlay.vue'
export { default as PermissionConfig } from './components/interaction/PermissionConfig.vue'
// 权限配置对外类型经核心领域模块统一导出（`SubjectItem` 为既有公开名，映射到核心 `PermissionSubject`）。
export {
  type DataScopeRow,
  type FieldPermRow,
  type PermissionNode,
  type PermissionSubject as SubjectItem,
  type PermissionTab,
} from '@bms/core'
export { default as ApprovalFlow } from './components/approval/ApprovalFlow.vue'
export { default as ApprovalProgress, type ApprovalProgressDirection } from './components/approval/ApprovalProgress.vue'
export { default as ApprovalTimeline } from './components/approval/ApprovalTimeline.vue'
export { default as ApprovalActionPanel, type ApprovalPanelPayload } from './components/approval/ApprovalActionPanel.vue'
// 说明：`ApprovalFlowDiagram` / `ProcessCanvas` 为独立分包懒加载入口（`defineAsyncComponent`），
// 不作为根出口静态导出，否则会被静态引入而使动态导入无法分包。
export {
  default as ProcessModeler,
  type ModelerHistoryItem,
} from './components/approval/ProcessModeler.vue'
export { default as ProcessPalette } from './components/approval/ProcessPalette.vue'
export { default as ProcessProperties } from './components/approval/ProcessProperties.vue'
// 审批与建模的对外类型经核心领域模块统一导出（保持既有公开名）。
export {
  type ApprovalAction,
  type ApprovalAssignee,
  type ApprovalAttachment,
  type ApprovalInstance,
  type ApprovalInstanceStatus,
  type ApprovalNode,
  type ApprovalNodeStatus,
  type ApprovalRecord,
  type ApprovalTask,
  type ApprovalTimelineOrder,
  type ModelerElement,
  type ModelerElementProperties,
  type ModelerElementType,
  type ModelerValidateResult,
} from '@bms/core'
export {
  default as ImportDialog,
  type ImportResult,
  type ImportStep,
} from './components/import-export/ImportDialog.vue'
export { default as ImportErrorReport } from './components/import-export/ImportErrorReport.vue'
// 说明：`ExportProgress` / `ImportDialogBody` 为独立分包懒加载入口（`defineAsyncComponent`），
// 不作为根出口静态导出，否则会被静态引入而使动态导入无法分包。
export {
  default as ExportButton,
  type ExportPayload,
  type ExportScope,
} from './components/import-export/ExportButton.vue'
// 说明：`FormDesignerCanvas` / `FieldPropertyPanel` / `ExtFieldDialog` 为独立分包懒加载入口（`defineAsyncComponent`），
// 不作为根出口静态导出，否则会被静态引入而使动态导入无法分包。
export {
  default as FormDesigner,
  type DesignerBlockAction,
  type DesignerField,
  type DesignerLayer,
  type DesignerLevelType as DesignerLevel,
  type DesignerSection,
  type DesignerSelection,
  type DesignerView,
  type FormLayoutShape as FormLayout,
} from './components/form-design/FormDesigner.vue'
export type { FieldPropertyPatch, SectionPropertyPatch, CanvasPropertyPatch } from './components/form-design/FieldPropertyPanel.vue'
export type { ExtFieldCreated } from './components/form-design/ExtFieldDialog.vue'
export type { DesignerMoveEvent } from './components/form-design/FormDesignerCanvas.vue'
// 说明：`FormRendererBody` 为独立分包懒加载入口（`defineAsyncComponent`），
// 不作为根出口静态导出，否则会被静态引入而使动态导入无法分包。
export {
  default as FormRenderer,
  type FormRenderMode,
  type FormValidateResult,
} from './components/form-render/FormRenderer.vue'
export {
  useBaseFormRenderer,
  type UseBaseFormRendererOptions,
  type UseBaseFormRendererResult,
} from './composables/useBaseFormRenderer'
export {
  MULTIPLE_WIDGETS,
  getFieldWidget,
  resolveFieldComponent,
  resolveFieldComponentByType,
} from './utils/formWidgets'
// 说明：`MessageGrid` 为独立分包懒加载入口（`defineAsyncComponent`），
// 不作为根出口静态导出，否则会被静态引入而使动态导入无法分包。
export {
  default as I18nMessageEditor,
  type I18nChangePayload,
  type I18nLocale,
  type I18nMessageRow,
  type MessageTab,
} from './components/i18n/I18nMessageEditor.vue'
export { default as LocaleList } from './components/i18n/LocaleList.vue'
export { default as MessageFilter } from './components/i18n/MessageFilter.vue'
export {
  useBaseMessageCatalog,
  type UseBaseMessageCatalogOptions,
  type UseBaseMessageCatalogResult,
} from './composables/useBaseMessageCatalog'
export { default as ReportDesigner } from './components/report/ReportDesigner.vue'
export type { ReportChartItem, ReportDataset } from '@bms/core'
export { default as ScreenDesigner, type ScreenPage } from './components/screen/ScreenDesigner.vue'
export type { ScreenComponent, ScreenComponentType } from '@bms/core'
export { default as ScreenPlayer, type ScreenPlayerPage } from './components/screen/ScreenPlayer.vue'
export {
  useBaseScreenDesigner,
  type UseBaseScreenDesignerOptions,
  type UseBaseScreenDesignerResult,
} from './composables/useBaseScreenDesigner'
export {
  useBaseScreenPlayer,
  type UseBaseScreenPlayerOptions,
  type UseBaseScreenPlayerResult,
} from './composables/useBaseScreenPlayer'
export { default as AiAssistant } from './components/ai/AiAssistant.vue'
export { default as AiSessionList } from './components/ai/AiSessionList.vue'
export { default as AiMessageItem } from './components/ai/AiMessageItem.vue'
export { default as AiComposer } from './components/ai/AiComposer.vue'
export { default as AiActionConfirm } from './components/ai/AiActionConfirm.vue'
// 说明：`AiChatPanel` 为独立分包懒加载入口（`defineAsyncComponent`），不作为根出口静态导出。
// AI 助手对外类型经核心领域模块统一导出（保持既有公开名）。
export {
  type AiActionState,
  type AiCitation,
  type AiMessage,
  type AiMessageStatus,
  type AiMode,
  type AiPendingAction,
  type AiRole,
  type AiSession,
} from '@bms/core'
export { default as IconRenderer } from './components/interaction/IconRenderer.vue'
export { default as IconPicker, type IconPickerSize } from './components/interaction/IconPicker.vue'
export { default as IconLibrary, type CustomIcon, type IconSourceGroup } from './components/interaction/IconLibrary.vue'
export {
  default as CodeEditor,
  type EditorDiagnostic,
  type EditorLanguage,
} from './components/interaction/CodeEditor.vue'
export { default as SqlEditor, type SqlValidateResult } from './components/interaction/SqlEditor.vue'
export {
  default as ExpressionEditor,
  type ExpressionTemplate,
  type ExpressionToken,
  type ExpressionValidateResult,
} from './components/interaction/ExpressionEditor.vue'
export { default as CronEditor } from './components/interaction/CronEditor.vue'
export { default as CodeViewer, type ViewerLanguage } from './components/interaction/CodeViewer.vue'
export { default as CaptchaField, type CaptchaKind } from './components/field/CaptchaField.vue'
export { default as ImageCaptcha } from './components/field/ImageCaptcha.vue'
export { default as SliderCaptcha } from './components/field/SliderCaptcha.vue'
export { default as SmsCaptcha } from './components/field/SmsCaptcha.vue'
export { default as AmountField } from './components/field/AmountField.vue'
export { default as CascadeField, type CascadeOption, type CascadeValue } from './components/field/CascadeField.vue'
export { default as EnumField, type EnumFieldForm, type EnumFieldValue } from './components/field/EnumField.vue'
export { default as InlineSwitchCell } from './components/field/InlineSwitchCell.vue'
export { default as NumberField } from './components/field/NumberField.vue'
export { default as RichTextField, type RichTextFieldMode } from './components/field/RichTextField.vue'
export { default as SwitchField } from './components/field/SwitchField.vue'
export { default as TagInputField, type TagColorMap } from './components/field/TagInputField.vue'
export { default as TransferField, type TransferItem, type TransferValue } from './components/field/TransferField.vue'
export {
  default as TreeSelectField,
  type TreeFieldNode,
  type TreeFieldValue,
} from './components/field/TreeSelectField.vue'
export { default as DateTimeField, type DateTimeKind, type DateTimeValue } from './components/field/DateTimeField.vue'
export { default as DictSelectField, type DictFieldValue } from './components/field/DictSelectField.vue'
export { default as FileUploadField, type UploadFieldItem } from './components/field/FileUploadField.vue'
export { default as ImageUploadField } from './components/field/ImageUploadField.vue'
export { default as FileListField } from './components/field/FileListField.vue'
export { default as ImageCropDialog } from './components/field/ImageCropDialog.vue'
export { default as OrgSelectField, type OrgFieldValue } from './components/field/OrgSelectField.vue'
export { default as UserSelectField, type UserFieldValue } from './components/field/UserSelectField.vue'
export { default as PostSelectField, type PostFieldValue } from './components/field/PostSelectField.vue'
export { default as DeptTreeSelectField, type DeptFieldValue } from './components/field/DeptTreeSelectField.vue'
export {
  default as OrgCompositePicker,
  type OrgCompositeValue,
} from './components/field/OrgCompositePicker.vue'
export { default as DictCascaderField, type DictCascadeValue } from './components/field/DictCascaderField.vue'
export { default as DictLabel } from './components/field/DictLabel.vue'
export { default as DictAdvancedQuery } from './components/field/DictAdvancedQuery.vue'
export { default as ConditionGroupBuilder } from './components/field/ConditionGroupBuilder.vue'
export { default as CheckboxInput, type CheckboxForm, type CheckboxValue } from './components/input/CheckboxInput.vue'
export { default as NumberInput } from './components/input/NumberInput.vue'
export { default as RadioInput, type RadioForm, type RadioValue } from './components/input/RadioInput.vue'
export { default as SelectInput, type SelectValue } from './components/input/SelectInput.vue'
export { default as SwitchInput } from './components/input/SwitchInput.vue'
export { type InputOption, type InputOptionGroup, type InputOptions } from './components/input/types'
export { default as PasswordInput, type PasswordStrength } from './components/input/PasswordInput.vue'
export { default as TextareaInput } from './components/input/TextareaInput.vue'
export { default as TextInput } from './components/input/TextInput.vue'
export { default as CollapsePanel } from './components/layout/CollapsePanel.vue'
export { default as DualTabs } from './components/layout/DualTabs.vue'
export { default as FormLayoutShell } from './components/layout/FormLayoutShell.vue'
export { default as MainLayout } from './components/layout/MainLayout.vue'
export { default as PageContainer, type BreadcrumbItem } from './components/layout/PageContainer.vue'
export { default as SideMenu } from './components/layout/SideMenu.vue'
export { default as SideMenuItem } from './components/layout/SideMenuItem.vue'
export { default as TabNavBar } from './components/layout/TabNavBar.vue'
export { default as TabNavContextMenu, type TabNavAction } from './components/layout/TabNavContextMenu.vue'
export { default as CollapsePanelGroup } from './components/layout/CollapsePanelGroup.vue'
export { default as ContentTabs, type ContentTabItem } from './components/layout/ContentTabs.vue'
export { default as GridItem } from './components/layout/GridItem.vue'
export { default as GridLayout, type GridAlign, type GridJustify } from './components/layout/GridLayout.vue'
export { default as LayoutCard, type CardPadding } from './components/layout/LayoutCard.vue'
export { default as ModuleAreaOutlet } from './components/layout/ModuleAreaOutlet.vue'
export { default as SpacingDivider, type SpacingSize } from './components/layout/SpacingDivider.vue'
export { default as SplitPane, type SplitDirection } from './components/layout/SplitPane.vue'
export { default as TreeMasterDetail, type MasterTreeNode } from './components/layout/TreeMasterDetail.vue'
export { default as ConfirmDialog } from './components/modal/ConfirmDialog.vue'
export { default as FormDialog } from './components/modal/FormDialog.vue'
export { default as FormDrawer } from './components/modal/FormDrawer.vue'
export { useConfirm, type ConfirmOptions, type ConfirmState } from './composables/useConfirm'
export { useFeedback, type UseFeedbackResult } from './composables/useFeedback'
export {
  useBaseContainer,
  type UseBaseContainerOptions,
  type UseBaseContainerResult,
} from './composables/useBaseContainer'
export { useBaseLayout, type UseBaseLayoutOptions, type UseBaseLayoutResult } from './composables/useBaseLayout'
export {
  useModuleArea,
  type ModuleAreaItem,
  type UseModuleAreaOptions,
  type UseModuleAreaResult,
} from './composables/useModuleArea'
export { useBaseDisplay, type UseBaseDisplayResult } from './composables/useBaseDisplay'
export { useBaseTable, type UseBaseTableOptions, type UseBaseTableResult } from './composables/useBaseTable'
export {
  useBaseQueryScheme,
  type UseBaseQuerySchemeOptions,
  type UseBaseQuerySchemeResult,
} from './composables/useBaseQueryScheme'
export {
  useDisplayPlaceholder,
  type UseDisplayPlaceholderOptions,
  type UseDisplayPlaceholderResult,
} from './composables/useDisplayPlaceholder'
export { useBaseDataState, type UseBaseDataStateResult } from './composables/useBaseDataState'
export {
  useInteractionPlaceholder,
  type UseInteractionPlaceholderOptions,
  type UseInteractionPlaceholderResult,
} from './composables/useInteractionPlaceholder'
export {
  useBaseUploadEngine,
  type UseBaseUploadEngineOptions,
  type UseBaseUploadEngineResult,
} from './composables/useBaseUploadEngine'
export {
  useBaseAsyncTask,
  type UseBaseAsyncTaskOptions,
  type UseBaseAsyncTaskResult,
} from './composables/useBaseAsyncTask'
export { useBaseDragDrop, type UseBaseDragDropResult } from './composables/useBaseDragDrop'
export { useBaseFormMeta, type UseBaseFormMetaOptions, type UseBaseFormMetaResult } from './composables/useBaseFormMeta'
export { useBaseLocale, type UseBaseLocaleOptions, type UseBaseLocaleResult } from './composables/useBaseLocale'
export {
  useBaseOptionSource,
  type UseBaseOptionSourceOptions,
  type UseBaseOptionSourceResult,
} from './composables/useBaseOptionSource'
export {
  useBaseSubscription,
  type SubscriptionHandler,
  type UseBaseSubscriptionResult,
} from './composables/useBaseSubscription'
export {
  getCodeModuleLoadCount,
  loadCodeModules,
  resetCodeModuleCache,
  useCodeKernel,
  type CodeModules,
  type UseCodeKernelResult,
} from './composables/useCodeKernel'
export {
  escapeHtml,
  getHighlightLoadCount,
  highlightCode,
  HIGHLIGHT_LANGUAGES,
  loadHighlight,
  resetHighlightCache,
  useHighlight,
  type UseHighlightResult,
} from './composables/useHighlight'
export { getIconRegistry, resetIconRegistry, setIconRegistry, useIconRegistry } from './composables/useIconRegistry'
export { ensureOfficialIcons, getOfficialIconsLoadCount } from './icons/official'
export {
  CRON_TEMPLATES,
  describeCron,
  formatCron,
  parseCron,
  validateCron,
  type CronFields,
  type CronTemplate,
  type CronValidateResult,
} from './utils/cron'
export { useBaseTreeData, type UseBaseTreeDataOptions, type UseBaseTreeDataResult } from './composables/useBaseTreeData'
export { useBaseAccess, type UseBaseAccessResult } from './composables/useBaseAccess'
export { useBaseUserDisplay, type UseBaseUserDisplayResult } from './composables/useBaseUserDisplay'
export {
  useBaseNotification,
  type UseBaseNotificationOptions,
  type UseBaseNotificationResult,
} from './composables/useBaseNotification'
export {
  useBaseAiAssistant,
  type UseBaseAiAssistantOptions,
  type UseBaseAiAssistantResult,
} from './composables/useBaseAiAssistant'
export { useBaseSearch, type UseBaseSearchOptions, type UseBaseSearchResult } from './composables/useBaseSearch'
export {
  useBaseOrgSelect,
  type OrgSelectValue,
  type UseBaseOrgSelectOptions,
  type UseBaseOrgSelectResult,
} from './composables/useBaseOrgSelect'
export { debounce, type DebouncedFunction } from './utils/debounce'
export { createHttpOrgSource, orgSourceRegistry, registerOrgSource } from './utils/orgSource'
export {
  useBaseCaptcha,
  type UseBaseCaptchaOptions,
  type UseBaseCaptchaResult,
} from './composables/useBaseCaptcha'
export { createHttpCaptchaSource, captchaSourceRegistry, registerCaptchaSource } from './utils/captchaSource'
export {
  useBaseDictSelect,
  type DictSelectValue,
  type UseBaseDictSelectOptions,
  type UseBaseDictSelectResult,
} from './composables/useBaseDictSelect'
export {
  useBaseDictQuery,
  type UseBaseDictQueryOptions,
  type UseBaseDictQueryResult,
} from './composables/useBaseDictQuery'
export { createHttpDictSource, dictSourceRegistry, registerDictSource } from './utils/dictSource'
export { localStorageDictChannel } from './utils/dictStorage'
export { createDictTranslator } from './utils/dictTranslator'
export {
  useBaseFileUpload,
  type FileUploadValue,
  type UseBaseFileUploadOptions,
  type UseBaseFileUploadResult,
} from './composables/useBaseFileUpload'
export { createHttpUploadTransport, registerUploadTransport, uploadTransportRegistry } from './utils/uploadTransport'
export { hashFile, type FileHashWorkerRequest, type FileHashWorkerResponse } from './utils/fileHash'
export {
  compressImage,
  createObjectUrl,
  planImageCompress,
  readImageDimension,
  revokeObjectUrl,
  type ImageCompressRequest,
  type ImageProcessWorkerRequest,
  type ImageProcessWorkerResponse,
} from './utils/imageProcess'
export { mountImageCropper, type ImageCropOptions, type ImageCropperHandle } from './utils/imageCrop'
export { escapeSearchText, highlightHit, highlightKeyword, sanitizeHighlight } from './utils/searchHighlight'
export {
  createHttpSearchEngine,
  registerSearchEngine,
  searchEngineRegistry,
} from './utils/searchEngine'
export { createSseStreamAdapter, type SseStreamAdapterOptions } from './utils/aiStream'
export { chartEngineRegistry, registerChartEngine } from './utils/chartEngine'
export { loadMarked, renderAiMarkdown, resetMarkedCache, splitAiContent } from './utils/aiMarkdown'
export {
  startUnreadPolling,
  onVisibilityChange,
  type UnreadPollingOptions,
  type UnreadPollingHandle,
} from './utils/notificationRealtime'
export {
  canFullscreen,
  enterFullscreen,
  exitFullscreen,
  fullscreenElement,
  isFullscreen,
  onFullscreenChange,
} from './utils/fullscreen'
export { isDocumentHidden } from './utils/visibility'
export {
  observeIntersection,
  observeResize,
  onWindowResize,
  supportsIntersection,
  supportsResize,
  viewportWidth,
} from './utils/observe'
export { matchesMedia, onMediaChange, prefersDark, prefersReducedMotion, supportsMediaQuery } from './utils/media'
export { onGlobalKeydown, startPointerDrag } from './utils/keyboard'
export { readCssVar } from './utils/cssVar'
export {
  createNotificationChannel,
  type NotificationChannelMessage,
  type NotificationChannelHandle,
} from './utils/notificationChannel'
export { useBaseWatermark, type UseBaseWatermarkResult } from './composables/useBaseWatermark'
export { useBasePresignedUrl, type UseBasePresignedUrlResult } from './composables/useBasePresignedUrl'
export {
  useRichTextKernel,
  type UseRichTextKernelOptions,
  type UseRichTextKernelResult,
} from './composables/useRichTextKernel'
export { RICH_TEXT_ALLOWED_ATTR, RICH_TEXT_ALLOWED_TAGS, sanitizeHtml, sanitizeSvg, sanitizeToText } from './utils/sanitizeHtml'
export { diffKind, formatDiffValue, inferValueType, type AuditDiffKind, type AuditValueType } from './utils/auditDiff'
export {
  useFieldPlaceholder,
  type UseFieldPlaceholderOptions,
  type UseFieldPlaceholderResult,
} from './composables/useFieldPlaceholder'
export { useBaseInput, type UseBaseInputOptions, type UseBaseInputResult } from './composables/useBaseInput'
export { useBaseField, type UseBaseFieldOptions, type UseBaseFieldResult } from './composables/useBaseField'
export {
  useBasePersistedState,
  type UseBasePersistedStateOptions,
  type UseBasePersistedStateResult,
} from './composables/useBasePersistedState'
export {
  useBaseDesignToken,
  type UseBaseDesignTokenOptions,
  type UseBaseDesignTokenResult,
} from './composables/useBaseDesignToken'
export {
  DEFAULT_BREAKPOINTS,
  useResponsive,
  type ResponsiveBreakpoint,
  type ResponsiveBreakpoints,
  type UseResponsiveOptions,
  type UseResponsiveResult,
} from './composables/useResponsive'
export {
  useFormShell,
  type DetailRecord,
  type UseFormShellOptions,
  type UseFormShellResult,
} from './composables/useFormShell'
export { useSideMenu, type UseSideMenuOptions, type UseSideMenuResult } from './composables/useSideMenu'
export { useTabNav, type TabNavItem, type UseTabNavOptions, type UseTabNavResult } from './composables/useTabNav'
export { useModalShell, type UseModalShellResult } from './composables/useModalShell'
export { useFormModal, type UseFormModalOptions, type UseFormModalResult } from './composables/useFormModal'
export {
  useBaseFormPage,
  type FormMode,
  type UseBaseFormPageOptions,
  type UseBaseFormPageResult,
} from './composables/useBaseFormPage'
export { default as StepWizard } from './components/interaction/StepWizard.vue'
export { default as WizardStep } from './components/interaction/WizardStep.vue'
export { default as PreferencePanel } from './components/interaction/PreferencePanel.vue'
export { default as PreferenceGroup } from './components/interaction/PreferenceGroup.vue'
export { default as BulkActionBar } from './components/interaction/BulkActionBar.vue'
export { default as ThemeSwitch } from './components/interaction/ThemeSwitch.vue'
export { default as BrandProvider } from './components/interaction/BrandProvider.vue'
export { default as TenantSwitcher } from './components/interaction/TenantSwitcher.vue'
export { default as TenantList } from './components/interaction/TenantList.vue'
export {
  useBaseSelection,
  type UseBaseSelectionOptions,
  type UseBaseSelectionResult,
} from './composables/useBaseSelection'
export {
  useBaseBulkAction,
  type UseBaseBulkActionOptions,
  type UseBaseBulkActionResult,
} from './composables/useBaseBulkAction'
export { useBaseTheme, type UseBaseThemeOptions, type UseBaseThemeResult } from './composables/useBaseTheme'
export { useBaseTenant, type UseBaseTenantOptions, type UseBaseTenantResult } from './composables/useBaseTenant'
export { useBaseWizard, type UseBaseWizardOptions, type UseBaseWizardResult } from './composables/useBaseWizard'
export { usePreferences, type UsePreferencesOptions, type UsePreferencesResult } from './composables/usePreferences'
export {
  DEFAULT_PREFERENCE_GROUPS,
  resolvePreferenceGroups,
  type PreferenceControl,
  type PreferenceGroupDef,
  type PreferenceItem,
  type PreferenceOption,
} from './utils/preferenceItems'
export { default as PrintSheet } from './components/print/PrintSheet.vue'
export { default as PrintPreview } from './components/print/PrintPreview.vue'
export { default as PrintButton, type PrintAction } from './components/print/PrintButton.vue'
export {
  useBasePrintTemplate,
  type UseBasePrintTemplateOptions,
  type UseBasePrintTemplateResult,
} from './composables/useBasePrintTemplate'
export { useBasePrint, type UseBasePrintOptions, type UseBasePrintResult } from './composables/useBasePrint'
export { invokeBrowserPrint } from './utils/printWindow'
export { default as PermissionTree } from './components/interaction/PermissionTree.vue'
export { default as FieldPermMatrix } from './components/interaction/FieldPermMatrix.vue'
export { default as FieldPermCell } from './components/interaction/FieldPermCell.vue'
export { default as DataScopePanel } from './components/interaction/DataScopePanel.vue'
export { default as SubjectBinding } from './components/interaction/SubjectBinding.vue'
export {
  useBasePermissionConfig,
  type UseBasePermissionConfigOptions,
  type UseBasePermissionConfigResult,
} from './composables/useBasePermissionConfig'
export {
  useBaseFieldPerm,
  type UseBaseFieldPermOptions,
  type UseBaseFieldPermResult,
} from './composables/useBaseFieldPerm'
export {
  useBaseFileDownload,
  type UseBaseFileDownloadOptions,
  type UseBaseFileDownloadResult,
} from './composables/useBaseFileDownload'
export {
  useBaseImportFlow,
  type UseBaseImportFlowOptions,
  type UseBaseImportFlowResult,
} from './composables/useBaseImportFlow'
export {
  useBaseExportFlow,
  type UseBaseExportFlowOptions,
  type UseBaseExportFlowResult,
} from './composables/useBaseExportFlow'
export { triggerDownload, type TriggerDownloadInput } from './utils/downloadFile'
export {
  toDesignerDrop,
  toDragPayload,
  type SortableMoveInput,
  type SortablePhaseInput,
} from './utils/dragSortable'
export {
  useBaseFormDesigner,
  type UseBaseFormDesignerOptions,
  type UseBaseFormDesignerResult,
} from './composables/useBaseFormDesigner'
export {
  useBaseApprovalFlow,
  type UseBaseApprovalFlowOptions,
  type UseBaseApprovalFlowResult,
} from './composables/useBaseApprovalFlow'
export {
  useBaseProcessModeler,
  type UseBaseProcessModelerOptions,
  type UseBaseProcessModelerResult,
} from './composables/useBaseProcessModeler'
export {
  useBaseChart,
  type UseBaseChartOptions,
  type UseBaseChartResult,
} from './composables/useBaseChart'
export {
  useBaseReportDesigner,
  type UseBaseReportDesignerOptions,
  type UseBaseReportDesignerResult,
} from './composables/useBaseReportDesigner'
export { APPROVAL_ACTION_METAS, approvalActionMeta, type ApprovalActionMeta } from './utils/approvalActions'
export { equivalentBpmnStrong, parseBpmnStrongStructure, type BpmnStrongStructure } from './utils/bpmnRoundTrip'
