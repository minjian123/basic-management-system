"""平台默认事件契约：架构《接口与集成》「事件模型清单」平台域部分的机读声明（v1.0.0）。

- 覆盖平台域事件（`sys` / `wf` / `file` / `notification` / `tenant` / `identity` 事件域）；
- 产品域事件（`pur` / `pay` / `sale` / `wh` / `sup` / `cw`）由产品仓库随服务实现声明，本模块不代声明；
- 字段取「事件模型清单」的「主要载荷」列（字段级规格为对外契约，新增只增不删、必须可选）；
- 经 `register_platform_event_contracts()` 幂等登记进默认注册表（应用装配与快照 CLI 共用）。

> 事件命名规则（首段为已登记事件域）见《命名规范》「基础设施命名」节；契约规则见
> `bms_core/events/contracts.py` 与《后端开发规范》「事件与任务规范」节。
"""

from bms_core.events.contracts import (
    EventContract,
    EventContractRegistry,
    EventFieldSpec,
    EventSubscription,
    default_event_contract_registry,
)

__all__ = [
    "PLATFORM_EVENT_CONTRACTS",
    "PLATFORM_EVENT_SUBSCRIPTIONS",
    "register_platform_event_contracts",
]

_STRING_REQUIRED = EventFieldSpec(type="string", required=True)
_STRING_OPTIONAL = EventFieldSpec(type="string")
_INTEGER_REQUIRED = EventFieldSpec(type="integer", required=True)
_BOOLEAN_REQUIRED = EventFieldSpec(type="boolean", required=True)

_USER_PAYLOAD: dict[str, EventFieldSpec] = {
    "user_id": _STRING_REQUIRED,
    "username": _STRING_REQUIRED,
    "dept_id": _STRING_OPTIONAL,
    "status": _STRING_REQUIRED,
}

_HELP_ARTICLE_PAYLOAD: dict[str, EventFieldSpec] = {
    "article_id": _STRING_REQUIRED,
    "category_id": _STRING_OPTIONAL,
    "target_key": _STRING_OPTIONAL,
}

_TENANT_PAYLOAD: dict[str, EventFieldSpec] = {
    "tenant_code": _STRING_REQUIRED,
    "db_key": _STRING_REQUIRED,
    "status": _STRING_REQUIRED,
}

PLATFORM_EVENT_CONTRACTS: tuple[EventContract, ...] = (
    EventContract(event_type="sys.user.created", description="用户创建后", fields=dict(_USER_PAYLOAD)),
    EventContract(event_type="sys.user.updated", description="用户修改后", fields=dict(_USER_PAYLOAD)),
    EventContract(event_type="sys.user.deleted", description="用户删除后", fields=dict(_USER_PAYLOAD)),
    EventContract(
        event_type="sys.user.password_reset",
        description="管理员重置密码或自助找回后",
        fields={"user_id": _STRING_REQUIRED},
    ),
    EventContract(
        event_type="sys.dept.changed",
        description="部门增删改 / 移动",
        fields={"dept_id": _STRING_REQUIRED, "parent_id": _STRING_OPTIONAL},
    ),
    EventContract(
        event_type="wf.process.deployed",
        description="流程定义发布新版本",
        fields={"definition_key": _STRING_REQUIRED, "version": _STRING_REQUIRED},
    ),
    EventContract(
        event_type="wf.instance.started",
        description="流程实例启动",
        fields={
            "instance_id": _STRING_REQUIRED,
            "business_type": _STRING_REQUIRED,
            "business_id": _STRING_REQUIRED,
        },
    ),
    EventContract(
        event_type="wf.task.completed",
        description="审批节点通过",
        fields={
            "task_id": _STRING_REQUIRED,
            "instance_id": _STRING_REQUIRED,
            "approver": _STRING_REQUIRED,
            "action": _STRING_REQUIRED,
        },
    ),
    EventContract(
        event_type="wf.instance.rejected",
        description="流程被驳回",
        fields={"instance_id": _STRING_REQUIRED, "node_id": _STRING_REQUIRED, "comment": _STRING_OPTIONAL},
    ),
    EventContract(
        event_type="wf.instance.finished",
        description="流程实例结束",
        fields={"instance_id": _STRING_REQUIRED, "result": _STRING_REQUIRED},
    ),
    EventContract(
        event_type="file.uploaded",
        description="文件上传完成",
        fields={"file_id": _STRING_REQUIRED, "sha256": _STRING_REQUIRED, "size": _INTEGER_REQUIRED},
    ),
    EventContract(
        event_type="notification.sent",
        description="通知 / 邮件 / 短信发送",
        fields={"user_id": _STRING_REQUIRED, "type": _STRING_REQUIRED, "biz_type": _STRING_OPTIONAL},
    ),
    EventContract(
        event_type="sys.notice.published",
        description="公告发布 / 更新 / 下线",
        fields={"notice_id": _STRING_REQUIRED, "title": _STRING_REQUIRED, "is_top": _BOOLEAN_REQUIRED},
    ),
    EventContract(
        event_type="sys.form.updated",
        description="菜单 / 表单 / 字段 / 按钮变更（平台统一维护）",
        fields={
            "form_id": _STRING_REQUIRED,
            "menu_id": _STRING_OPTIONAL,
            "business_id": _STRING_OPTIONAL,
            "changed_type": _STRING_REQUIRED,
        },
    ),
    EventContract(
        event_type="sys.help.article.published",
        description="帮助文章发布",
        fields=dict(_HELP_ARTICLE_PAYLOAD),
    ),
    EventContract(
        event_type="sys.help.article.updated",
        description="帮助文章更新",
        fields=dict(_HELP_ARTICLE_PAYLOAD),
    ),
    EventContract(
        event_type="sys.help.article.deleted",
        description="帮助文章删除",
        fields=dict(_HELP_ARTICLE_PAYLOAD),
    ),
    EventContract(
        event_type="sys.task.completed",
        description="定时任务执行完成",
        fields={"task_id": _STRING_REQUIRED, "status": _STRING_REQUIRED},
    ),
    EventContract(event_type="tenant.created", description="租户开通", fields=dict(_TENANT_PAYLOAD)),
    EventContract(event_type="tenant.suspended", description="租户停用", fields=dict(_TENANT_PAYLOAD)),
    EventContract(event_type="tenant.activated", description="租户启用", fields=dict(_TENANT_PAYLOAD)),
    EventContract(
        event_type="identity.user.jit_created",
        description="SSO 首登自动建号",
        fields={"user_id": _STRING_REQUIRED, "idp_key": _STRING_REQUIRED},
    ),
    EventContract(
        event_type="sys.archive.completed",
        description="归档批次完成",
        fields={"policy_id": _STRING_REQUIRED, "archived_count": _INTEGER_REQUIRED, "target": _STRING_REQUIRED},
    ),
)
"""平台默认事件契约（23 条；字段规格为对外契约，变更走兼容规则）。"""

PLATFORM_EVENT_SUBSCRIPTIONS: tuple[EventSubscription, ...] = ()
"""平台内建消费方订阅声明（本期为空；服务级订阅随消费方实现落地登记）。"""


def register_platform_event_contracts(registry: EventContractRegistry | None = None) -> None:
    """登记平台默认事件契约与订阅（幂等；应用装配与快照 CLI 共用）。

    Args:
        registry: 目标注册表（缺省默认注册表）。
    """
    target = registry or default_event_contract_registry()
    for contract in PLATFORM_EVENT_CONTRACTS:
        target.register(contract)
    for subscription in PLATFORM_EVENT_SUBSCRIPTIONS:
        target.register_subscription(subscription)
