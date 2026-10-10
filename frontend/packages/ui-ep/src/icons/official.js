/** 官方图标登记：懒加载 `@element-plus/icons-vue` 并幂等登记为 `el:{PascalCase}`（模块级缓存，不重复加载）。 */
import { IconProvider } from '@bms/core';
import { markRaw } from 'vue';
/** 常用图标分类映射（未列出者归 `common`）。 */
const CATEGORY_MAP = {
    ArrowDown: 'direction',
    ArrowUp: 'direction',
    ArrowLeft: 'direction',
    ArrowRight: 'direction',
    DArrowLeft: 'direction',
    DArrowRight: 'direction',
    Edit: 'edit',
    EditPen: 'edit',
    Delete: 'edit',
    Document: 'edit',
    DocumentCopy: 'edit',
    Picture: 'media',
    VideoCamera: 'media',
    Microphone: 'media',
    Headset: 'media',
    User: 'common',
    Setting: 'common',
    Menu: 'common',
    Search: 'common',
    Plus: 'common',
    Minus: 'common',
};
/** 已登记官方图标的注册表（WeakSet 去重）。 */
const officialRegistered = new WeakSet();
/** 官方图标模块（模块级缓存）。 */
let officialModule;
/** 加载计数（测试用）。 */
let officialLoads = 0;
/** 加载官方图标模块（模块级缓存）。 */
function loadOfficialModule() {
    if (!officialModule) {
        officialLoads += 1;
        officialModule = import('@element-plus/icons-vue').then((mod) => mod);
    }
    return officialModule;
}
/** 取官方图标模块加载次数（测试用）。 */
export function getOfficialIconsLoadCount() {
    return officialLoads;
}
/**
 * 幂等登记官方图标（首次调用懒加载图标模块；重复键跳过）。
 *
 * @param registry 图标注册表。
 */
export async function ensureOfficialIcons(registry) {
    if (officialRegistered.has(registry)) {
        return;
    }
    const mod = await loadOfficialModule();
    for (const [name, component] of Object.entries(mod)) {
        if (!/^[A-Z]/.test(name)) {
            continue;
        }
        const key = `el:${name}`;
        if (registry.get(key)) {
            continue;
        }
        registry.register(new IconProvider(key, markRaw(component), {
            name,
            category: CATEGORY_MAP[name] ?? 'common',
            tags: [name.toLowerCase()],
        }));
    }
    officialRegistered.add(registry);
}
