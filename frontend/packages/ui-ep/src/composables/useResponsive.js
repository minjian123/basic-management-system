/** 响应式断点组合式：断点值取自设计令牌（`BaseDesignToken.breakpoints`），优先 `matchMedia` 监听。 */
import { computed, onScopeDispose, ref } from 'vue';
import { useBaseDesignToken } from './useBaseDesignToken';
import { onMediaChange, supportsMediaQuery } from '../utils/media';
import { onWindowResize, viewportWidth } from '../utils/observe';
/** 内置缺省断点（可由令牌 / 选项覆盖）。 */
export const DEFAULT_BREAKPOINTS = { mobile: 768, narrow: 992, wide: 1200 };
/** 当前视口宽度（非浏览器回退宽屏阈值，保持原口径）。 */
function currentWidth() {
    return viewportWidth() || DEFAULT_BREAKPOINTS.wide;
}
/**
 * 使用响应式断点。
 *
 * @param options 选项。
 * @returns 断点与派生布尔量。
 */
export function useResponsive(options = {}) {
    const token = useBaseDesignToken();
    const breakpoints = computed(() => ({
        ...DEFAULT_BREAKPOINTS,
        ...(token.tokens.value.breakpoints ?? {}),
        ...(options.breakpoints ?? {}),
    }));
    const width = ref(currentWidth());
    const cleanups = [];
    if (supportsMediaQuery()) {
        cleanups.push(onMediaChange(`(max-width: ${breakpoints.value.narrow}px)`, () => {
            width.value = currentWidth();
        }));
    }
    else {
        cleanups.push(onWindowResize(() => {
            width.value = currentWidth();
        }));
    }
    const breakpoint = computed(() => {
        if (width.value < breakpoints.value.mobile) {
            return 'mobile';
        }
        return width.value < breakpoints.value.narrow ? 'narrow' : 'wide';
    });
    const isMobile = computed(() => breakpoint.value === 'mobile');
    const isNarrow = computed(() => breakpoint.value !== 'wide');
    const isWide = computed(() => breakpoint.value === 'wide');
    onScopeDispose(() => {
        for (const cleanup of cleanups) {
            cleanup();
        }
    });
    return { breakpoint, isMobile, isNarrow, isWide, breakpoints };
}
