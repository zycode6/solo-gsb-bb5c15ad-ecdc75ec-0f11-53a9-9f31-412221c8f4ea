"""HTTP 层集成测试：单步绑综修复建议接口。

直接运行：python3 tests/test_api.py
依赖 fastapi 与 httpx（已在 requirements.txt；httpx 为 TestClient 依赖）。
测试使用独立临时 SQLite，不影响默认 data/weave.db。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_tmp = tempfile.mkdtemp(prefix="weave-test-")
os.environ["DATABASE_PATH"] = os.path.join(_tmp, "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app import db  # noqa: E402
from app.main import app  # noqa: E402


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  ok: {msg}")


client = TestClient(app)
db.init_db()

TWILL = {
    "name": "2/2 twill",
    "cyclic": True,
    "max_float": 1,
    "threading": [0, 1, 2, 3],
    "tie_up": [[1, 1, 0, 0], [0, 1, 1, 0], [0, 0, 1, 1], [1, 0, 0, 1]],
    "treadling": [0, 1, 2, 3],
}

# 无违规设计：空建议用
CLEAN = {
    "name": "plain",
    "cyclic": False,
    "max_float": 2,
    "threading": [0, 1, 0, 1],
    "tie_up": [[1, 0], [0, 1]],
    "treadling": [0, 1, 0, 1],
}


def test_suggestions_happy_path():
    did = client.post("/designs", json=TWILL).json()["id"]
    r = client.post(f"/designs/{did}/tie-up-suggestions", params={"limit": 5})
    check(r.status_code == 200, f"status 200, got {r.status_code} {r.text}")
    data = r.json()
    check(len(data) == 5, "limit=5 returns 5 suggestions")
    expected_keys = {
        "treadle_index", "shaft_index", "new_value",
        "remaining_violations", "affected_interlacing_points",
    }
    check(all(set(x) == expected_keys for x in data),
          "each suggestion has exactly the 5 documented fields")
    check(all(x["remaining_violations"] == 7 for x in data),
          "remaining violations come from re-running the full audit")
    check(data[0] == {
        "treadle_index": 0, "shaft_index": 0, "new_value": 0,
        "remaining_violations": 7, "affected_interlacing_points": 1,
    }, "best suggestion is treadle 0 / shaft 0 -> 0")


def test_suggestions_sorting_and_limit_bounds():
    did = client.post("/designs", json=TWILL).json()["id"]
    # 不传 limit 时默认 50，返回全部 16 个候选
    r_default = client.post(f"/designs/{did}/tie-up-suggestions")
    check(r_default.status_code == 200 and len(r_default.json()) == 16,
          "missing limit defaults to 50 and returns all 16 candidates")
    # 边界 1 与 50
    check(client.post(f"/designs/{did}/tie-up-suggestions",
                      params={"limit": 1}).json()
          == [{"treadle_index": 0, "shaft_index": 0, "new_value": 0,
               "remaining_violations": 7, "affected_interlacing_points": 1}],
          "limit=1 yields single best row")
    r50 = client.post(f"/designs/{did}/tie-up-suggestions",
                      params={"limit": 50})
    check(r50.status_code == 200 and len(r50.json()) == 16,
          "limit=50 (upper bound) returns all 16 candidates")
    # 越界 0 与 51
    check(client.post(f"/designs/{did}/tie-up-suggestions",
                      params={"limit": 0}).status_code == 422,
          "limit=0 rejected with 422")
    check(client.post(f"/designs/{did}/tie-up-suggestions",
                      params={"limit": 51}).status_code == 422,
          "limit=51 rejected with 422")
    # 全量结果的排序：剩余数、点数、踏板、综框
    full = r50.json()
    keys = [(x["remaining_violations"], x["affected_interlacing_points"],
             x["treadle_index"], x["shaft_index"]) for x in full]
    check(keys == sorted(keys), "response is sorted by the documented 4 keys")


def test_suggestions_empty_list():
    did = client.post("/designs", json=CLEAN).json()["id"]
    r = client.post(f"/designs/{did}/tie-up-suggestions", params={"limit": 10})
    check(r.status_code == 200 and r.json() == [],
          "design without violations yields an empty suggestion list")


def test_suggestions_404():
    r = client.post("/designs/999999/tie-up-suggestions", params={"limit": 5})
    check(r.status_code == 404, f"unknown id -> 404, got {r.status_code}")
    check("999999" in r.json()["detail"], "404 detail mentions the id")


def test_original_design_not_modified():
    resp = client.post("/designs", json=TWILL).json()
    did = resp["id"]
    client.post(f"/designs/{did}/tie-up-suggestions", params={"limit": 50})
    again = client.get(f"/designs/{did}").json()
    check(again["tie_up"] == TWILL["tie_up"], "stored tie_up untouched")
    check(again["threading"] == TWILL["threading"]
          and again["treadling"] == TWILL["treadling"],
          "stored threading/treadling untouched")
    check(again["audit"]["violations"] == resp["audit"]["violations"]
          and len(resp["audit"]["violations"]) == 8,
          "stored audit untouched (still 8 violations)")
    check(again["cyclic"] is True and again["max_float"] == 1,
          "stored cyclic/max_float untouched")


if __name__ == "__main__":
    test_suggestions_happy_path()
    test_suggestions_sorting_and_limit_bounds()
    test_suggestions_empty_list()
    test_suggestions_404()
    test_original_design_not_modified()
    print("all api tests passed")
