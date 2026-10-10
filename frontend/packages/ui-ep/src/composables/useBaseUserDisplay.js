/** 用户展示投影：把核心用户展示能力基类 `BaseUserDisplay` 投影为组合式（姓名 / 头像 / 状态 / 部门路径 + 成员花名册）。 */
import { BaseUserDisplay } from '@bms/core';
import { onScopeDispose, ref } from 'vue';
/** 具体用户展示（可实例化，花名册方法触发更新通知）。 */
class UserDisplayState extends BaseUserDisplay {
    setUser(user) {
        super.setUser(user);
        this.notifyLifecycle('update');
    }
    setUsers(users = []) {
        super.setUsers(users);
        this.notifyLifecycle('update');
    }
    mergeUsers(users) {
        super.mergeUsers(users);
        this.notifyLifecycle('update');
    }
    clearUsers() {
        super.clearUsers();
        this.notifyLifecycle('update');
    }
}
/**
 * 使用用户展示投影。
 *
 * @param initial 初始用户信息。
 * @returns 用户展示基类实例与响应式面。
 */
export function useBaseUserDisplay(initial) {
    const userDisplay = new UserDisplayState();
    if (initial) {
        userDisplay.setUser(initial);
    }
    const user = ref(userDisplay.user);
    const name = ref(userDisplay.name);
    const avatar = ref(userDisplay.avatar);
    const status = ref(userDisplay.status);
    const deptPath = ref(userDisplay.deptPath);
    const users = ref([...userDisplay.users]);
    function sync() {
        user.value = userDisplay.user;
        name.value = userDisplay.name;
        avatar.value = userDisplay.avatar;
        status.value = userDisplay.status;
        deptPath.value = userDisplay.deptPath;
        users.value = [...userDisplay.users];
    }
    const off = userDisplay.onLifecycle((event) => {
        if (event === 'update') {
            sync();
        }
    });
    onScopeDispose(off);
    return {
        userDisplay,
        user,
        name,
        avatar,
        status,
        deptPath,
        users,
        setUser: (next) => userDisplay.setUser(next),
        setUsers: (next) => userDisplay.setUsers(next),
        mergeUsers: (next) => userDisplay.mergeUsers(next),
        clearUsers: () => userDisplay.clearUsers(),
        findUser: (id) => userDisplay.findUser(id),
        displayOf: (id) => userDisplay.displayOf(id),
    };
}
