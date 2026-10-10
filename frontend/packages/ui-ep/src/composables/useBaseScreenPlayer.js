/** 大屏播放投影：把核心能力基类 `BaseScreenPlayer` 投影为组合式（多页轮播 / 播放态 / 按组件取数）。 */
import { BaseScreenPlayer, } from '@bms/core';
import { markRaw, onScopeDispose, ref, toRaw } from 'vue';
/** 具体大屏播放件（可实例化）。 */
class ScreenPlayerState extends BaseScreenPlayer {
}
/**
 * 使用大屏播放投影。
 *
 * @param options 选项。
 * @returns 大屏播放基类实例与响应式面。
 */
export function useBaseScreenPlayer(options = {}) {
    const player = new ScreenPlayerState();
    player.setReady(options.ready ?? false);
    if (options.screenCode !== undefined) {
        player.screenCode = options.screenCode;
    }
    if (options.canvas !== undefined) {
        player.setCanvas(options.canvas);
    }
    if (options.pages !== undefined) {
        player.setPages(options.pages);
    }
    if (options.componentsByPage !== undefined) {
        player.setComponents(options.componentsByPage);
    }
    if (options.activePageId !== undefined && player.pages.some((page) => page.id === options.activePageId)) {
        player.activePageId = options.activePageId;
    }
    if (options.autoplay !== undefined) {
        player.setPlaying(options.autoplay);
    }
    if (options.interval !== undefined) {
        player.setInterval(options.interval);
    }
    if (options.fullscreen !== undefined) {
        player.setFullscreen(options.fullscreen);
    }
    if (options.jobs !== undefined) {
        player.jobs = options.jobs;
    }
    if (options.access !== undefined) {
        player.access = markRaw(toRaw(options.access));
    }
    if (options.notice !== undefined) {
        player.notice = markRaw(toRaw(options.notice));
    }
    if (options.dataState !== undefined) {
        player.dataState = markRaw(toRaw(options.dataState));
    }
    if (options.asyncTask !== undefined) {
        player.asyncTask = markRaw(toRaw(options.asyncTask));
    }
    const ready = ref(player.ready);
    const degraded = ref(player.degraded);
    const busy = ref(player.busy);
    const phase = ref(player.phase);
    const canvas = ref(player.canvas);
    const pages = ref([...player.pages]);
    const components = ref(player.currentComponents);
    const activePageId = ref(player.activePageId);
    const playing = ref(player.playing);
    const interval = ref(player.interval);
    const currentInterval = ref(player.currentInterval);
    const fullscreen = ref(player.fullscreen);
    const data = ref({ ...player.data });
    const errorMessage = ref(player.errorMessage);
    const requestCount = ref(player.requestCount);
    /** 从基类实例同步响应式面。 */
    const sync = () => {
        ready.value = player.ready;
        degraded.value = player.degraded;
        busy.value = player.busy;
        phase.value = player.phase;
        canvas.value = player.canvas;
        pages.value = [...player.pages];
        components.value = player.currentComponents;
        activePageId.value = player.activePageId;
        playing.value = player.playing;
        interval.value = player.interval;
        currentInterval.value = player.currentInterval;
        fullscreen.value = player.fullscreen;
        data.value = { ...player.data };
        errorMessage.value = player.errorMessage;
        requestCount.value = player.requestCount;
    };
    const off = player.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(() => {
        off();
        player.dispose();
    });
    /** 包裹动作：执行后同步响应式面。 */
    const run = (action) => {
        const value = action();
        sync();
        return value;
    };
    return {
        player,
        ready,
        degraded,
        busy,
        phase,
        canvas,
        pages,
        components,
        activePageId,
        playing,
        interval,
        currentInterval,
        fullscreen,
        data,
        errorMessage,
        requestCount,
        setReady: (value) => run(() => player.setReady(value)),
        setJobs: (jobs) => run(() => player.setJobs(jobs)),
        setCanvas: (value) => run(() => player.setCanvas(value)),
        setPages: (value) => run(() => player.setPages(value)),
        setComponents: (value) => run(() => player.setComponents(value)),
        setPlaying: (value) => run(() => player.setPlaying(value)),
        setInterval: (value) => run(() => player.setInterval(value)),
        setFullscreen: (value) => run(() => player.setFullscreen(value)),
        selectPage: (pageId) => run(() => player.selectPage(pageId)),
        next: () => run(() => player.next()),
        prev: () => run(() => player.prev()),
        toggle: (force) => run(() => player.toggle(force)),
        markLoaded: () => run(() => player.markLoaded()),
        load: async (input) => {
            const value = await player.load(input);
            sync();
            return value;
        },
        queryComponent: async (componentId, pageId, params) => {
            const value = await player.queryComponent(componentId, pageId, params);
            sync();
            return value;
        },
        refreshPage: async (pageId) => {
            const value = await player.refreshPage(pageId);
            sync();
            return value;
        },
    };
}
