/**
 * 用户 / 组织展示能力基类：姓名 / 头像 / 状态 / 部门路径，及成员花名册。
 *
 * 花名册（`users`）为向后兼容扩展：组织选择、消息内用户信息等按 id 批量展示的场景
 * 统一经本基类解析；既有 `user` / `setUser` / `name` / `avatar` / `status` / `deptPath` 不变。
 */
import { BaseComponent } from '../base/BaseComponent';
/** 用户展示能力基类（抽象）。 */
export class BaseUserDisplay extends BaseComponent {
    /** 能力键。 */
    identifier = 'user-display';
    /** 当前用户信息。 */
    user;
    /** 成员花名册（按 id 索引；组织选择等场景复用）。 */
    users = [];
    /**
     * 设置当前用户信息。
     *
     * @param user 用户信息（缺省清空）。
     */
    setUser(user) {
        this.user = user;
    }
    /**
     * 整体替换成员花名册。
     *
     * @param users 成员信息（缺省清空）。
     */
    setUsers(users = []) {
        this.users.splice(0, this.users.length, ...users.map((item) => ({ ...item })));
    }
    /**
     * 增量合并成员花名册（同 id 覆盖，新项追加）。
     *
     * @param users 成员信息。
     */
    mergeUsers(users) {
        for (const item of users) {
            const exist = this.users.find((user) => user.id === item.id);
            if (exist === undefined) {
                this.users.push({ ...item });
            }
            else {
                Object.assign(exist, item);
            }
        }
    }
    /** 清空成员花名册。 */
    clearUsers() {
        this.users.splice(0, this.users.length);
    }
    /**
     * 按 id 查找成员。
     *
     * @param id 用户标识。
     */
    findUser(id) {
        return this.users.find((user) => user.id === id);
    }
    /**
     * 按 id 取展示信息（缺失回落 `id` 并标记已删除）。
     *
     * @param id 用户标识。
     */
    displayOf(id) {
        return this.findUser(id) ?? { id, name: id, deleted: true };
    }
    /** 姓名。 */
    get name() {
        return this.user?.name ?? '';
    }
    /** 头像地址。 */
    get avatar() {
        return this.user?.avatar;
    }
    /** 状态。 */
    get status() {
        return this.user?.status;
    }
    /** 部门路径。 */
    get deptPath() {
        return this.user?.deptPath;
    }
}
