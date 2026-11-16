"""通知服务入口：应用工厂 `ApplicationFactory`（共享基座 + 服务身份 / 路由 / 消费组）。"""

from fastapi import APIRouter

from bms_core.application import BaseServiceApplicationFactory
from bms_core.core.concurrent import ConcurrentStableList
from bms_core.core.config import Settings
from bms_core.events.consumer_records import EventConsumerRecord
from bms_notification import CONTRACT_VERSION, SERVICE_NAME, SERVICE_TITLE, __version__
from bms_notification.api.router import api_router
from bms_notification.domains.notification.center import DatabaseNotificationCenter
from bms_notification.domains.notification.consumers import event_consumer_records


class ApplicationFactory(BaseServiceApplicationFactory):
    """应用工厂：通知服务（通用装配由共享基座承载）。"""

    key: str = "application_factory"
    service_name: str = SERVICE_NAME
    service_title: str = SERVICE_TITLE
    version: str = __version__
    contract_version: str = CONTRACT_VERSION

    def prepare_settings(self, settings: Settings) -> None:
        """启用真实通知中心与通知偏好读取（未显式配置时）。

        `[notification_center].provider` / `[notification_preference].provider` 未显式配置时分别置
        `db` / `http`；显式配置（含 `null`）一律尊重——便于联调期临时回退占位实现。

        Args:
            settings: 应用配置（可变）。
        """
        if not settings.notification_center.provider:
            settings.notification_center.provider = DatabaseNotificationCenter.plugin_name
        if not settings.notification_preference.provider:
            settings.notification_preference.provider = "http"

    def service_routers(self) -> ConcurrentStableList[APIRouter]:
        """业务路由（探针路由由基座统一挂载）。

        Returns:
            ConcurrentStableList[APIRouter]: 业务聚合路由。
        """
        return ConcurrentStableList([api_router])

    def event_consumer_records(self) -> ConcurrentStableList[EventConsumerRecord]:
        """本服务自持的事件消费组声明（通知组）。

        Returns:
            ConcurrentStableList[EventConsumerRecord]: 消费组声明。
        """
        return event_consumer_records()
