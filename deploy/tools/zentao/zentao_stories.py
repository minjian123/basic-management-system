# -*- coding: utf-8 -*-
"""禅道需求 story API 操作（deploy/tools/zentao/zentao_stories.py）

创建必填：title、spec、pri（1-4）、category；reviewer 必须传数组（22.5 踩坑，见 create）。
category 枚举：feature 功能 / interface 接口 / performance 性能 /
safe 安全 / experience 体验 / improve 改进 / other 其他。
删除：REST DELETE /stories/:id 在 22.5 已验证可用（Web 删除需 confirm=yes 参数，作备用）。
"""
from zentao_client import ZentaoClient

CATEGORIES = ("feature", "interface", "performance", "safe", "experience", "improve", "other")


def list_(client, product=None, **kw):
    """需求列表（取全）；传 product 则取该产品下的需求。"""
    path = f"/products/{product}/stories" if product else "/stories"
    return client.fetch_all(path, **kw)


def get(client, story_id):
    return client.get(f"/stories/{story_id}")


def search(client, product=None, **filters):
    """按条件查询需求（客户端过滤）。product 指定产品（不传则全局）；
    filters 见 zentao_search.filter_items：name(匹配 title)/assigned_to/status/pri/
    deadline_from/deadline_to/est_from/est_to。"""
    from zentao_search import filter_items
    path = f"/products/{product}/stories" if product else "/stories"
    return filter_items(client.fetch_all(path), **filters)


def create(client, product, title, pri=2, category="feature", spec="", reviewer=None, **fields):
    """创建需求；product 走 URL 参数（body 亦可），title/spec/pri/category 必填。

    踩坑（22.5 实测）：REST 入口把 reviewer 默认成空字符串，服务端
    array_filter($_POST['reviewer'])（module/story/zen.php:1254）直接抛 TypeError，
    需求创建失败且返回 PHP 报错页。reviewer 必须传数组（账号名或用户 ID 均可）；
    不传时默认当前登录账号。
    """
    if category not in CATEGORIES:
        raise ValueError(f"category 取值应为 {CATEGORIES} 之一，实际 {category!r}")
    if reviewer is None:
        reviewer = [client.account]
    if isinstance(reviewer, str):
        reviewer = [reviewer]
    body = {"title": title, "spec": spec or title, "pri": pri,
            "category": category, "reviewer": reviewer, **fields}
    return client.post("/stories", body=body, params={"product": product})


def update(client, story_id, **fields):
    return client.put(f"/stories/{story_id}", body=fields)


def delete(client, story_id):
    return client.delete(f"/stories/{story_id}")


if __name__ == "__main__":  # 简单自测
    c = ZentaoClient()
    print(list_(c, product=1))
