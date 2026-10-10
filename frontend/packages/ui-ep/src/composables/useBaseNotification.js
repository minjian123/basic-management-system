/** 通知组件基类投影：把核心 `BaseNotification` 投影为组合式（编排 / 角标 / 乐观已读删除 / 实时与轮询 / 多标签同步）。 */
import { BaseNotification, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
import { createNotificationChannel } from '../utils/notificationChannel';
import { onVisibilityChange } from '../utils/notificationRealtime';
/** 具体通知件（可实例化）。 */
class NotificationState extends BaseNotification {
}
/**
 * 使用通知组件基类投影。
 *
 * @param options 选项。
 * @returns 通知基类实例与响应式面。
 */
export function useBaseNotification(options = {}) {
    const center = new NotificationState();
    if (options.items !== undefined) {
        center.setItems(options.items);
    }
    if (options.pageSize !== undefined) {
        center.setPageSize(options.pageSize);
    }
    if (options.typeFilter !== undefined) {
        center.setTypeFilter(options.typeFilter);
    }
    if (options.readFilter !== undefined) {
        center.setReadFilter(options.readFilter);
    }
    if (options.unreadCount !== undefined) {
        center.setUnreadCount(options.unreadCount);
    }
    if (options.jobs !== undefined) {
        center.setJobs(options.jobs);
    }
    if (options.realtime !== undefined) {
        center.setRealtime(markRaw(toRaw(options.realtime)));
    }
    center.setReady(options.ready ?? false);
    const ready = ref(center.ready);
    const degraded = ref(center.degraded);
    const phase = ref(center.phase);
    const errorMessage = ref(center.errorMessage);
    const items = ref([...center.items]);
    const total = ref(center.total);
    const page = ref(center.page);
    const pageSize = ref(center.pageSize);
    const typeFilter = ref(center.typeFilter);
    const readFilter = ref(center.readFilter);
    const unreadCount = ref(center.unreadCount);
    const badgeCount = ref(center.badgeCount);
    const badgeText = ref(center.badgeText);
    const showBadge = ref(center.showBadge);
    const connectionState = ref(center.connectionState);
    const selectedIds = ref([...center.selectedIds]);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = center.ready;
        degraded.value = center.degraded;
        phase.value = center.phase;
        errorMessage.value = center.errorMessage;
        items.value = [...center.items];
        total.value = center.total;
        page.value = center.page;
        pageSize.value = center.pageSize;
        typeFilter.value = center.typeFilter;
        readFilter.value = center.readFilter;
        unreadCount.value = center.unreadCount;
        badgeCount.value = center.badgeCount;
        badgeText.value = center.badgeText;
        showBadge.value = center.showBadge;
        connectionState.value = center.connectionState;
        selectedIds.value = [...center.selectedIds];
    };
    const channel = typeof options.channelName === 'string'
        ? createNotificationChannel(options.channelName, (message) => {
            if (message.unreadCount !== undefined) {
                center.setUnreadCount(message.unreadCount);
            }
            sync();
        })
        : undefined;
    const offVisibility = onVisibilityChange((visible) => {
        center.setVisible(visible);
    });
    const off = center.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        offVisibility();
        channel?.close();
        center.dispose();
    });
    /** 包裹动作：执行后同步响应式面。 */
    const run = (action) => {
        const value = action();
        sync();
        return value;
    };
    /** 广播角标（多标签同步）。 */
    const publishBadge = (action, ids) => {
        channel?.publish({
            unreadCount: center.unreadCount,
            latestId: center.items[0]?.id,
            action,
            ids,
        });
    };
    return {
        center,
        ready,
        degraded,
        phase,
        errorMessage,
        items,
        total,
        page,
        pageSize,
        typeFilter,
        readFilter,
        unreadCount,
        badgeCount,
        badgeText,
        showBadge,
        connectionState,
        selectedIds,
        setReady: (value) => run(() => center.setReady(value)),
        setJobs: (jobs) => run(() => center.setJobs(jobs)),
        setRealtime: (adapter) => run(() => center.setRealtime(adapter === undefined ? undefined : markRaw(toRaw(adapter)))),
        setPage: (value) => run(() => center.setPage(value)),
        setPageSize: (size) => run(() => center.setPageSize(size)),
        setTypeFilter: (type) => run(() => center.setTypeFilter(type)),
        setReadFilter: (read) => run(() => center.setReadFilter(read)),
        setUnreadCount: (value) => run(() => center.setUnreadCount(value)),
        setItems: (value) => run(() => center.setItems(value)),
        setVisible: (visible) => center.setVisible(visible),
        recent: (limit) => center.recent(limit),
        load: async () => {
            const value = await center.load();
            sync();
            return value;
        },
        refresh: async () => {
            const value = await center.refresh();
            sync();
            return value;
        },
        syncUnread: async () => {
            const value = await center.syncUnread();
            sync();
            return value;
        },
        loadDetail: async (id) => {
            const value = await center.loadDetail(id);
            sync();
            return value;
        },
        markRead: async (id) => {
            const value = await center.markRead(id);
            sync();
            publishBadge('read', [id]);
            return value;
        },
        readBatch: async (ids) => {
            const value = await center.readBatch(ids);
            sync();
            publishBadge('read', [...ids]);
            return value;
        },
        markAllRead: async () => {
            const value = await center.markAllRead();
            sync();
            publishBadge('read-all');
            return value;
        },
        remove: async (id) => {
            const value = await center.remove(id);
            sync();
            publishBadge('remove', [id]);
            return value;
        },
        toggleSelect: (id) => run(() => center.toggleSelect(id)),
        clearSelection: () => run(() => center.clearSelection()),
        applyRealtime: (payload) => {
            center.applyRealtime(payload);
            sync();
        },
        compensate: async () => {
            const value = await center.compensate();
            sync();
            return value;
        },
        connect: () => run(() => center.connect()),
        disconnect: () => run(() => center.disconnect()),
    };
}
