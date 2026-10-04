"""滑块挑战真实实现测试（Kiwi 2205）：合成出图 / 轨迹判定 / 单次失效 / 失败计数 / 坐标不下发 /
fail-closed / 选项 / 装配。"""

import base64
import io
import json
from types import SimpleNamespace
from typing import Any, cast

import fakeredis.aioredis
import pytest
from fastapi import Request
from PIL import Image
from redis.asyncio import Redis

from bms_core.captcha.base import (
    BaseCaptcha,
    CaptchaCredential,
    CaptchaKind,
    build_captcha_key,
    get_captcha,
)
from bms_core.captcha.default import CaptchaSliderOptions, DefaultCaptcha
from bms_core.captcha.null import NullCaptcha
from bms_core.core import plugin as plugin_module
from bms_core.core.assembly import DefaultCaptchaFactory
from bms_core.core.concurrent import ConcurrentStableDict
from bms_core.core.config import PluginSelection, Settings
from bms_core.core.exceptions import (
    CaptchaExpiredError,
    CaptchaVerifyError,
    ParamError,
    PluginError,
    ServiceUnavailableError,
)
from bms_core.core.plugin import PluginRegistry

_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _captcha(client: object, **options: object) -> DefaultCaptcha:
    """构造滑块实现（注入测试客户端；选项经 `slider_` 前缀键）。

    Args:
        client: Redis 客户端替身。
        **options: 滑块选项覆盖。

    Returns:
        DefaultCaptcha: 验证码实现。
    """
    slider = CaptchaSliderOptions.from_options(ConcurrentStableDict(options)) if options else None
    return DefaultCaptcha(url=None, client=cast("Redis", client), slider=slider)


async def _record(client: Redis, captcha_id: str) -> ConcurrentStableDict[str, Any]:
    """读取挑战记录（直接查 Redis）。

    Args:
        client: Redis 客户端。
        captcha_id: 挑战编号。

    Returns:
        ConcurrentStableDict[str, Any]: 挑战记录。
    """
    raw = await client.get(build_captcha_key(captcha_id))
    assert raw is not None
    return ConcurrentStableDict(cast("dict[str, Any]", json.loads(raw)))


def _payload(challenge: Any) -> ConcurrentStableDict[str, Any]:
    """解析挑战 `payload`。

    Args:
        challenge: 挑战值对象。

    Returns:
        ConcurrentStableDict[str, Any]: `payload` 解析结果。
    """
    return ConcurrentStableDict(cast("dict[str, Any]", json.loads(challenge.payload)))


def _trace(gap_x: int, *, duration: int = 300, start: int = 0) -> tuple[tuple[int, int, int], ...]:
    """构造一条终点落在 `gap_x` 的两点轨迹。

    Args:
        gap_x: 终点横坐标。
        duration: 总时长（毫秒）。
        start: 起点时间（毫秒）。

    Returns:
        tuple: 轨迹点序列。
    """
    return ((0, 0, start), (gap_x, 0, start + duration))


@pytest.fixture
def redis_client() -> fakeredis.aioredis.FakeRedis:
    """fakeredis 客户端（与真实 redis-py 同接口，decode_responses）。"""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.kiwi_id(2205)
async def test_generate_slider_image_payload_and_record(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """合成出图：payload 含 background/slider（base64 PNG、尺寸随选项）与宽高、无坐标；记录含缺口位置。"""
    captcha = _captcha(redis_client, slider_width=240, slider_height=120, slider_piece_size=40)
    challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)

    assert challenge.kind is CaptchaKind.SLIDER
    assert challenge.image == b""
    assert challenge.expires_in == 300
    assert challenge.target == ""
    assert challenge.cooldown == 0

    raw = json.loads(challenge.payload)
    assert set(raw) == {"background", "slider", "width", "height", "piece_size", "piece_y"}
    # 横坐标 `gap_x` 为判定依据，**不得下发**；块图尺寸与纵坐标必须下发（客户端据此把块图绘到缺口高度）。
    assert "gap_x" not in challenge.payload
    assert raw["width"] == 240
    assert raw["height"] == 120
    assert raw["piece_size"] == 40
    assert isinstance(raw["piece_y"], int)
    assert 40 <= raw["piece_y"] < 120 - 40

    background = base64.b64decode(raw["background"])
    slider = base64.b64decode(raw["slider"])
    assert background.startswith(_PNG_MAGIC)
    assert slider.startswith(_PNG_MAGIC)
    assert Image.open(io.BytesIO(background)).size == (240, 120)
    assert Image.open(io.BytesIO(slider)).size == (40, 40)

    record = await _record(redis_client, challenge.captcha_id)
    assert record["kind"] == "slider"
    assert record["scene"] == "login"
    assert record["fails"] == 0
    assert isinstance(record["gap_x"], int)
    assert isinstance(record["gap_y"], int)
    assert 40 <= record["gap_x"] < 240 - 40
    assert 40 <= record["gap_y"] < 120 - 40
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
async def test_verify_slider_success_single_use(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """正确轨迹通过且单次失效（二次使用 20102）。"""
    captcha = _captcha(redis_client)
    challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    gap_x = (await _record(redis_client, challenge.captcha_id))["gap_x"]

    credential = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=_trace(gap_x))
    assert await captcha.verify_credential(credential)
    assert not await captcha.verify_credential(credential)

    with pytest.raises(CaptchaExpiredError) as raised:
        await captcha.require_credential(credential)
    assert raised.value.code == 20102
    assert raised.value.http_status == 404
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
async def test_verify_slider_mismatch_counts_and_retry(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """错位轨迹被拒（20101）、fails 递增且保留 TTL、可重试。"""
    captcha = _captcha(redis_client)
    challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    gap_x = (await _record(redis_client, challenge.captcha_id))["gap_x"]

    wrong = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=_trace(gap_x + 100))
    with pytest.raises(CaptchaVerifyError) as raised:
        await captcha.require_credential(wrong)
    assert raised.value.code == 20101
    assert raised.value.http_status == 200

    record = await _record(redis_client, challenge.captcha_id)
    assert record["fails"] == 1
    assert await redis_client.ttl(build_captcha_key(challenge.captcha_id)) > 0

    correct = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=_trace(gap_x))
    assert await captcha.verify_credential(correct)
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
async def test_verify_slider_machine_traces_rejected(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """机器轨迹被拒：点数不足、**瞬移且像素级对准**、时间回退、负时间。"""
    captcha = _captcha(redis_client)
    challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    gap_x = (await _record(redis_client, challenge.captcha_id))["gap_x"]

    cases: tuple[tuple[tuple[int, int, int], ...], ...] = (
        ((gap_x, 0, 300),),
        # 瞬移 + 像素级对准（偏差 0 ≤ exact_tolerance）：脚本特征，拒。
        ((0, 0, 0), (gap_x, 0, 40)),
        ((0, 0, 0), (gap_x, 0, 150)),
        ((0, 0, 500), (gap_x, 0, 100)),
        ((0, 0, -1), (gap_x, 0, 300)),
    )
    for trace in cases:
        assert not await captcha.verify_credential(
            CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=trace)
        )
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
async def test_verify_slider_human_traces_accepted(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """人类形态放行（回归）：快速但**略偏**、慢速略偏、慢速对准 —— 只要在落点容差内即通过；
    只有「瞬移 + 像素级对准」才判机器。

    （用户口径 2026-10-04：瞬时对准是机器人；慢慢对、不太准的反而可能是人。）
    """
    captcha = _captcha(redis_client)
    defaults = CaptchaSliderOptions.from_options(ConcurrentStableDict())
    allowed = defaults.tolerance
    exact = defaults.exact_tolerance

    # (时长, 落点偏差) —— 均应在容差内通过
    accepted: tuple[tuple[int, int], ...] = (
        (150, exact + 4),  # 快速但略偏（非像素级对准）
        (600, exact + 4),  # 慢速略偏（最像人）
        (600, 0),  # 慢速对准（人也能对准）
        (4000, 2),  # 更慢、更准
    )
    for duration, offset in accepted:
        challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
        gap_x = (await _record(redis_client, challenge.captcha_id))["gap_x"]
        trace = ((0, 0, 0), (gap_x + offset, 0, duration))
        assert await captcha.verify_credential(
            CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=trace)
        ), f"人类形态应放行：duration={duration} offset={offset}"

    # 落点超差（无论快慢）仍拒：超出 tolerance 即机器/乱拖
    for duration in (150, 600):
        challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
        gap_x = (await _record(redis_client, challenge.captcha_id))["gap_x"]
        trace = ((0, 0, 0), (gap_x + allowed + 3, 0, duration))
        assert not await captcha.verify_credential(
            CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=trace)
        ), f"落点超差应拒：duration={duration}"
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
async def test_slider_redis_unavailable_fail_closed() -> None:
    """Redis 不可用 fail-closed：出题 10007/503、校验 False、强制入口 20101。"""

    class _Broken:
        """恒抛连接异常的客户端替身。"""

        async def set(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

        async def pttl(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

        async def getdel(self, *args: object, **kwargs: object) -> None:
            """恒定抛错。"""
            raise ConnectionError("redis down")

    captcha = _captcha(_Broken())
    with pytest.raises(ServiceUnavailableError) as raised:
        await captcha.generate("login", kind=CaptchaKind.SLIDER)
    assert raised.value.code == 10007
    assert raised.value.http_status == 503

    credential = CaptchaCredential(captcha_id="x", kind=CaptchaKind.SLIDER, trace=_trace(0))
    assert not await captcha.verify_credential(credential)
    with pytest.raises(CaptchaVerifyError) as forced:
        await captcha.require_credential(credential)
    assert forced.value.code == 20101


@pytest.mark.kiwi_id(2205)
async def test_slider_dirty_record_and_empty_trace(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """脏值与空轨迹边界：gap_x 缺失 / 布尔 / 空轨迹均判不通过。"""

    class _Stub:
        """固定 `getdel` 返回值的客户端替身。"""

        def __init__(self, value: object) -> None:
            self._value = value

        async def pttl(self, key: str) -> int:
            """返回固定剩余有效期（毫秒）。"""
            return 300000

        async def getdel(self, key: str) -> object:
            """返回固定原始值。"""
            return self._value

        async def set(self, *args: object, **kwargs: object) -> None:
            """空实现（回写失败计数用）。"""

    credential = CaptchaCredential(captcha_id="x", kind=CaptchaKind.SLIDER, trace=_trace(5))
    assert not await _captcha(_Stub('{"kind": "slider", "fails": 0}')).verify_credential(credential)
    assert not await _captcha(_Stub('{"kind": "slider", "gap_x": true}')).verify_credential(credential)
    assert not await _captcha(_Stub('{"kind": "slider", "gap_x": "5"}')).verify_credential(credential)

    empty = CaptchaCredential(captcha_id="x", kind=CaptchaKind.SLIDER)
    assert not await _captcha(_Stub('{"kind": "slider", "gap_x": 5}')).verify_credential(empty)


@pytest.mark.kiwi_id(2205)
async def test_slider_options_parse_and_validate(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """滑块选项：缺省 / 覆盖 / 小画布块图钳制生效；非法值拒启；渲染尺寸随选项。"""
    default = CaptchaSliderOptions.from_options(ConcurrentStableDict[str, object]())
    assert (default.width, default.height, default.piece_size) == (300, 150, 48)
    assert (default.tolerance, default.min_duration_ms, default.min_points) == (10, 300, 2)
    assert default.exact_tolerance == 4
    assert default == CaptchaSliderOptions.from_options(None)

    # 「像素级对准」上限可配，且**不超过落点容差**（超过容差按容差收敛；越界类型/范围仍拒启）
    assert CaptchaSliderOptions.from_options(ConcurrentStableDict({"slider_exact_tolerance": 6})).exact_tolerance == 6
    assert CaptchaSliderOptions.from_options(ConcurrentStableDict({"slider_exact_tolerance": 40})).exact_tolerance == 10
    assert (
        CaptchaSliderOptions.from_options(
            ConcurrentStableDict({"slider_tolerance": 6, "slider_exact_tolerance": 8})
        ).exact_tolerance
        == 6
    )

    clamped = CaptchaSliderOptions.from_options(ConcurrentStableDict({"slider_width": 160, "slider_height": 80}))
    assert clamped.piece_size == 39
    small = DefaultCaptcha(url=None, client=redis_client, slider=clamped)
    small_challenge = await small.generate("login", kind=CaptchaKind.SLIDER)
    assert Image.open(io.BytesIO(base64.b64decode(_payload(small_challenge)["background"]))).size == (160, 80)
    await small.aclose()

    custom = CaptchaSliderOptions.from_options(
        ConcurrentStableDict(
            {
                "slider_width": "200",
                "slider_height": 100,
                "slider_piece_size": 30,
                "slider_tolerance": 5,
                "slider_min_duration_ms": 0,
                "slider_min_points": 1,
            }
        )
    )
    assert (custom.width, custom.height, custom.piece_size) == (200, 100, 30)

    bad_options: tuple[ConcurrentStableDict[str, object], ...] = (
        ConcurrentStableDict({"slider_width": "abc"}),
        ConcurrentStableDict({"slider_height": []}),
        ConcurrentStableDict({"slider_piece_size": 999}),
        ConcurrentStableDict({"slider_tolerance": -1}),
        ConcurrentStableDict({"slider_min_duration_ms": 999999}),
        ConcurrentStableDict({"slider_min_points": 0}),
        ConcurrentStableDict({"slider_width": True}),
    )
    for bad in bad_options:
        with pytest.raises(PluginError):
            CaptchaSliderOptions.from_options(bad)

    captcha = _captcha(redis_client, slider_width=200, slider_height=100, slider_piece_size=30)
    challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    assert Image.open(io.BytesIO(base64.b64decode(_payload(challenge)["background"]))).size == (200, 100)
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
async def test_slider_empty_duration_and_single_point(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """时长下限为 0 时单点轨迹按落点判通过（覆盖不校验时长分支）。"""
    captcha = _captcha(redis_client, slider_tolerance=3, slider_min_duration_ms=0, slider_min_points=1)
    challenge = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    gap_x = (await _record(redis_client, challenge.captcha_id))["gap_x"]

    within = CaptchaCredential(captcha_id=challenge.captcha_id, kind=CaptchaKind.SLIDER, trace=((gap_x + 3, 0, 0),))
    assert await captcha.verify_credential(within)

    other = await captcha.generate("login", kind=CaptchaKind.SLIDER)
    gap_x2 = (await _record(redis_client, other.captcha_id))["gap_x"]
    beyond = CaptchaCredential(captcha_id=other.captcha_id, kind=CaptchaKind.SLIDER, trace=((gap_x2 + 4, 0, 0),))
    assert not await captcha.verify_credential(beyond)
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
async def test_generate_sms_rejected(redis_client: fakeredis.aioredis.FakeRedis) -> None:
    """短信形态改走 `/captcha/sms`（`send_sms`），出题端点传 `kind=sms` 判参数错误（10001）。"""
    captcha = _captcha(redis_client)
    with pytest.raises(ParamError) as raised:
        await captcha.generate("login", kind=CaptchaKind.SMS)
    assert raised.value.code == 10001
    await captcha.aclose()


@pytest.mark.kiwi_id(2205)
def test_slider_factory_injects_options(monkeypatch: pytest.MonkeyPatch) -> None:
    """装配工厂：默认配置解析 DefaultCaptcha 并注入滑块选项；provider 空回落 NullCaptcha。"""
    factory = DefaultCaptchaFactory(
        Settings(
            captcha=PluginSelection(provider="default", options=ConcurrentStableDict({"slider_width": "200"})),
            config_source=PluginSelection(provider=""),
        )
    )
    assert isinstance(factory.create(), DefaultCaptcha)

    registry = PluginRegistry()
    registry.register("captcha", "default", lambda: DefaultCaptcha(url="redis://localhost:6379/0"))
    registry.register("captcha", "null", lambda: NullCaptcha())
    monkeypatch.setattr(plugin_module, "_DEFAULT_REGISTRY", registry)

    real = get_captcha(_request(Settings(captcha=PluginSelection(provider="default"))))
    assert isinstance(real, DefaultCaptcha)
    assert isinstance(real, BaseCaptcha)

    fallback = get_captcha(_request(Settings(captcha=PluginSelection(provider=""))))
    assert isinstance(fallback, NullCaptcha)


def _request(settings: Settings) -> Request:
    """构造最小请求替身（提供者只读 `app.state.settings`）。

    Args:
        settings: 应用配置。

    Returns:
        Request: 请求替身。
    """
    return cast("Request", SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings))))
