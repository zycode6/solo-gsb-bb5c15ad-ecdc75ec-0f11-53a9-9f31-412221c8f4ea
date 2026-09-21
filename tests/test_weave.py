"""核心织纹逻辑的单元测试（不依赖 FastAPI）。"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.weave import (  # noqa: E402
    DesignError,
    audit_floats,
    build_interlacing,
    tie_up_suggestions,
    validate_design,
    _runs,
)


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


def test_interlacing():
    # 平纹：2 综 2 踏
    threading = [0, 1, 0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1, 0, 1]
    m = build_interlacing(threading, tie_up, treadling)
    check(m == [[1, 0, 1, 0],
                [0, 1, 0, 1],
                [1, 0, 1, 0],
                [0, 1, 0, 1]], "plain weave interlacing")


def test_warp_and_weft_floats():
    # 第 0 根经纱连续 3 纬浮起；第 0 纬纬纱连续浮过 3 根经纱
    threading = [0, 0, 0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 0, 1]
    # 矩阵:
    # 1 1 1
    # 1 1 1
    # 1 1 1
    # 0 0 0
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    warp = [x for x in v if x.direction == "warp"]
    weft = [x for x in v if x.direction == "weft"]
    check(len(warp) == 3 and all(x.length == 3 and x.start == 0 for x in warp),
          "warp floats of length 3 on all 3 ends")
    check(len(weft) == 1 and weft[0].yarn_index == 3 and weft[0].length == 3,
          "weft float of length 3 on pick 3")
    check(all(x.yarn_index in (0, 1, 2) for x in warp), "warp yarn indices")


def test_cyclic_merge():
    # 列: 1 1 0 0 1 1 -> 非循环两段(0,2),(4,2)；循环合并为 (4,4)
    check(_runs([1, 1, 0, 0, 1, 1], 1, False) == [(0, 2), (4, 2)],
          "non-cyclic runs")
    check(_runs([1, 1, 0, 0, 1, 1], 1, True) == [(4, 4)],
          "cyclic merge across boundary")
    # 全 1 列：只有一段，不自我合并
    check(_runs([1, 1, 1], 1, True) == [(0, 3)],
          "all-float line stays a single run")
    # 首尾不相接时不合并
    check(_runs([1, 0, 0, 1, 0], 1, True) == [(0, 1), (3, 1)],
          "no merge when boundary not both target")


def test_cyclic_audit_end_to_end():
    # 2/2 斜纹 4x4 循环，max_float=2：循环合并后每根经纱浮长恰为 2，不超限
    threading = [0, 1, 2, 3]
    tie_up = [[1, 1, 0, 0],
              [0, 1, 1, 0],
              [0, 0, 1, 1] if False else [0, 0, 1, 1],
              [1, 0, 0, 1]]
    treadling = [0, 1, 2, 3]
    _, v = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(v == [], "2/2 twill cyclic: no float exceeds 2")
    # 非循环时边界处浮长仍 <= 2，也不超限
    _, v2 = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v2 == [], "2/2 twill non-cyclic: no float exceeds 2")
    # max_float=1 时循环与非循环都应报出浮长 2
    _, v3 = audit_floats(threading, tie_up, treadling, max_float=1, cyclic=True)
    check(len(v3) > 0 and all(x.length == 2 for x in v3),
          "2/2 twill with max_float=1 flags length-2 floats")


def test_cyclic_wrap_violation():
    # 构造跨边界合并后才超限的情形：列 1 1 0 1 1，max_float=2
    # 非循环：两段长度 2、2，不超限；循环：合并为长度 4，超限
    threading = [0]
    tie_up = [[1], [0]]
    treadling = [0, 0, 1, 0, 0]
    _, v_off = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=False)
    check(v_off == [], "wrap-around float not flagged when cyclic=False")
    _, v_on = audit_floats(threading, tie_up, treadling, max_float=2, cyclic=True)
    check(len(v_on) == 1 and v_on[0].direction == "warp"
          and v_on[0].yarn_index == 0 and v_on[0].start == 3 and v_on[0].length == 4,
          "wrap-around float merged to length 4 starting at 3")


def test_validation():
    ok_cases = []
    # 维度不一致：绑综矩阵不是矩形
    try:
        validate_design([0], [[1, 0], [1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 穿综索引越界
    try:
        validate_design([0, 2], [[1, 0], [0, 1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 踏综索引越界
    try:
        validate_design([0], [[1], [0]], [2], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 绑综取值非 0/1
    try:
        validate_design([0], [[2]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 空输入
    try:
        validate_design([], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    # 负索引
    try:
        validate_design([-1], [[1]], [0], 2)
        ok_cases.append(False)
    except DesignError:
        ok_cases.append(True)
    check(all(ok_cases), "invalid designs are rejected")


def test_tie_up_suggestions_basic():
    # 2 踏 2 综；穿综 [0,0,1,1,1]、踏综 [0,0,0,1]、max_float=1：
    # 基线 6 条违规。仅 (0,0)->0（剩 4）与 (1,0)->1（剩 5）严格减少。
    threading = [0, 0, 1, 1, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 0, 0, 1]
    _, baseline = audit_floats(threading, tie_up, treadling, 1, False)
    check(len(baseline) == 6, "baseline has 6 violations")

    sugs = tie_up_suggestions(threading, tie_up, treadling, 1, False)
    check([(s.treadle_index, s.shaft_index) for s in sugs] == [(0, 0), (1, 0)],
          "only strictly-improving flips are returned, ordered by remaining")
    s0, s1 = sugs
    check(s0.new_value == 0 and s0.remaining_violations == 4,
          "flip tie_up[0][0] 1->0 leaves 4 violations")
    check(s1.new_value == 1 and s1.remaining_violations == 5,
          "flip tie_up[1][0] 0->1 leaves 5 violations")
    # 受影响交织点数 = 踩该踏板的纬纱数 × 穿该综框的经纱数
    check(s0.affected_interlacing_points == 3 * 2,
          "affected points = pick_count * end_count (3 picks * 2 ends)")
    check(s1.affected_interlacing_points == 1 * 2,
          "affected points for treadle 1 / shaft 0 (1 pick * 2 ends)")


def test_tie_up_suggestions_sorting_and_limit():
    # 2/2 斜纹 max_float=1、cyclic：基线 8 条违规；任一单元翻转都剩 7 条，
    # 受影响点数恒为 1，应按 (踏板, 综框) 行优先次序稳定输出全部 16 个候选。
    threading = [0, 1, 2, 3]
    tie_up = [[1, 1, 0, 0],
              [0, 1, 1, 0],
              [0, 0, 1, 1],
              [1, 0, 0, 1]]
    treadling = [0, 1, 2, 3]
    all_sugs = tie_up_suggestions(threading, tie_up, treadling, 1, True)
    check(len(all_sugs) == 16, "all 16 single flips reduce 8 violations to 7")
    check(
        [(s.treadle_index, s.shaft_index) for s in all_sugs]
        == [(t, s) for t in range(4) for s in range(4)],
        "ties broken by treadle then shaft index (row-major)",
    )
    check(all(s.remaining_violations == 7 for s in all_sugs),
          "every candidate leaves exactly 7 violations")
    check(all(s.new_value == 1 - tie_up[s.treadle_index][s.shaft_index]
              for s in all_sugs),
          "new_value is the bitwise flip of the original cell")
    limited = tie_up_suggestions(threading, tie_up, treadling, 1, True, limit=3)
    check(len(limited) == 3
          and [(s.treadle_index, s.shaft_index) for s in limited]
          == [(0, 0), (0, 1), (0, 2)],
          "limit keeps the first 3 after sorting")
    limit_one = tie_up_suggestions(threading, tie_up, treadling, 1, True, limit=1)
    check(len(limit_one) == 1 and limit_one[0].treadle_index == 0
          and limit_one[0].shaft_index == 0,
          "limit=1 returns the single best candidate")


def test_tie_up_suggestions_affected_points_tie_break():
    # 相同剩余违规数时，受影响点数少的优先；点数相同再按踏板、综框排序。
    threading = [0, 1, 1]
    tie_up = [[1, 0], [1, 1], [1, 0]]
    treadling = [2, 0, 2]
    sugs = tie_up_suggestions(threading, tie_up, treadling, 1, False)
    check(
        [(s.treadle_index, s.shaft_index, s.remaining_violations,
          s.affected_interlacing_points) for s in sugs]
        == [
            (2, 1, 2, 4),  # 剩余 2，最优
            (0, 0, 3, 1),  # 剩余 3：点数 1
            (0, 1, 3, 2),  # 剩余 3：点数 2，踏板 0
            (2, 0, 3, 2),  # 剩余 3：点数 2，踏板 2
        ],
        "sorted by remaining, affected points, treadle, shaft",
    )


def test_tie_up_suggestions_empty_and_immutable():
    # 平纹 max_float=1 本身无违规：没有任何翻转能严格减少，返回空列表
    threading = [0, 1]
    tie_up = [[1, 0], [0, 1]]
    treadling = [0, 1]
    check(tie_up_suggestions(threading, tie_up, treadling, 1, False) == [],
          "no suggestions for a clean design")

    # 有违规但任何单步翻转都不改善时同样返回空
    threading2 = [0, 1, 0, 1]
    tie_up2 = [[1, 0], [0, 1]]
    treadling2 = [0, 0, 1, 1]
    _, baseline2 = audit_floats(threading2, tie_up2, treadling2, 1, False)
    check(len(baseline2) == 4, "baseline with 4 violations but no single-step cure")
    check(tie_up_suggestions(threading2, tie_up2, treadling2, 1, False) == [],
          "empty list when no single flip reduces violations")

    # 不得修改原 tie_up
    before = [row[:] for row in tie_up2]
    tie_up_suggestions(threading2, tie_up2, treadling2, 1, False)
    check(tie_up2 == before, "original tie_up is not mutated")


if __name__ == "__main__":
    test_interlacing()
    test_warp_and_weft_floats()
    test_cyclic_merge()
    test_cyclic_audit_end_to_end()
    test_cyclic_wrap_violation()
    test_validation()
    test_tie_up_suggestions_basic()
    test_tie_up_suggestions_sorting_and_limit()
    test_tie_up_suggestions_affected_points_tie_break()
    test_tie_up_suggestions_empty_and_immutable()
    print("all tests passed")
