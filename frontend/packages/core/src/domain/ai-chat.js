/**
 * 领域纯函数：AI 助手对话（模式 / 消息与会话归一 / 流式状态机 / 结果与引用 / 二次确认与撤销 / 错误码）。
 *
 * 不触 DOM、不请求、不依赖渲染框架与第三方库；同输入同输出。
 * 消息 / 会话字段与后端 `ai_chat_log` 派生视图对齐；错误码取值 10201 ~ 10216（与《概要设计 · AI 能力》同源）。
 */
import { fnv1aHex, stableStringify } from './serialize';
/** AI 对话权限码（对话 / 问数 / 审批辅助 / 文档问答入口）。 */
export const AI_CHAT_PERM = 'ai:chat';
/** AI 审计与模型管理权限码（全量审计会话）。 */
export const AI_MANAGE_PERM = 'ai:manage';
/** AI 助手占位文案。 */
export const AI_PLACEHOLDER_TEXT = 'AI 助手未就绪（占位）';
/** 流式通道未就绪文案。 */
export const AI_STREAM_PLACEHOLDER_TEXT = '流式通道未就绪（占位）';
/** 自动执行未开启文案。 */
export const AI_AUTO_EXECUTE_DISABLED_TEXT = '自动执行未开启';
/** 缺二次确认文案。 */
export const AI_CONFIRM_REQUIRED_TEXT = '自动执行需二次确认';
/** 不可撤销文案。 */
export const AI_REVOKE_UNAVAILABLE_TEXT = '该动作不可撤销';
/** 消息内容长度上限（码点，与 08_07 / 08_08 统一为 4000）。 */
export const AI_MESSAGE_MAX = 4000;
/** 问题输入长度上限（码点）。 */
export const AI_PROMPT_MAX = 2000;
/** 会话列表页长缺省。 */
export const AI_SESSION_PAGE_SIZE_DEFAULT = 20;
/** 会话列表页长上限。 */
export const AI_SESSION_PAGE_SIZE_MAX = 200;
/** 助手模式集合（与组件设计 §4 同源）。 */
export const AI_MODES = ['ask', 'report', 'approval', 'doc_qa'];
/** 消息角色集合。 */
export const AI_ROLES = ['user', 'assistant'];
/** 消息状态集合。 */
export const AI_MESSAGE_STATUSES = ['streaming', 'done', 'error', 'stopped'];
/** 结果种类集合。 */
export const AI_RESULT_KINDS = ['chart', 'table'];
/** 引用来源类型集合。 */
export const AI_CITATION_TYPES = ['file', 'article', 'record'];
/** 自动执行动作状态集合。 */
export const AI_ACTION_STATES = ['pending', 'confirmed', 'executed', 'revoked', 'failed'];
/**
 * 归一文本（去首尾空格，空串回落 `undefined`）。
 *
 * @param value 原始值。
 * @returns 字符串或 `undefined`。
 */
function normalizeText(value) {
    if (typeof value === 'string' && value.trim() !== '') {
        return value.trim();
    }
    if (typeof value === 'number' && Number.isFinite(value)) {
        return String(value);
    }
    return undefined;
}
/**
 * 归一内容文本（保留空串，去首尾换行）。
 *
 * @param value 原始值。
 * @returns 内容文本。
 */
function normalizeContent(value) {
    return typeof value === 'string' ? value : '';
}
/**
 * 归一助手模式（非白名单回落 `ask`）。
 *
 * @param value 原始模式。
 * @returns 助手模式。
 */
export function normalizeAiMode(value) {
    const text = typeof value === 'string' ? value.trim() : '';
    return AI_MODES.includes(text) ? text : 'ask';
}
/**
 * 归一消息角色（非白名单回落 `assistant`）。
 *
 * @param value 原始角色。
 * @returns 消息角色。
 */
export function normalizeAiRole(value) {
    const text = typeof value === 'string' ? value.trim() : '';
    return AI_ROLES.includes(text) ? text : 'assistant';
}
/**
 * 归一消息状态（非白名单回落 `done`）。
 *
 * @param value 原始状态。
 * @returns 消息状态。
 */
export function normalizeAiMessageStatus(value) {
    const text = typeof value === 'string' ? value.trim() : '';
    return AI_MESSAGE_STATUSES.includes(text) ? text : 'done';
}
/**
 * 归一引用来源类型（非白名单回落 `file`）。
 *
 * @param value 原始类型。
 * @returns 引用来源类型。
 */
export function normalizeAiCitationType(value) {
    const text = typeof value === 'string' ? value.trim() : '';
    return AI_CITATION_TYPES.includes(text) ? text : 'file';
}
/**
 * 归一结果种类（非白名单回落 `table`）。
 *
 * @param value 原始种类。
 * @returns 结果种类。
 */
export function normalizeAiResultKind(value) {
    const text = typeof value === 'string' ? value.trim() : '';
    return AI_RESULT_KINDS.includes(text) ? text : 'table';
}
/**
 * 归一单条引用来源（缺 `title` 或 `id` 视为脏项）。
 *
 * @param value 原始引用。
 * @returns 归一引用或 `undefined`。
 */
export function normalizeAiCitation(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    const raw = value;
    const title = normalizeText(raw.title);
    const id = normalizeText(raw.id);
    if (title === undefined || id === undefined) {
        return undefined;
    }
    return { type: normalizeAiCitationType(raw.type), title, id };
}
/**
 * 归一引用来源数组（脏项剔除）。
 *
 * @param value 原始数组。
 * @returns 归一引用数组。
 */
export function normalizeAiCitations(value) {
    if (!Array.isArray(value)) {
        return [];
    }
    const out = [];
    for (const entry of value) {
        const citation = normalizeAiCitation(entry);
        if (citation !== undefined) {
            out.push(citation);
        }
    }
    return out;
}
/**
 * 归一单个结果列（缺 `name` 视为脏项）。
 *
 * @param value 原始列。
 * @returns 归一列或 `undefined`。
 */
export function normalizeAiResultColumn(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    const raw = value;
    const name = normalizeText(raw.name);
    if (name === undefined) {
        return undefined;
    }
    const column = { name };
    const type = normalizeText(raw.type);
    if (type !== undefined) {
        column.type = type;
    }
    const label = normalizeText(raw.label);
    if (label !== undefined) {
        column.label = label;
    }
    return column;
}
/**
 * 归一结果列数组（脏项剔除）。
 *
 * @param value 原始数组。
 * @returns 归一列数组。
 */
export function normalizeAiResultColumns(value) {
    if (!Array.isArray(value)) {
        return [];
    }
    const out = [];
    for (const entry of value) {
        const column = normalizeAiResultColumn(entry);
        if (column !== undefined) {
            out.push(column);
        }
    }
    return out;
}
/**
 * 归一结构化结果（`kind` 非法视为脏项）。
 *
 * @param value 原始结果。
 * @returns 归一结果或 `undefined`。
 */
export function normalizeAiResult(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    const raw = value;
    const kind = normalizeText(raw.kind);
    if (kind === undefined || !AI_RESULT_KINDS.includes(kind)) {
        return undefined;
    }
    const result = { kind: kind };
    const chartType = normalizeText(raw.chartType);
    if (chartType !== undefined) {
        result.chartType = chartType;
    }
    const datasetId = normalizeText(raw.datasetId);
    if (datasetId !== undefined) {
        result.datasetId = datasetId;
    }
    const title = normalizeText(raw.title);
    if (title !== undefined) {
        result.title = title;
    }
    const columns = normalizeAiResultColumns(raw.columns);
    if (columns.length > 0) {
        result.columns = columns;
    }
    if (Array.isArray(raw.rows)) {
        result.rows = [...raw.rows];
    }
    return result;
}
/**
 * 归一单条消息（缺 `id` 视为脏项；`content` 允许空串以承载流式占位）。
 *
 * @param value 原始消息。
 * @returns 归一消息或 `undefined`。
 */
export function normalizeAiMessage(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    const raw = value;
    const id = normalizeText(raw.id);
    if (id === undefined) {
        return undefined;
    }
    const message = {
        id,
        role: normalizeAiRole(raw.role),
        status: normalizeAiMessageStatus(raw.status),
        content: normalizeContent(raw.content),
    };
    const result = normalizeAiResult(raw.result);
    if (result !== undefined) {
        message.result = result;
    }
    const citations = normalizeAiCitations(raw.citations);
    if (citations.length > 0) {
        message.citations = citations;
    }
    if (Array.isArray(raw.risks)) {
        const risks = raw.risks.map((item) => normalizeText(item)).filter((item) => item !== undefined);
        if (risks.length > 0) {
            message.risks = risks;
        }
    }
    const auditId = normalizeText(raw.auditId);
    if (auditId !== undefined) {
        message.auditId = auditId;
    }
    const createdAt = normalizeText(raw.createdAt);
    if (createdAt !== undefined) {
        message.createdAt = createdAt;
    }
    return message;
}
/**
 * 归一消息数组（脏项剔除）。
 *
 * @param value 原始数组。
 * @returns 归一消息数组。
 */
export function normalizeAiMessages(value) {
    if (!Array.isArray(value)) {
        return [];
    }
    const out = [];
    for (const entry of value) {
        const message = normalizeAiMessage(entry);
        if (message !== undefined) {
            out.push(message);
        }
    }
    return out;
}
/**
 * 归一单个会话（缺 `id` 视为脏项）。
 *
 * @param value 原始会话。
 * @returns 归一会话或 `undefined`。
 */
export function normalizeAiSession(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    const raw = value;
    const id = normalizeText(raw.id);
    if (id === undefined) {
        return undefined;
    }
    return {
        id,
        title: normalizeText(raw.title) ?? '新会话',
        mode: normalizeAiMode(raw.mode),
        updatedAt: normalizeText(raw.updatedAt ?? raw.updated_at) ?? '',
    };
}
/**
 * 归一会话数组（脏项剔除）。
 *
 * @param value 原始数组。
 * @returns 归一会话数组。
 */
export function normalizeAiSessions(value) {
    if (!Array.isArray(value)) {
        return [];
    }
    const out = [];
    for (const entry of value) {
        const session = normalizeAiSession(entry);
        if (session !== undefined) {
            out.push(session);
        }
    }
    return out;
}
/**
 * 归一会话列表页结果（支持数组或 `{ items, total }`）。
 *
 * @param value 原始结果。
 * @returns 归一页结果。
 */
export function normalizeAiSessionsPage(value) {
    if (Array.isArray(value)) {
        const items = normalizeAiSessions(value);
        return { items, total: items.length };
    }
    if (value === null || typeof value !== 'object') {
        return { items: [], total: 0 };
    }
    const raw = value;
    const items = normalizeAiSessions(raw.items);
    const totalRaw = raw.total;
    const total = typeof totalRaw === 'number' && Number.isFinite(totalRaw) && totalRaw >= 0 ? Math.floor(totalRaw) : items.length;
    return { items, total };
}
/**
 * 归一待确认动作（缺 `id` 视为脏项）。
 *
 * @param value 原始动作。
 * @returns 归一动作或 `undefined`。
 */
export function normalizePendingAction(value) {
    if (value === null || typeof value !== 'object' || Array.isArray(value)) {
        return undefined;
    }
    const raw = value;
    const id = normalizeText(raw.id);
    if (id === undefined) {
        return undefined;
    }
    const state = normalizeText(raw.state);
    const action = {
        id,
        title: normalizeText(raw.title) ?? '待确认操作',
        state: AI_ACTION_STATES.includes(state ?? '')
            ? state
            : 'pending',
        confirmable: raw.confirmable !== false,
        revocable: raw.revocable === true,
    };
    const summary = normalizeText(raw.summary);
    if (summary !== undefined) {
        action.summary = summary;
    }
    const content = normalizeText(raw.content);
    if (content !== undefined) {
        action.content = content;
    }
    const auditId = normalizeText(raw.auditId);
    if (auditId !== undefined) {
        action.auditId = auditId;
    }
    return action;
}
/**
 * 助手模式中文标签。
 *
 * @param mode 模式。
 * @returns 标签。
 */
export function modeLabel(mode) {
    if (mode === 'report') {
        return '智能问数';
    }
    if (mode === 'approval') {
        return '审批辅助';
    }
    if (mode === 'doc_qa') {
        return '文档问答';
    }
    return '通用对话';
}
/**
 * 消息状态中文标签。
 *
 * @param status 状态。
 * @returns 标签。
 */
export function messageStatusLabel(status) {
    if (status === 'streaming') {
        return '生成中';
    }
    if (status === 'error') {
        return '生成失败';
    }
    if (status === 'stopped') {
        return '已停止';
    }
    return '已完成';
}
/**
 * 引用来源类型中文标签。
 *
 * @param type 来源类型。
 * @returns 标签。
 */
export function citationTypeLabel(type) {
    if (type === 'article') {
        return '帮助文章';
    }
    if (type === 'record') {
        return '业务记录';
    }
    return '文件';
}
/**
 * 消息状态 → 语义色（复用 `domain/status.ts` 五档）。
 *
 * @param status 状态。
 * @returns 语义色。
 */
export function resolveAiSemantic(status) {
    if (status === 'streaming') {
        return 'primary';
    }
    if (status === 'error') {
        return 'danger';
    }
    if (status === 'stopped') {
        return 'info';
    }
    return 'success';
}
/**
 * 派生下一个会话标识（`s-{n}` 递增不冲突）。
 *
 * @param sessions 既有会话。
 * @returns 新会话标识。
 */
export function nextSessionId(sessions) {
    let index = sessions.length + 1;
    const used = new Set(sessions.map((session) => session.id));
    while (used.has(`s-${index}`)) {
        index += 1;
    }
    return `s-${index}`;
}
/**
 * 派生下一个消息标识（`m-{n}` 递增不冲突）。
 *
 * @param messages 既有消息。
 * @returns 新消息标识。
 */
export function nextMessageId(messages) {
    let index = messages.length + 1;
    const used = new Set(messages.map((message) => message.id));
    while (used.has(`m-${index}`)) {
        index += 1;
    }
    return `m-${index}`;
}
/**
 * 由问题内容派生会话标题（截断到指定长度）。
 *
 * @param content 问题内容。
 * @param max 最大长度（缺省 20）。
 * @returns 会话标题。
 */
export function deriveSessionTitle(content, max = 20) {
    const text = content.trim().replace(/\s+/g, ' ');
    if (text === '') {
        return '新会话';
    }
    const limit = Math.max(1, Math.floor(max));
    return text.length > limit ? `${text.slice(0, limit)}…` : text;
}
/**
 * 会话按更新时间降序排序（缺失视为最旧、稳定保序）。
 *
 * @param sessions 会话数组。
 * @returns 排序后的新数组。
 */
export function sortSessions(sessions) {
    return sessions
        .map((session, index) => ({ session, index }))
        .sort((a, b) => {
        const left = a.session.updatedAt;
        const right = b.session.updatedAt;
        if (left === right) {
            return a.index - b.index;
        }
        if (left === '') {
            return 1;
        }
        if (right === '') {
            return -1;
        }
        return left < right ? 1 : -1;
    })
        .map((entry) => entry.session);
}
/**
 * 按模式与关键字筛选会话。
 *
 * @param sessions 会话数组。
 * @param query 筛选条件。
 * @returns 命中会话（新数组）。
 */
export function filterSessions(sessions, query) {
    const mode = query.mode ?? 'all';
    const keyword = (query.keyword ?? '').trim();
    return sessions.filter((session) => {
        if (mode !== 'all' && session.mode !== mode) {
            return false;
        }
        if (keyword !== '' && !session.title.includes(keyword)) {
            return false;
        }
        return true;
    });
}
/**
 * 创建流式助手消息占位。
 *
 * @param input 消息入参。
 * @returns 处于 `streaming` 的新消息。
 */
export function startStreamMessage(input) {
    const message = {
        id: input.id,
        role: input.role,
        status: 'streaming',
        content: input.content ?? '',
    };
    if (input.createdAt !== undefined) {
        message.createdAt = input.createdAt;
    }
    return message;
}
/**
 * 追加流式片段（仅对 `streaming` 消息生效，迟到帧忽略）。
 *
 * @param message 消息。
 * @param delta 片段。
 * @returns 新消息。
 */
export function appendStreamChunk(message, delta) {
    if (message.status !== 'streaming' || delta === '') {
        return { ...message };
    }
    return { ...message, content: message.content + delta };
}
/**
 * 结束流式（置 `done` 并合并完成载荷）。
 *
 * @param message 消息。
 * @param patch 完成载荷（结果 / 引用 / 风险 / 审计）。
 * @returns 新消息。
 */
export function finishMessage(message, patch) {
    const next = { ...message, status: 'done' };
    if (patch !== undefined) {
        if (patch.content !== undefined) {
            next.content = patch.content;
        }
        const result = normalizeAiResult(patch.result);
        if (result !== undefined) {
            next.result = result;
        }
        const citations = normalizeAiCitations(patch.citations);
        if (citations.length > 0) {
            next.citations = citations;
        }
        if (Array.isArray(patch.risks)) {
            const risks = patch.risks
                .map((item) => normalizeText(item))
                .filter((item) => item !== undefined);
            if (risks.length > 0) {
                next.risks = risks;
            }
        }
        const auditId = normalizeText(patch.auditId);
        if (auditId !== undefined) {
            next.auditId = auditId;
        }
    }
    return next;
}
/**
 * 置消息为失败态（保留已接收内容）。
 *
 * @param message 消息。
 * @param errorMessage 失败说明（不写入消息内容，供件层提示）。
 * @returns 新消息。
 */
export function failMessage(message, errorMessage) {
    const next = { ...message, status: 'error' };
    if (errorMessage !== undefined && next.content === '') {
        next.content = errorMessage;
    }
    return next;
}
/**
 * 置消息为停止态（保留已接收内容）。
 *
 * @param message 消息。
 * @returns 新消息。
 */
export function stopMessage(message) {
    return { ...message, status: 'stopped' };
}
/**
 * 流式状态机（按事件对消息做不可变迁移）。
 *
 * @param message 消息。
 * @param event 流式事件。
 * @returns 新消息。
 */
export function reduceStream(message, event) {
    if (event.type === 'chunk') {
        return appendStreamChunk(message, event.delta);
    }
    if (event.type === 'done') {
        return finishMessage(message, event.patch);
    }
    if (event.type === 'error') {
        return failMessage(message, event.message);
    }
    if (event.type === 'stop') {
        return stopMessage(message);
    }
    return { ...message, status: 'streaming' };
}
/**
 * 是否可发送（就绪 ∧ 有权 ∧ 非流式中 ∧ 内容合法）。
 *
 * @param ready 数据通路是否就绪。
 * @param content 内容。
 * @param streaming 是否流式中。
 * @param hasPerm 是否持对话权限。
 * @returns 是否可发送。
 */
export function canSend(ready, content, streaming, hasPerm) {
    return ready && hasPerm && !streaming && validatePrompt(content).valid;
}
/**
 * 是否可停止（流式中）。
 *
 * @param streaming 是否流式中。
 * @returns 是否可停止。
 */
export function canStop(streaming) {
    return streaming;
}
/**
 * 是否可重新生成（助手消息且状态为失败 / 已停止）。
 *
 * @param message 消息。
 * @returns 是否可重生成。
 */
export function canRegenerate(message) {
    return message.role === 'assistant' && (message.status === 'error' || message.status === 'stopped');
}
/**
 * 统计码点数（与长度上限口径一致）。
 *
 * @param text 文本。
 * @returns 码点数。
 */
export function countAiCodePoints(text) {
    return [...text].length;
}
/**
 * 校验问题输入（空 / 超长）。
 *
 * @param content 输入内容。
 * @returns 校验结果。
 */
export function validatePrompt(content) {
    const text = content.trim();
    if (text === '') {
        return { valid: false, message: '请输入问题' };
    }
    if (countAiCodePoints(text) > AI_PROMPT_MAX) {
        return { valid: false, message: `问题超过 ${AI_PROMPT_MAX} 字` };
    }
    return { valid: true };
}
/**
 * 是否可自动执行（持对话权限且开关开启）。
 *
 * @param autoExecute 自动执行开关。
 * @param hasPerm 是否持对话权限。
 * @returns 是否可用。
 */
export function canAutoExecute(autoExecute, hasPerm) {
    return autoExecute && hasPerm;
}
/**
 * 自动审批是否可用（依赖自动执行开关）。
 *
 * @param autoExecute 自动执行开关。
 * @param autoApprove 自动审批开关。
 * @returns 是否可用。
 */
export function autoApproveAvailable(autoExecute, autoApprove) {
    return autoExecute && autoApprove;
}
/**
 * 是否需要二次确认（待确认且可确认）。
 *
 * @param action 待确认动作。
 * @returns 是否需要确认。
 */
export function requiresConfirm(action) {
    return action.state === 'pending' && action.confirmable;
}
/**
 * 是否可撤销（已执行且可撤销）。
 *
 * @param action 待确认动作。
 * @returns 是否可撤销。
 */
export function canRevokeAction(action) {
    return action.state === 'executed' && action.revocable;
}
/**
 * 确认动作（`pending` → `confirmed`）。
 *
 * @param action 待确认动作。
 * @returns 新动作。
 */
export function applyActionConfirm(action) {
    return { ...action, state: 'confirmed' };
}
/**
 * 标记动作已执行（`confirmed` → `executed`，可回传审计与可撤销）。
 *
 * @param action 待确认动作。
 * @param patch 执行回执。
 * @returns 新动作。
 */
export function applyActionExecute(action, patch) {
    const next = { ...action, state: 'executed' };
    if (patch?.auditId !== undefined) {
        next.auditId = patch.auditId;
    }
    if (patch?.revocable !== undefined) {
        next.revocable = patch.revocable;
    }
    return next;
}
/**
 * 撤销动作（`executed` → `revoked`）。
 *
 * @param action 待确认动作。
 * @returns 新动作。
 */
export function applyActionRevoke(action) {
    return { ...action, state: 'revoked' };
}
/**
 * 标记动作失败。
 *
 * @param action 待确认动作。
 * @returns 新动作。
 */
export function applyActionFail(action) {
    return { ...action, state: 'failed' };
}
/**
 * 待确认动作状态查询。
 *
 * @param action 待确认动作。
 * @returns 状态。
 */
export function resolveActionState(action) {
    return action.state;
}
/**
 * 是否 AI 错误码（`10201 ~ 10216`）。
 *
 * @param value 待判定值。
 * @returns 是否 AI 错误码。
 */
export function isAiErrorCode(value) {
    const code = typeof value === 'number' ? value : Number(value);
    return Number.isInteger(code) && code >= 10201 && code <= 10216;
}
/**
 * 解析 AI 错误码文案。
 *
 * @param code 错误码。
 * @returns 文案（未知回落通用文案）。
 */
export function resolveAiErrorText(code) {
    const table = {
        10201: '模型不可用或未配置',
        10202: 'AI 调用超时',
        10203: 'AI 输出校验未通过',
        10204: 'AI 预算超限',
        10205: '租户无可用模型端点',
        10206: '数据集不在白名单内',
        10207: '生成的 SQL 未通过安全校验',
        10208: '自动执行未开启',
        10209: '自动审批未开启',
        10210: '动作不在白名单内',
        10211: '缺少二次确认',
        10212: '该动作不可撤销',
        10213: '文件尚未完成分段',
        10216: '审计落库失败',
    };
    const key = typeof code === 'number' ? code : Number(code);
    return table[key] ?? 'AI 请求失败';
}
/**
 * 派生 AI 请求幂等键（内容派生）。
 *
 * @param input 参与派生的载荷。
 * @returns 幂等键（`ai:{hash}`）。
 */
export function deriveAiKey(input) {
    return `ai:${fnv1aHex(stableStringify(input))}`;
}
/**
 * 切分消息内容为文本段与围栏代码段（供 Markdown 与只读高亮分工）。
 *
 * @param content 消息内容。
 * @returns 分段数组。
 */
export function splitContentSegments(content) {
    const segments = [];
    const lines = content.split('\n');
    let buffer = [];
    let code;
    let lang;
    for (const line of lines) {
        const fence = /^```(\w*)\s*$/.exec(line);
        if (fence !== null) {
            if (code === undefined) {
                if (buffer.length > 0) {
                    segments.push({ type: 'text', text: buffer.join('\n') });
                    buffer = [];
                }
                code = [];
                lang = fence[1] === '' ? undefined : fence[1];
            }
            else {
                segments.push({ type: 'code', text: code.join('\n'), ...(lang !== undefined ? { lang } : {}) });
                code = undefined;
                lang = undefined;
            }
            continue;
        }
        if (code === undefined) {
            buffer.push(line);
        }
        else {
            code.push(line);
        }
    }
    if (code !== undefined) {
        segments.push({ type: 'code', text: code.join('\n'), ...(lang !== undefined ? { lang } : {}) });
    }
    if (buffer.length > 0) {
        segments.push({ type: 'text', text: buffer.join('\n') });
    }
    return segments.filter((segment) => segment.text !== '');
}
/**
 * 取可重生成的原始输入（该助手消息之前最近的一条用户消息）。
 *
 * @param messages 消息数组。
 * @param messageId 目标消息标识。
 * @param mode 当前模式（缺省 `ask`）。
 * @returns 原始输入与模式或 `undefined`。
 */
export function resolveRegenerateInput(messages, messageId, mode = 'ask') {
    const index = messages.findIndex((message) => message.id === messageId);
    if (index < 0 || messages[index].role !== 'assistant') {
        return undefined;
    }
    for (let cursor = index - 1; cursor >= 0; cursor -= 1) {
        if (messages[cursor].role === 'user') {
            return { content: messages[cursor].content, mode };
        }
    }
    return undefined;
}
