/** 偏好持久化投影：把核心偏好持久化能力基类 `BasePersistedState` 投影为组合式（本地即时 / 本地存储 / 快照回滚 / 保存）。 */
import { BasePersistedState } from '@bms/core';
import { onScopeDispose, ref, shallowRef } from 'vue';
/** 具体持久化状态（可实例化）。 */
class PersistedState extends BasePersistedState {
}
/**
 * 解析存储后端（全局存储缺失或受限时返回 `undefined`）。
 *
 * @param option 存储后端口径。
 * @returns 存储实现或 `undefined`。
 */
function resolveStorage(option) {
    if (option === undefined || option === 'local' || option === 'session') {
        const scope = globalThis;
        return option === 'session' ? scope.sessionStorage : scope.localStorage;
    }
    return option;
}
/**
 * 使用偏好持久化投影。
 *
 * @param options 选项。
 * @returns 持久化基类实例与响应式面。
 */
export function useBasePersistedState(options = {}) {
    const persisted = new PersistedState();
    const storage = resolveStorage(options.storage);
    if (storage !== undefined) {
        persisted.storage = storage;
    }
    if (options.remoteSaver !== undefined) {
        persisted.remoteSaver = options.remoteSaver;
    }
    if (options.stateKey !== undefined) {
        persisted.stateKey = options.stateKey;
    }
    if (options.restore !== false) {
        persisted.restore();
    }
    if (options.initial !== undefined && !persisted.hasLocal) {
        persisted.setLocal(options.initial);
    }
    const local = shallowRef(persisted.local);
    const remoteVersion = ref(persisted.remoteVersion);
    const hasLocal = ref(persisted.hasLocal);
    const dirty = ref(persisted.dirty);
    const pendingSync = ref(persisted.pendingSync);
    /** 从基类实例同步响应式面（含 `pendingSync` 等非生命周期字段）。 */
    const sync = () => {
        local.value = persisted.local;
        remoteVersion.value = persisted.remoteVersion;
        hasLocal.value = persisted.hasLocal;
        dirty.value = persisted.dirty;
        pendingSync.value = persisted.pendingSync;
    };
    const off = persisted.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    let timer;
    /** 清理未触发的防抖定时器。 */
    const clearTimer = () => {
        if (timer !== undefined) {
            clearTimeout(timer);
            timer = undefined;
        }
    };
    onScopeDispose(clearTimer);
    return {
        persisted,
        local,
        remoteVersion,
        hasLocal,
        dirty,
        pendingSync,
        setLocal: (value) => {
            persisted.setLocal(value);
            sync();
        },
        setRemoteVersion: (version) => {
            persisted.remoteVersion = version;
            persisted.notifyLifecycle('update');
            sync();
        },
        needsRemoteRefresh: (version) => persisted.needsRemoteRefresh(version),
        loadRemote: () => persisted.loadRemote(),
        restore: () => {
            const restored = persisted.restore();
            sync();
            return restored;
        },
        persist: () => {
            const written = persisted.persist();
            sync();
            return written;
        },
        snapshot: () => {
            persisted.snapshot();
            sync();
        },
        rollback: () => {
            const rolled = persisted.rollback();
            sync();
            return rolled;
        },
        clear: () => {
            clearTimer();
            persisted.clear();
            sync();
        },
        reset: async (defaults) => {
            const saved = await persisted.reset(defaults);
            sync();
            return saved;
        },
        save: async () => {
            clearTimer();
            const saved = await persisted.save();
            sync();
            return saved;
        },
        saveDebounced: () => {
            const delay = options.saveDelay ?? 0;
            if (delay <= 0) {
                void persisted.save().then(sync);
                return;
            }
            clearTimer();
            timer = setTimeout(() => {
                timer = undefined;
                void persisted.save().then(sync);
            }, delay);
        },
    };
}
