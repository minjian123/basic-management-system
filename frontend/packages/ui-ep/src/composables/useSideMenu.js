/** 侧边菜单组合式：权限过滤 + 关键词过滤 + 菜单 → 路由构建 / 注册 / 卸载（经核心 `BaseDynamicRoutes`）。
 *
 * 菜单源支持**响应式**（`MaybeRef<MenuNode[]>`：常量 / `ref` / `computed`）——异步菜单（如动态菜单
 * 接口）在装载完成后自动重算过滤结果与路径清单，宿主无需重建组合式实例。
 */
import { BaseDynamicRoutes, filterMenuByKeyword, filterMenuByPermission, toRouteNodes, } from '@bms/core';
import { computed, ref, unref } from 'vue';
import { useBaseAccess } from './useBaseAccess';
/** 具体动态路由状态（可实例化）。 */
class MenuRouteState extends BaseDynamicRoutes {
}
/**
 * 使用侧边菜单。
 *
 * @param options 选项。
 * @returns 菜单状态与路由操作。
 */
export function useSideMenu(options = {}) {
    const access = useBaseAccess(options.codes ?? []);
    const canAccess = options.canAccess ?? (options.codes === undefined ? () => true : (code) => access.canAccess(code));
    const source = computed(() => unref(options.menu) ?? []);
    const menu = computed(() => filterMenuByPermission(source.value, canAccess));
    const keyword = ref('');
    const filtered = computed(() => filterMenuByKeyword(menu.value, keyword.value));
    const state = new MenuRouteState();
    const routes = ref([]);
    const routePaths = computed(() => state.build(toRouteNodes(menu.value)));
    function setKeyword(value) {
        keyword.value = value;
    }
    function register() {
        const paths = routePaths.value;
        state.register(paths);
        routes.value = [...state.routes];
        return paths;
    }
    function unregister(path) {
        state.unregister(path);
        routes.value = [...state.routes];
    }
    return {
        menu,
        keyword,
        filtered,
        setKeyword,
        routes,
        get routePaths() {
            return routePaths.value;
        },
        register,
        unregister,
        codes: access.codes,
        setCodes: access.setCodes,
    };
}
