# pyright: reportPrivateUsage=false, reportArgumentType=false, reportUnknownLambdaType=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false

"""事件主题供给用例（Kiwi 2532）：主题派生 / 幂等创建与扩容 / 租户清单 / 只读校验 / 命令行分支。

不发真实请求：HTTP 客户端用替身按预设响应返回，只为验证「派生 → 请求 → 结果归类」这条链路。
"""

import runpy
import sys
from types import SimpleNamespace
from typing import cast

import httpx
import pytest

from bms_core.core.concurrent import (
    ConcurrentStableDict,
    ConcurrentStableFrozenDict,
    ConcurrentStableList,
)
from bms_core.core.config import Settings
from bms_core.events.base import EventConsumer
from bms_core.events.consumer_records import EventConsumerRecord
from bms_core.servicecall.base import DEFAULT_BASE_URL_TEMPLATE
from ops import event_topics
from ops.event_topics import (
    _check,
    _ensure_topic,
    _find_topic,
    _group_topics,
    _partitions_for,
    _tenant_base_url,
    _topic_specs,
    main,
)

pytestmark = pytest.mark.kiwi_id(2532)


class _Response:
    """HTTP 响应替身（状态码 + 可解析体 / 解析异常）。"""

    def __init__(self, *, status_code: int = 200, payload: object = None, json_error: bool = False) -> None:
        """初始化响应替身。"""
        self.status_code = status_code
        self._payload = payload
        self._json_error = json_error

    def json(self) -> object:
        """返回预设体（或抛解析异常）。"""
        if self._json_error:
            raise ValueError("响应不是 JSON")
        return self._payload


class _Client:
    """HTTP 客户端替身：按队列返回响应 / 抛异常，并记录调用。"""

    def __init__(self, responses: ConcurrentStableList[object] | None = None) -> None:
        """初始化预设响应队列。"""
        self.responses = list(responses or ConcurrentStableList())
        self.calls: ConcurrentStableList[tuple[str, str, object, object]] = ConcurrentStableList()

    def __enter__(self) -> _Client:
        """支持 `with httpx.Client(...)` 形态。"""
        return self

    def __exit__(self, *_: object) -> None:
        """退出上下文（无资源）。"""
        return None

    def get(self, url: str) -> _Response:
        """GET 调用。"""
        self.calls.add(("GET", url, None, None))
        return cast("_Response", self._next())

    def request(
        self,
        method: str,
        url: str,
        json: object = None,
        headers: object = None,
    ) -> _Response:
        """通用请求调用。"""
        self.calls.add((method, url, json, headers))
        return cast("_Response", self._next())

    def _next(self) -> object:
        """取下一个预设项（异常项直接抛出）。"""
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _ok(payload: object, status_code: int = 200) -> _Response:
    """成功响应。"""
    return _Response(status_code=status_code, payload=payload)


def _msg_body(code: int, **extra: object) -> object:
    """msg 统一响应体（普通字典，贴合 `json()` 的真实返回类型）。"""
    return {"code": code, "message": "msg", "data": None, **extra}


def _settings(
    endpoints: ConcurrentStableFrozenDict[str, str] | None = None,
    options: ConcurrentStableFrozenDict[str, object] | None = None,
) -> Settings:
    """最小配置替身（只填主题供给用到的字段）。"""
    return cast(
        "Settings",
        SimpleNamespace(
            service_client=SimpleNamespace(
                endpoints=endpoints if endpoints is not None else ConcurrentStableFrozenDict[str, str](),
                options=options if options is not None else ConcurrentStableFrozenDict[str, object](),
            )
        ),
    )


def _record(consumer: str, event_type: str) -> EventConsumerRecord:
    """消费组声明替身。"""
    return EventConsumerRecord(
        consumer=consumer,
        event_type=event_type,
        handler_factory=lambda: cast("EventConsumer", None),
    )


def test_topic_specs_derive_and_merge() -> None:
    """按事件契约派生主题：命名空间取事件域、同主题多事件合并、按命名空间 + 主题排序。"""
    specs = _topic_specs()
    topics = [spec.topic for spec in specs]

    assert topics == sorted(topics)
    assert len(topics) == len(set(topics))
    audit = next(spec for spec in specs if spec.topic == "bms-sys-operation")
    assert audit.namespace == "sys"
    assert "sys.operation.logged" in audit.event_types
    assert all(spec.topic.startswith("bms-") for spec in specs)
    assert all(spec.namespace for spec in specs)


def test_partitions_for_audit_and_default() -> None:
    """审计三主题取审计分区数，其余取默认值。"""
    assert _partitions_for("bms-sys-operation", audit=4, default=1) == 4
    assert _partitions_for("bms-sys-user", audit=4, default=1) == 1


def test_tenant_base_url_explicit_and_template() -> None:
    """租户服务基址：显式覆盖优先并去尾斜线，缺省按模板替换服务键。"""
    explicit = _settings(ConcurrentStableFrozenDict({"tenant": "http://tenant:9000/"}))
    assert _tenant_base_url(explicit) == "http://tenant:9000"

    template = _settings(ConcurrentStableFrozenDict({"base_url": "http://svc:8000"}))
    assert _tenant_base_url(template) == "http://tenant:8000"

    assert _tenant_base_url(_settings()) == DEFAULT_BASE_URL_TEMPLATE.replace("{service}", "tenant")


def test_active_tenants_parses_codes_and_skips_invalid(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """租户清单：只收对象里的字符串编码，非对象 / 非字符串项跳过。"""
    payload = {
        "data": {
            "items": [
                {"code": "acme"},
                "bad",
                {"code": 7},
                {"code": "demo"},
            ]
        }
    }
    client = _Client(ConcurrentStableList([_ok(payload)]))

    codes = event_topics._active_tenants(client, _settings())  # pyright: ignore[reportPrivateUsage]

    assert list(codes) == ["acme", "demo"]
    assert client.calls[0][1].endswith("/api/v1/tenant-registry/active")


def test_active_tenants_failure_branches(capsys: pytest.CaptureFixture[str]) -> None:
    """租户清单失败分支：不可达 / 非 200 / 非 JSON / 缺 items 均退出码 1。"""
    cases: ConcurrentStableList[tuple[_Client, str]] = ConcurrentStableList(
        [
            (_Client(ConcurrentStableList([httpx.HTTPError("kill")])), "租户清单不可达"),
            (_Client(ConcurrentStableList([_ok({}, status_code=500)])), "租户清单调用失败"),
            (_Client(ConcurrentStableList([_Response(json_error=True)])), "不是合法 JSON"),
            (_Client(ConcurrentStableList([_ok({"data": {}})])), "缺少 data.items"),
        ]
    )
    for client, keyword in cases:
        with pytest.raises(SystemExit) as excinfo:
            event_topics._active_tenants(client, _settings())  # pyright: ignore[reportPrivateUsage]
        assert excinfo.value.code == 1
        assert keyword in capsys.readouterr().err


def test_request_payload_headers_and_failure_branches(capsys: pytest.CaptureFixture[str]) -> None:
    """请求封装：GET 不带体、POST 带体与租户头；网络异常 / 非 JSON / 非对象响应退出码 1。"""
    client = _Client(
        ConcurrentStableList(
            [
                _ok(_msg_body(0)),
                _ok(_msg_body(0)),
            ]
        )
    )
    status, body = event_topics._request(client, "GET", "http://msg/x", "acme", None)  # pyright: ignore[reportPrivateUsage]
    assert status == 200 and body.get("code") == 0
    assert client.calls[0][2] is None
    assert dict(cast("dict[str, str]", client.calls[0][3])) == {"X-Tenant-ID": "acme"}

    payload: ConcurrentStableDict[str, object] = ConcurrentStableDict({"a": 1})
    event_topics._request(client, "POST", "http://msg/x", "acme", payload)  # pyright: ignore[reportPrivateUsage]
    assert dict(cast("dict[str, object]", client.calls[1][2])) == {"a": 1}

    bad_cases: ConcurrentStableList[tuple[_Client, str]] = ConcurrentStableList(
        [
            (_Client(ConcurrentStableList([httpx.HTTPError("kill")])), "msg 管理端点不可达"),
            (_Client(ConcurrentStableList([_Response(json_error=True)])), "不是 JSON"),
            (_Client(ConcurrentStableList([_ok([])])), "不是对象"),
        ]
    )
    for bad_client, keyword in bad_cases:
        with pytest.raises(SystemExit) as excinfo:
            event_topics._request(bad_client, "GET", "http://msg/x", "acme", None)  # pyright: ignore[reportPrivateUsage]
        assert excinfo.value.code == 1
        assert keyword in capsys.readouterr().err


def test_find_topic_matches_exact_name_and_tolerates_bad_payload() -> None:
    """查主题：按名称精确命中；非 200 / 缺 items / 元素非对象 / 无同名均按不存在。"""
    match = {
        "data": {
            "items": [
                "bad",
                {"name": "bms-sys-user-other", "partition_count": 1},
                {"name": "bms-sys-user", "partition_count": 2, "id": 9},
            ]
        }
    }
    client = _Client(ConcurrentStableList([_ok(match)]))
    found = _find_topic(client, "http://msg", "acme", "sys", "bms-sys-user")
    assert found is not None and found.get("partition_count") == 2
    assert "namespace=sys" in client.calls[0][1] and "keyword=bms-sys-user" in client.calls[0][1]

    missing_cases: ConcurrentStableList[tuple[_Client, object]] = ConcurrentStableList(
        [
            (_Client(ConcurrentStableList([_ok({}, status_code=500)])), None),
            (_Client(ConcurrentStableList([_ok({"data": {}})])), None),
            (_Client(ConcurrentStableList([_ok({"data": {"items": [{"name": "other"}]}})])), None),
        ]
    )
    for missing_client, expected in missing_cases:
        assert _find_topic(missing_client, "http://msg", "acme", "sys", "bms-sys-user") is expected


def _spec(topic: str = "bms-sys-user", namespace: str = "sys") -> event_topics._TopicSpec:
    """主题规格替身。"""
    return event_topics._TopicSpec(
        namespace=namespace, topic=topic, event_types=ConcurrentStableList([f"{namespace}.user.created"])
    )


def test_ensure_topic_dry_run_created_and_skips(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """幂等创建：计划态不请求；成功创建；命名空间未启用 / 租户缺失 / 其他失败分别归类。"""
    client = _Client()
    assert _ensure_topic(client, "http://msg", "acme", _spec(), 1, dry_run=True) == "planned"
    assert len(client.calls) == 0
    assert "[计划]" in capsys.readouterr().out

    cases: ConcurrentStableList[tuple[int, str]] = ConcurrentStableList(
        [
            (0, "created"),
            (event_topics._NAMESPACE_INVALID, "namespace-disabled"),
            (event_topics._TENANT_NOT_FOUND, "tenant-missing"),
            (999, "failed"),
        ]
    )
    for code, expected in cases:
        result = _ensure_topic(
            _Client(ConcurrentStableList([_ok(_msg_body(code))])), "http://msg", "acme", _spec(), 1, dry_run=False
        )
        assert result == expected
    assert "[创建]" in capsys.readouterr().out


def test_ensure_topic_existing_paths(capsys: pytest.CaptureFixture[str]) -> None:
    """已存在分支：查询不到 / 扩容成功 / 分区数非法 / 扩容失败 / 现有分区更大 / 恰好相等。"""
    list_payload = {"data": {"items": [{"name": "bms-sys-user", "partition_count": 1, "id": 9}]}}

    not_found = _ensure_topic(
        _Client(ConcurrentStableList([_ok(_msg_body(event_topics._TOPIC_EXISTS)), _ok({"data": {"items": []}})])),
        "http://msg",
        "acme",
        _spec(),
        1,
        dry_run=False,
    )
    assert not_found == "failed"

    expanded = _ensure_topic(
        _Client(
            ConcurrentStableList(
                [
                    _ok(_msg_body(event_topics._TOPIC_EXISTS)),
                    _ok(list_payload),
                    _ok(_msg_body(0)),
                ]
            )
        ),
        "http://msg",
        "acme",
        _spec(),
        4,
        dry_run=False,
    )
    assert expanded == "expanded"

    expand_invalid = _ensure_topic(
        _Client(
            ConcurrentStableList(
                [
                    _ok(_msg_body(event_topics._TOPIC_EXISTS)),
                    _ok(list_payload),
                    _ok(_msg_body(event_topics._PARTITION_INVALID)),
                ]
            )
        ),
        "http://msg",
        "acme",
        _spec(),
        4,
        dry_run=False,
    )
    assert expand_invalid == "failed"

    expand_failed = _ensure_topic(
        _Client(
            ConcurrentStableList(
                [
                    _ok(_msg_body(event_topics._TOPIC_EXISTS)),
                    _ok(list_payload),
                    _ok(_msg_body(999)),
                ]
            )
        ),
        "http://msg",
        "acme",
        _spec(),
        4,
        dry_run=False,
    )
    assert expand_failed == "failed"

    larger = _ensure_topic(
        _Client(
            ConcurrentStableList(
                [
                    _ok(_msg_body(event_topics._TOPIC_EXISTS)),
                    _ok({"data": {"items": [{"name": "bms-sys-user", "partition_count": 10, "id": 9}]}}),
                ]
            )
        ),
        "http://msg",
        "acme",
        _spec(),
        1,
        dry_run=False,
    )
    assert larger == "larger"

    # 现有分区字段非整数按 0 处理（目标 1 → 走扩容）。
    non_int = _ensure_topic(
        _Client(
            ConcurrentStableList(
                [
                    _ok(_msg_body(event_topics._TOPIC_EXISTS)),
                    _ok({"data": {"items": [{"name": "bms-sys-user", "partition_count": "bad", "id": 9}]}}),
                    _ok(_msg_body(0)),
                ]
            )
        ),
        "http://msg",
        "acme",
        _spec(),
        1,
        dry_run=False,
    )
    assert non_int == "expanded"

    equal = _ensure_topic(
        _Client(
            ConcurrentStableList(
                [
                    _ok(_msg_body(event_topics._TOPIC_EXISTS)),
                    _ok({"data": {"items": [{"name": "bms-sys-user", "partition_count": 4, "id": 9}]}}),
                ]
            )
        ),
        "http://msg",
        "acme",
        _spec(),
        4,
        dry_run=False,
    )
    assert equal == "exists"
    out = capsys.readouterr().out
    assert "[扩容]" in out and "[存在]" in out and "[提示]" in out


def test_group_topics_groups_unique_topics(monkeypatch: pytest.MonkeyPatch) -> None:
    """组 → 主题映射：同组多事件同主题去重，不同组分开。"""
    records: ConcurrentStableList[EventConsumerRecord] = ConcurrentStableList(
        [
            _record("bms-audit-chain", "sys.operation.logged"),
            _record("bms-audit-chain", "sys.operation.updated"),
            _record("bms-audit-chain", "sys.login.logged"),
            _record("bms-notify", "notification.requested"),
        ]
    )
    monkeypatch.setattr(event_topics, "load_records", lambda *args, **kwargs: records)
    monkeypatch.setattr(event_topics, "service_factory", lambda service: cast("object", None))

    groups = _group_topics("platform", group_prefix="bms-")

    assert list(groups["bms-audit-chain"]) == ["bms-sys-operation", "bms-sys-login"]
    assert list(groups["bms-notify"]) == ["bms-notification-requested"]


def _fake_find(counts: ConcurrentStableDict[str, object]):
    """构造按主题返回分区数的 `_find_topic` 替身。"""

    def _find(
        client: object, base: str, tenant: str, namespace: str, topic: str
    ) -> ConcurrentStableDict[str, object] | None:
        del client, base, tenant
        if topic not in counts:
            return None
        raw = counts.get(topic)
        if raw is None:
            return None
        return ConcurrentStableDict({"name": topic, "namespace": namespace, "partition_count": raw})

    return _find


def test_check_reports_gaps(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """只读校验：缺主题 / 分区不足 / 同组分区数不一致均报缺口（退出码 1），并跳过无关组主题。"""
    specs: ConcurrentStableList[event_topics._TopicSpec] = ConcurrentStableList(
        [_spec("bms-sys-operation"), _spec("bms-sys-login"), _spec("bms-sys-user")]
    )
    groups: ConcurrentStableDict[str, ConcurrentStableList[str]] = ConcurrentStableDict(
        {
            "bms-audit-chain": ConcurrentStableList(["bms-sys-operation", "bms-sys-login"]),
            "bms-unrelated": ConcurrentStableList(["bms-not-in-specs"]),
        }
    )
    counts: ConcurrentStableDict[str, object] = ConcurrentStableDict({"bms-sys-operation": 4, "bms-sys-login": 2})
    monkeypatch.setattr(event_topics, "_find_topic", _fake_find(counts))

    code = _check(
        _Client(),
        "http://msg",
        specs,
        ConcurrentStableList(["acme"]),
        audit=4,
        default=1,
        groups=groups,
    )
    assert code == 1
    err = capsys.readouterr().err
    assert "bms-sys-user：主题不存在" in err
    assert "bms-sys-login：分区 2 < 目标 4" in err
    assert "分区数不一致" in err


def test_check_passes_when_all_ready(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """只读校验通过：全部主题存在且分区达标（退出码 0）。"""
    specs: ConcurrentStableList[event_topics._TopicSpec] = ConcurrentStableList(
        [_spec("bms-sys-operation"), _spec("bms-sys-user")]
    )
    counts: ConcurrentStableDict[str, object] = ConcurrentStableDict({"bms-sys-operation": 4, "bms-sys-user": 1})
    monkeypatch.setattr(event_topics, "_find_topic", _fake_find(counts))

    code = _check(
        _Client(),
        "http://msg",
        specs,
        ConcurrentStableList(["acme", "demo"]),
        audit=4,
        default=1,
        groups=ConcurrentStableDict(),
    )
    assert code == 0
    assert "主题校验通过：2 个租户 × 2 个主题" in capsys.readouterr().out


def _patch_main(monkeypatch: pytest.MonkeyPatch, client: _Client) -> ConcurrentStableList[object]:
    """按测试需要打桩 `main` 的外部依赖，返回记录调用参数的容器。"""
    captured: ConcurrentStableList[object] = ConcurrentStableList()
    monkeypatch.setattr(event_topics, "get_settings", lambda: _settings_with_prefix())
    monkeypatch.setattr(event_topics, "_msg_base", lambda settings: "http://msg")
    monkeypatch.setattr(event_topics, "_topic_specs", lambda: ConcurrentStableList([_spec()]))
    monkeypatch.setattr(event_topics, "_group_topics", lambda *args, **kwargs: ConcurrentStableDict())
    monkeypatch.setattr(event_topics.httpx, "Client", lambda **kwargs: client)

    def _check_recorder(*args: object, **kwargs: object) -> int:
        captured.add((args, kwargs))
        return 0

    monkeypatch.setattr(event_topics, "_check", _check_recorder)
    return captured


def _settings_with_prefix() -> Settings:
    """带消费组前缀的配置替身。"""
    settings = _settings()
    cast("SimpleNamespace", settings).event_consumer = SimpleNamespace(group_prefix="bms-")
    return settings


def test_main_dry_run_with_explicit_tenants(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """命令行计划态：显式租户不查清单、不发写请求，退出码 0。"""
    client = _Client()
    _patch_main(monkeypatch, client)

    code = main(ConcurrentStableList(["--tenant", "acme", "--tenant", "demo", "--dry-run"]))

    assert code == 0
    out = capsys.readouterr().out
    assert out.count("[计划]") == 2
    assert len(client.calls) == 0


def test_main_ensure_reports_failures(monkeypatch: pytest.MonkeyPatch) -> None:
    """命令行创建态：任一主题失败即退出码 1；租户来自 `/active` 清单。"""
    client = _Client(
        ConcurrentStableList(
            [
                _ok({"data": {"items": [{"code": "acme"}]}}),
                _ok(_msg_body(999)),
            ]
        )
    )
    _patch_main(monkeypatch, client)

    code = main(ConcurrentStableList([]))

    assert code == 1
    assert client.calls[0][1].endswith("/api/v1/tenant-registry/active")
    assert client.calls[1][0] == "POST"


def test_main_without_tenants_returns_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """命令行：租户清单为空时直接返回 0（无可处理租户）。"""
    client = _Client(ConcurrentStableList([_ok({"data": {"items": []}})]))
    _patch_main(monkeypatch, client)

    assert main(ConcurrentStableList([])) == 0
    assert "没有可处理的租户" in capsys.readouterr().out


def test_main_check_delegates_and_uses_tenant_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """命令行只读校验：转交 `_check`，并把分区参数 / 显式租户透传。"""
    client = _Client()
    captured = _patch_main(monkeypatch, client)

    code = main(
        ConcurrentStableList(["--check", "--tenant", "acme", "--partitions-audit", "8", "--partitions-default", "2"])
    )

    assert code == 0
    args, kwargs = cast("tuple[tuple[object, ...], dict[str, object]]", captured[0])
    assert list(cast("ConcurrentStableList[str]", args[3])) == ["acme"]
    assert kwargs == {"audit": 8, "default": 2, "groups": ConcurrentStableDict()}


def test_module_entry_exposes_main(monkeypatch: pytest.MonkeyPatch) -> None:
    """`python -m ops.event_topics` 有入口：`__main__` 守卫把 `main()` 的退出码透传。"""
    client = _Client()
    _patch_main(monkeypatch, client)
    monkeypatch.setattr(sys, "argv", ["ops.event_topics", "--tenant", "acme", "--dry-run"])

    with (
        pytest.warns(RuntimeWarning, match="found in sys.modules"),
        pytest.raises(SystemExit) as excinfo,
    ):
        runpy.run_module("ops.event_topics", run_name="__main__")

    assert excinfo.value.code == 0
