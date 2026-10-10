/**
 * 动态路由能力基类：菜单树 → 路由构建 / 注册 / 卸载。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 动态路由能力基类（抽象）。 */
export class BaseDynamicRoutes extends BaseComponent {
    /** 能力键。 */
    identifier = 'dynamic-routes';
    /** 已注册路由路径（保序）。 */
    routes = [];
    /**
     * 由菜单树构建路由路径清单。
     *
     * @param menu 菜单树。
     * @returns 路由路径清单。
     */
    build(menu) {
        const paths = [];
        const walk = (nodes) => {
            for (const node of nodes) {
                paths.push(node.path);
                if (node.children !== undefined) {
                    walk(node.children);
                }
            }
        };
        walk(menu);
        return paths;
    }
    /**
     * 注册路由路径（去重、保序）。
     *
     * @param paths 路由路径。
     */
    register(paths) {
        for (const path of paths) {
            if (!this.routes.includes(path)) {
                this.routes.push(path);
            }
        }
    }
    /**
     * 卸载路由（缺省卸载全部）。
     *
     * @param path 指定路径；缺省清空。
     */
    unregister(path) {
        if (path === undefined) {
            this.routes.length = 0;
            return;
        }
        const index = this.routes.indexOf(path);
        if (index >= 0) {
            this.routes.splice(index, 1);
        }
    }
}
