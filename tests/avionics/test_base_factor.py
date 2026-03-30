from __future__ import annotations

import asyncio
from typing import Any

import pytest

from avionics import BaseFactor


class DummyFactor(BaseFactor):
    """
    BaseFactor の挙動検証用ダミー因子。

    データ取得ロジックは持たず、レベル遷移ロジックのみをテストする。
    定義書「4-2 OS構造」および各因子定義セクション参照。
    """

    async def update(self) -> None:  # type: ignore[override]
        """テスト用のダミー実装。外部データは使用しない。"""
        return None


def _run(coro: Any) -> Any:
    """簡易的にasync関数を同期テスト内で実行するユーティリティ。"""
    return asyncio.run(coro)


def test_dummy_factor_update_can_be_called() -> None:
    """DummyFactor.update() を呼んでも正常に完了する。"""
    dummy = DummyFactor(name="X", levels=[0, 1, 2])
    _run(dummy.update())


def test_downgrade_immediate() -> None:
    """
    downgradeが悪化方向のレベル遷移を即時適用することを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    assert factor.level == 0

    # 悪化方向（0→2）は即時に反映される想定
    factor.downgrade(2)
    assert factor.level == 2
    # 履歴にも記録されていること
    assert factor.history
    ts, lvl = factor.history[-1]
    assert lvl == 2
    assert ts is not None


def test_downgrade_error_invalid_level() -> None:
    """
    存在しないレベルや改善方向へのdowngrade呼び出しが例外になることを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 1

    with pytest.raises(ValueError):
        factor.downgrade(3)  # 定義外レベル

    with pytest.raises(ValueError):
        factor.downgrade(0)  # 現在値より小さい（改善方向）は禁止


def test_basefactor_init_missing_branch() -> None:
    """
    levelsが空リストの場合にBaseFactor.__init__がValueErrorを送出する分岐をカバーする。
    """
    with pytest.raises(ValueError):
        BaseFactor(name="X", levels=[])


def test_upgrade_delayed() -> None:
    """
    upgradeが継続確認なしでは反映されず、
    所定回数の確認後にのみレベルを変更することを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 2

    async def scenario() -> None:
        # 1回目：confirm_days=2 のため、まだ昇格しない
        applied = await factor.upgrade(new_level=0, confirm_days=2)
        assert applied is False
        assert factor.level == 2

        # 2回目：連続2回目の条件成立で昇格が確定
        applied = await factor.upgrade(new_level=0, confirm_days=2)
        assert applied is True
        assert factor.level == 0

    _run(scenario())


def test_upgrade_with_buffer_condition() -> None:
    """
    buffer_conditionにより昇格が抑制・許可されることを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 2

    async def scenario() -> None:
        async def buffer_false(_f: BaseFactor, _level: int) -> bool:
            return False

        async def buffer_true(_f: BaseFactor, _level: int) -> bool:
            return True

        # 確認日数を満たしても、バッファ条件がFalseなら昇格しない
        await factor.upgrade(new_level=0, confirm_days=1, buffer_condition=buffer_false)
        assert factor.level == 2

        # バッファ条件がTrueになった段階で昇格が適用される
        await factor.upgrade(new_level=0, confirm_days=1, buffer_condition=buffer_true)
        assert factor.level == 0

    _run(scenario())


def test_upgrade_reset_on_failure_condition() -> None:
    """
    condition_met=Falseの日が入ると連続カウンタがリセットされることを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 2

    async def scenario() -> None:
        # 1日目: 条件未達 → カウンタリセット
        applied = await factor.upgrade(new_level=0, confirm_days=2, condition_met=False)
        assert applied is False
        assert factor.level == 2

        # 2〜3日目: 連続2日条件を満たしてようやく昇格
        applied = await factor.upgrade(new_level=0, confirm_days=2, condition_met=True)
        assert applied is False
        assert factor.level == 2

        applied = await factor.upgrade(new_level=0, confirm_days=2, condition_met=True)
        assert applied is True
        assert factor.level == 0

    _run(scenario())


def test_upgrade_error_invalid_level_and_direction() -> None:
    """
    upgradeに無効なレベルや改善方向でないレベルを渡した場合に例外となることを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 1

    async def scenario() -> None:
        with pytest.raises(ValueError):
            await factor.upgrade(new_level=3, confirm_days=1)

        with pytest.raises(ValueError):
            # current=1 で1→2は改善方向ではない
            await factor.upgrade(new_level=2, confirm_days=1)

    _run(scenario())


def test_upgrade_invalid_confirm_days() -> None:
    """
    confirm_days<=0 の場合にBaseFactor.upgradeがValueErrorを送出する分岐をカバーする。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 1

    async def scenario() -> None:
        with pytest.raises(ValueError):
            await factor.upgrade(new_level=0, confirm_days=0)

    _run(scenario())


def test_upgrade_reset_on_buffer_failure() -> None:
    """
    buffer_conditionがFalseの日が入ると連続カウンタがリセットされることを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 2

    async def scenario() -> None:
        async def buffer_false(_f: BaseFactor, _level: int) -> bool:
            return False

        async def buffer_true(_f: BaseFactor, _level: int) -> bool:
            return True

        # 1日目: 条件・confirm_daysは満たすがバッファNG → 昇格せずリセット
        applied = await factor.upgrade(
            new_level=0,
            confirm_days=1,
            buffer_condition=buffer_false,
        )
        assert applied is False
        assert factor.level == 2

        # 2日目: バッファ条件も満たす → 昇格
        applied = await factor.upgrade(
            new_level=0,
            confirm_days=1,
            buffer_condition=buffer_true,
        )
        assert applied is True
        assert factor.level == 0

    _run(scenario())


def test_test_downgrade_helper() -> None:
    """
    BaseFactor.test_downgrade が降格ヘルパとして正常にTrueを返すことを確認する。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    assert factor.test_downgrade() is True


def test_test_downgrade_single_level_short_circuits() -> None:
    """
    レベルが1種類のみの場合、test_downgradeが即座にTrueを返すパスを確認する。
    """
    factor = DummyFactor(name="Y", levels=[0])
    assert factor.test_downgrade() is True


def test_basefactor_apply_signal_bundle_not_implemented() -> None:
    """
    BaseFactor.apply_signal_bundle が NotImplementedError を送出することを確認する。
    """
    base = BaseFactor(name="X", levels=[0, 1])

    async def scenario() -> None:
        with pytest.raises(NotImplementedError):
            await base.apply_signal_bundle(None, object(), altitude="mid")  # type: ignore[arg-type]

    _run(scenario())


def test_upgrade_with_sync_buffer_condition() -> None:
    """
    同期版buffer_conditionがAwaitable判定を通らない分岐もカバーする。
    """
    factor = DummyFactor(name="X", levels=[0, 1, 2])
    factor.level = 2

    def buffer_sync_false(_f: BaseFactor, _level: int) -> bool:
        return False

    def buffer_sync_true(_f: BaseFactor, _level: int) -> bool:
        return True

    async def scenario() -> None:
        # バッファNG → 昇格せずリセット
        applied = await factor.upgrade(
            new_level=0,
            confirm_days=1,
            buffer_condition=buffer_sync_false,
        )
        assert applied is False
        assert factor.level == 2

        # バッファOK → 昇格
        applied = await factor.upgrade(
            new_level=0,
            confirm_days=1,
            buffer_condition=buffer_sync_true,
        )
        assert applied is True
        assert factor.level == 0

    _run(scenario())

