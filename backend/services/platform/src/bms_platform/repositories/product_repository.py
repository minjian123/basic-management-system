"""产品档案仓储（平台服务自有）：产品档案只读查询（按状态 / 单条 / 分页）。

- 归属：读 `sys_product`（`platform` 服务 × 平台服务库 `bms_platform`；R4.1 产品注册机制）；
- 会话经构造注入（`get_db` / `get_platform_read_db` 同一请求同会话）；只读、不提交；
- 仅提供读方法，**不提供写接口**（注册运行时只读边界）；写路径仅开发期种子脚本 `ops/seed_module.py`；
- 对外 HTTP 只读出口（`GET /api/v1/products`）经 `bms_platform/api/products.py` 取用（R4.2）。
"""

from sqlalchemy import ColumnElement, func, select

from bms_core.core.concurrent import ConcurrentStableList, ConcurrentStableSet
from bms_core.repositories.base_db_repository import BaseDbRepository
from bms_core.schemas.pagination import BasePageQuery
from bms_platform.models.catalog import SysProduct


class ProductRepository(BaseDbRepository[SysProduct]):
    """产品档案仓储（`sys_product` 只读查询）。

    `sys_product` 除主键外无单列索引（`product_key` 为复合唯一约束、`deleted_at` 由公共软删除索引承担），
    故本仓储不提供排序参数（`sortable_fields` 仅主键），查询按 `id` 升序稳定返回。
    """

    model = SysProduct
    sortable_fields = ConcurrentStableSet({"id"})

    def _product_conditions(self, *, status: str | None = None) -> ConcurrentStableList[ColumnElement[bool]]:
        """构造产品档案筛选条件（列表 / 分页同源，防口径漂移）。

        Args:
            status: 状态筛选（`enabled` / `disabled` / `planned` / `retired`）；None 不过滤。

        Returns:
            ConcurrentStableList[ColumnElement[bool]]: 条件表达式列表。
        """
        conditions: ConcurrentStableList[ColumnElement[bool]] = ConcurrentStableList()
        if status is not None:
            conditions.add(self._column("status") == status)
        return conditions

    async def list_products(self, *, status: str | None = None) -> ConcurrentStableList[SysProduct]:
        """按状态查询产品档案（默认全部，`id` 升序）。

        Args:
            status: 状态筛选（`enabled` / `disabled` / `planned` / `retired`）；None 不过滤。

        Returns:
            ConcurrentStableList[SysProduct]: 记录列表。
        """
        conditions = self._product_conditions(status=status)
        statement = self._select().where(*conditions).order_by(self._column("id").asc())
        result = await self._session.execute(statement)
        return ConcurrentStableList(result.scalars().all())

    async def page_products(
        self,
        query: BasePageQuery,
        *,
        status: str | None = None,
    ) -> tuple[ConcurrentStableList[SysProduct], int]:
        """分页查询产品档案（筛选 + 排序 + 当前页 + 筛选后总数）。

        Args:
            query: 页码分页请求（含排序参数；排序经仓储白名单校验、非法忽略）。
            status: 状态筛选（`enabled` / `disabled` / `planned` / `retired`）；None 不过滤。

        Returns:
            tuple[ConcurrentStableList[SysProduct], int]: (当前页记录, 筛选后总数)。
        """
        conditions = self._product_conditions(status=status)
        statement = self._apply_sort(self._select().where(*conditions), self._resolve_sort(query))
        statement = statement.limit(query.size).offset((query.page - 1) * query.size)
        rows = ConcurrentStableList((await self._session.execute(statement)).scalars().all())
        count_statement = select(func.count()).select_from(self.model).where(*self._scope_where(), *conditions)
        total = int((await self._session.execute(count_statement)).scalar_one())
        return rows, total

    async def get_by_key(self, product_key: str) -> SysProduct | None:
        """按 `product_key` 查询单条记录（作用域过滤；不存在返回 None）。

        Args:
            product_key: 产品标识。

        Returns:
            SysProduct | None: 记录；不存在返回 None。
        """
        statement = self._select().where(self._column("product_key") == product_key)
        return (await self._session.execute(statement)).scalar_one_or_none()
