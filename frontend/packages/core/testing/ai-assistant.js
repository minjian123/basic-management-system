/**
 * AI 助手契约（`@bms/core/testing`）。
 *
 * 能力基类 / 投影 / 移动端为「同一契约多实现」，各自在本套件中传入适配器跑同一套断言：
 * 占位零请求、会话与消息取数、流式追加与停止、重生成、结果 / 引用 / 风险 / 审计合并、
 * 自动执行二次确认与撤销、权限门控与防重复。
 */
import { describe, expect, it } from 'vitest';
/** 契约会话（`s1` 通用对话）。 */
export const AI_CONTRACT_SESSIONS = [
    { id: 's1', title: '上月收款合计', mode: 'ask', updatedAt: '2026-09-20T10:00:00Z' },
];
/** 契约历史消息（`m1` 助手已完成）。 */
export const AI_CONTRACT_MESSAGES = [
    { id: 'm1', role: 'user', status: 'done', content: '上月收款合计' },
    { id: 'm2', role: 'assistant', status: 'done', content: '上月共收款 120 万。' },
];
/** 契约待确认动作（`a1`）。 */
export const AI_CONTRACT_ACTION = {
    id: 'a1',
    title: '生成采购申请',
    summary: '按缺口生成采购申请',
    content: '物料 A × 100',
    state: 'pending',
    confirmable: true,
    revocable: true,
};
/**
 * 创建流式适配器桩（记录调用轨迹，供测试派发片段 / 完成 / 失败）。
 *
 * @returns 流式适配器桩。
 */
export function createAiStreamStub() {
    const calls = [];
    let handlers;
    return {
        calls,
        adapter: {
            start: (input) => {
                calls.push('start');
                handlers = input.handlers;
                return {
                    abort: () => calls.push('abort'),
                };
            },
        },
        emitChunk: (chunk) => handlers?.onChunk(chunk),
        emitDone: (payload) => handlers?.onDone(payload),
        emitError: (error) => handlers?.onError(error),
    };
}
/**
 * AI 助手契约（`08_10` 冻结；后续移动端复用同一套断言）。
 *
 * 目标约定：会话 `s1`；历史消息 `m1`（用户）/ `m2`（助手）；发送后助手消息流式追加；
 * 流式完成载荷 `{ auditId: 'log-1', result: { kind: 'table', rows: [] } }`；待确认动作 `a1`。
 *
 * @param name 契约名。
 * @param create 目标工厂。
 */
export function describeAiAssistantContract(name, create) {
    /** 构造已就绪目标（含取数处理函数与权限）。 */
    const readyTarget = (jobs = {}) => {
        const target = create();
        target.setAccessCodes(['ai:chat']);
        target.setJobs({
            loadSessions: async () => ({ items: AI_CONTRACT_SESSIONS, total: 1 }),
            loadMessages: async () => AI_CONTRACT_MESSAGES,
            ...jobs,
        });
        target.setSessions(AI_CONTRACT_SESSIONS);
        target.setReady(true);
        return target;
    };
    /** 取最后一条助手消息。 */
    const lastAssistant = (target) => [...target.messages].reverse().find((message) => message.role === 'assistant');
    describe(name, () => {
        it('未就绪时降级且不产生请求', async () => {
            const target = create();
            target.setAccessCodes(['ai:chat']);
            target.setJobs({
                loadSessions: async () => AI_CONTRACT_SESSIONS,
                loadMessages: async () => AI_CONTRACT_MESSAGES,
            });
            expect(target.ready).toBe(false);
            expect(target.degraded).toBe(true);
            await target.loadSessions();
            await target.loadMessages('s1');
            await target.send({ content: '你好' });
            await target.stop();
            await target.regenerate();
            await target.confirmAction();
            await target.revokeAction();
            expect(target.requestCount).toBe(0);
        });
        it('就绪但未注入处理函数时不产生请求（占位）', async () => {
            const target = create();
            target.setAccessCodes(['ai:chat']);
            target.setReady(true);
            await target.loadSessions();
            await target.loadMessages('s1');
            expect(target.requestCount).toBe(0);
        });
        it('会话与消息取数装载', async () => {
            const target = readyTarget();
            await target.loadSessions();
            expect(target.requestCount).toBe(1);
            expect(target.sessions).toHaveLength(1);
            expect(target.activeSessionId).toBe('s1');
            await target.loadMessages('s1');
            expect(target.requestCount).toBe(2);
            expect(target.messages).toHaveLength(2);
        });
        it('发送进入流式并组装用户与助手消息', async () => {
            const target = readyTarget({ loadMessages: async () => [] });
            await target.loadMessages('s1');
            const stub = createAiStreamStub();
            target.setStream(stub.adapter);
            const result = await target.send({ content: '上月收款合计' });
            expect(target.requestCount).toBe(2);
            expect(target.streaming).toBe(true);
            expect(target.canSend).toBe(false);
            expect(target.messages.some((message) => message.role === 'user' && message.content === '上月收款合计')).toBe(true);
            expect(result).toBeDefined();
            stub.emitChunk('上月');
            stub.emitChunk('共收款 120 万。');
            expect(lastAssistant(target)?.content).toContain('120 万');
            stub.emitDone({ auditId: 'log-1', result: { kind: 'table', rows: [] } });
            expect(target.streaming).toBe(false);
            expect(target.phase).toBe('ready');
            expect(target.canSend).toBe(true);
            expect(lastAssistant(target)?.status).toBe('done');
            expect(lastAssistant(target)?.auditId).toBe('log-1');
        });
        it('停止置 stopped 并保留已接收内容、触发适配器 abort', async () => {
            const target = readyTarget({ loadMessages: async () => [] });
            await target.loadMessages('s1');
            const stub = createAiStreamStub();
            target.setStream(stub.adapter);
            await target.send({ content: '你好' });
            stub.emitChunk('部分内容');
            expect(await target.stop()).toBe(true);
            expect(target.streaming).toBe(false);
            expect(lastAssistant(target)?.status).toBe('stopped');
            expect(lastAssistant(target)?.content).toBe('部分内容');
            expect(stub.calls).toContain('abort');
        });
        it('流式失败置 error；重生成复用原问题', async () => {
            const target = readyTarget({ loadMessages: async () => [] });
            await target.loadMessages('s1');
            const stub = createAiStreamStub();
            target.setStream(stub.adapter);
            await target.send({ content: '再问一次' });
            stub.emitError(new Error('模型不可用'));
            expect(target.streaming).toBe(false);
            expect(target.phase).toBe('error');
            expect(lastAssistant(target)?.status).toBe('error');
            const again = await target.regenerate();
            expect(again).toBeDefined();
            expect(target.streaming).toBe(true);
            const userCount = target.messages.filter((message) => message.role === 'user').length;
            expect(userCount).toBe(1);
        });
        it('非流式兜底：注入 chat 后发送填充消息', async () => {
            const target = readyTarget({
                loadMessages: async () => [],
                chat: async () => ({ auditId: 'log-2', result: { kind: 'chart', chartType: 'bar', rows: [] } }),
            });
            await target.loadMessages('s1');
            await target.send({ content: '问数' });
            expect(target.streaming).toBe(false);
            expect(lastAssistant(target)?.status).toBe('done');
            expect(lastAssistant(target)?.auditId).toBe('log-2');
        });
        it('自动执行二次确认与撤销状态机', async () => {
            const target = readyTarget({
                confirmAction: async () => ({ revocable: true, auditId: 'log-3' }),
                revokeAction: async () => true,
            });
            target.setAutoExecute(true);
            target.setPendingAction(AI_CONTRACT_ACTION);
            expect(target.canAutoExecute).toBe(true);
            expect(await target.confirmAction('a1')).toBe(true);
            expect(target.pendingAction?.state).toBe('executed');
            expect(target.pendingAction?.auditId).toBe('log-3');
            expect(await target.revokeAction('a1')).toBe(true);
            expect(target.pendingAction?.state).toBe('revoked');
        });
        it('自动执行未开启时拒绝（10208）', async () => {
            const target = readyTarget();
            target.setPendingAction(AI_CONTRACT_ACTION);
            target.setAutoExecute(false);
            expect(await target.confirmAction('a1')).toBe(false);
            expect(target.errorCode).toBe(10208);
        });
        it('不可撤销时拒绝（10212）', async () => {
            const target = readyTarget();
            target.setAutoExecute(true);
            target.setPendingAction({ ...AI_CONTRACT_ACTION, state: 'executed', revocable: false });
            expect(await target.revokeAction('a1')).toBe(false);
            expect(target.errorCode).toBe(10212);
        });
        it('无 ai:chat 时不发送', async () => {
            const target = readyTarget({ loadMessages: async () => [] });
            target.setAccessCodes([]);
            expect(target.canChat).toBe(false);
            expect(await target.send({ content: '你好' })).toBeUndefined();
            expect(target.requestCount).toBe(0);
        });
        it('新建 / 切换会话', () => {
            const target = readyTarget();
            const session = target.newSession('report');
            expect(session.mode).toBe('report');
            expect(target.activeSessionId).toBe(session.id);
            expect(target.selectSession('s1')).toBe(true);
            expect(target.activeSessionId).toBe('s1');
        });
        it('释放中止在途流', async () => {
            const target = readyTarget({ loadMessages: async () => [] });
            await target.loadMessages('s1');
            const stub = createAiStreamStub();
            target.setStream(stub.adapter);
            await target.send({ content: '你好' });
            target.dispose();
            expect(stub.calls).toContain('abort');
        });
    });
}
