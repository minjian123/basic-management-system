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
export { default as ChartCard, type ChartType } from './components/display/ChartCard.vue'
export {
  default as DataTable,
  type DataTableColumn,
  type DataTableSort,
} from './components/display/DataTable.vue'
export {
  default as FilePreview,
  type PreviewErrorReason,
  type PreviewFile,
  type PreviewKind,
} from './components/display/FilePreview.vue'
export {
  default as GlobalSearch,
  type SearchDomain,
  type SearchGroup,
  type SearchHit,
} from './components/display/GlobalSearch.vue'
export {
  default as NoticeList,
  type NoticeItem,
  type NoticeType,
} from './components/display/NoticeList.vue'
export { default as QrCode, type QrLevel, type QrStatus } from './components/display/QrCode.vue'
export { default as QuickEntry, type QuickEntryItem } from './components/display/QuickEntry.vue'
export { default as UserAvatar, type AvatarSize } from './components/display/UserAvatar.vue'
export { default as UserInfo } from './components/display/UserInfo.vue'
export { default as WatermarkOverlay } from './components/display/WatermarkOverlay.vue'
export {
  default as PermissionConfig,
  type DataScopeRow,
  type FieldPermRow,
  type PermissionNode,
  type PermissionTab,
  type SubjectItem,
} from './components/interaction/PermissionConfig.vue'
export {
  default as ApprovalFlow,
  type ApprovalAction,
  type ApprovalActionPayload,
  type ApprovalInstance,
  type ApprovalInstanceStatus,
  type ApprovalNode,
  type ApprovalNodeStatus,
  type ApprovalRecord,
  type ApprovalTask,
} from './components/interaction/ApprovalFlow.vue'
export {
  default as ProcessModeler,
  type ModelerElement,
  type ModelerElementType,
  type ModelerValidateResult,
} from './components/interaction/ProcessModeler.vue'
export {
  default as ImportDialog,
  type ImportResult,
  type ImportStep,
} from './components/interaction/ImportDialog.vue'
export {
  default as ExportButton,
  type ExportPayload,
  type ExportScope,
} from './components/interaction/ExportButton.vue'
export {
  default as FormDesigner,
  type DesignerField,
  type DesignerLevel,
  type DesignerSection,
  type DesignerSelection,
  type FormLayout,
} from './components/interaction/FormDesigner.vue'
export {
  default as FormRenderer,
  type FormRenderMode,
  type FormValidateResult,
} from './components/interaction/FormRenderer.vue'
export {
  default as I18nMessageEditor,
  type I18nChangePayload,
  type I18nLocale,
  type I18nMessageRow,
} from './components/interaction/I18nMessageEditor.vue'
export {
  default as ReportDesigner,
  type ReportChartItem,
  type ReportDataset,
} from './components/interaction/ReportDesigner.vue'
export {
  default as ScreenDesigner,
  type ScreenComponent,
  type ScreenComponentType,
  type ScreenPage,
} from './components/interaction/ScreenDesigner.vue'
export { default as ScreenPlayer, type ScreenPlayerPage } from './components/interaction/ScreenPlayer.vue'
export {
  default as AiAssistant,
  type AiCitation,
  type AiMessage,
  type AiMessageStatus,
  type AiMode,
  type AiRole,
  type AiSession,
} from './components/interaction/AiAssistant.vue'
export { default as IconRenderer } from './components/interaction/IconRenderer.vue'
export { default as IconPicker, type IconPickerSize } from './components/interaction/IconPicker.vue'
export {
  default as IconLibrary,
  type CustomIcon,
  type IconSourceGroup,
} from './components/interaction/IconLibrary.vue'
export {
  default as CodeEditor,
  type EditorDiagnostic,
  type EditorLanguage,
} from './components/interaction/CodeEditor.vue'
export {
  default as SqlEditor,
  type SqlValidateResult,
} from './components/interaction/SqlEditor.vue'
export {
  default as ExpressionEditor,
  type ExpressionTemplate,
  type ExpressionToken,
  type ExpressionValidateResult,
} from './components/interaction/ExpressionEditor.vue'
export { default as CronEditor } from './components/interaction/CronEditor.vue'
export { default as CodeViewer, type ViewerLanguage } from './components/interaction/CodeViewer.vue'
export { default as CaptchaField, type CaptchaKind } from './components/field/CaptchaField.vue'
export { default as AmountField } from './components/field/AmountField.vue'
export {
  default as CascadeField,
  type CascadeOption,
  type CascadeValue,
} from './components/field/CascadeField.vue'
export { default as EnumField, type EnumFieldForm, type EnumFieldValue } from './components/field/EnumField.vue'
export { default as InlineSwitchCell } from './components/field/InlineSwitchCell.vue'
export { default as NumberField } from './components/field/NumberField.vue'
export {
  default as RichTextField,
  type RichTextFieldMode,
} from './components/field/RichTextField.vue'
export { default as SwitchField } from './components/field/SwitchField.vue'
export {
  default as TagInputField,
  type TagColorMap,
} from './components/field/TagInputField.vue'
export {
  default as TransferField,
  type TransferItem,
  type TransferValue,
} from './components/field/TransferField.vue'
export {
  default as TreeSelectField,
  type TreeFieldNode,
  type TreeFieldValue,
} from './components/field/TreeSelectField.vue'
export {
  default as DateTimeField,
  type DateTimeKind,
  type DateTimeValue,
} from './components/field/DateTimeField.vue'
export { default as DictSelectField, type DictFieldValue } from './components/field/DictSelectField.vue'
export { default as FileUploadField, type UploadFieldItem } from './components/field/FileUploadField.vue'
export { default as OrgSelectField, type OrgFieldValue } from './components/field/OrgSelectField.vue'
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
export {
  useBaseLayout,
  type UseBaseLayoutOptions,
  type UseBaseLayoutResult,
} from './composables/useBaseLayout'
export {
  useBaseDisplay,
  type UseBaseDisplayResult,
} from './composables/useBaseDisplay'
export {
  useDisplayPlaceholder,
  type UseDisplayPlaceholderOptions,
  type UseDisplayPlaceholderResult,
} from './composables/useDisplayPlaceholder'
export {
  useBaseDataState,
  type UseBaseDataStateResult,
} from './composables/useBaseDataState'
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
export {
  useBaseDragDrop,
  type UseBaseDragDropResult,
} from './composables/useBaseDragDrop'
export {
  useBaseFormMeta,
  type UseBaseFormMetaOptions,
  type UseBaseFormMetaResult,
} from './composables/useBaseFormMeta'
export {
  useBaseLocale,
  type UseBaseLocaleOptions,
  type UseBaseLocaleResult,
} from './composables/useBaseLocale'
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
export {
  useBaseTreeData,
  type UseBaseTreeDataOptions,
  type UseBaseTreeDataResult,
} from './composables/useBaseTreeData'
export {
  useBaseAccess,
  type UseBaseAccessResult,
} from './composables/useBaseAccess'
export {
  useBaseUserDisplay,
  type UseBaseUserDisplayResult,
} from './composables/useBaseUserDisplay'
export {
  useBaseWatermark,
  type UseBaseWatermarkResult,
} from './composables/useBaseWatermark'
export {
  useBasePresignedUrl,
  type UseBasePresignedUrlResult,
} from './composables/useBasePresignedUrl'
export {
  useRichTextKernel,
  type UseRichTextKernelOptions,
  type UseRichTextKernelResult,
} from './composables/useRichTextKernel'
export { RICH_TEXT_ALLOWED_ATTR, RICH_TEXT_ALLOWED_TAGS, sanitizeHtml, sanitizeToText } from './utils/sanitizeHtml'
export {
  diffKind,
  formatDiffValue,
  inferValueType,
  type AuditDiffKind,
  type AuditValueType,
} from './utils/auditDiff'
export {
  useFieldPlaceholder,
  type UseFieldPlaceholderOptions,
  type UseFieldPlaceholderResult,
} from './composables/useFieldPlaceholder'
export {
  useBaseInput,
  type UseBaseInputOptions,
  type UseBaseInputResult,
} from './composables/useBaseInput'
export {
  useBaseField,
  type UseBaseFieldOptions,
  type UseBaseFieldResult,
} from './composables/useBaseField'
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
export {
  useSideMenu,
  type UseSideMenuOptions,
  type UseSideMenuResult,
} from './composables/useSideMenu'
export {
  useTabNav,
  type TabNavItem,
  type UseTabNavOptions,
  type UseTabNavResult,
} from './composables/useTabNav'
export { useModalShell, type UseModalShellResult } from './composables/useModalShell'
export {
  useFormModal,
  type UseFormModalOptions,
  type UseFormModalResult,
} from './composables/useFormModal'
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
export {
  useBaseWizard,
  type UseBaseWizardOptions,
  type UseBaseWizardResult,
} from './composables/useBaseWizard'
export {
  usePreferences,
  type UsePreferencesOptions,
  type UsePreferencesResult,
} from './composables/usePreferences'
export {
  DEFAULT_PREFERENCE_GROUPS,
  resolvePreferenceGroups,
  type PreferenceControl,
  type PreferenceGroupDef,
  type PreferenceItem,
  type PreferenceOption,
} from './utils/preferenceItems'
