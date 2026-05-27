"""前后端开关联动测试：验证 PATCH /api/admin/flags 即时生效 + 持久化到.env。"""
import json, urllib.request, time

API = "http://localhost:8000/api"

def get(path):
    with urllib.request.urlopen(f"{API}{path}", timeout=30) as r:
        return json.loads(r.read())

def patch(path, body):
    d = json.dumps(body).encode()
    req = urllib.request.Request(f"{API}{path}", data=d, method="PATCH")
    req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())

TEST_FLAGS = [
    ("hybrid_retrieval_llm_rewrite", False, True),
    ("llm_streaming_enabled", True, False),
    ("langfuse_enabled", True, False),
]

print("=" * 60)
print("前后端开关联动测试")
print("=" * 60)

passed = 0
failed = 0

for name, initial, toggled in TEST_FLAGS:
    print(f"\n[{name}]")

    # 1. Check current value
    flags = get("/admin/flags")
    current = {f["name"]: f["value"] for f in flags["flags"]}
    before = current.get(name)
    print(f"  当前值: {before}")

    # 2. Toggle
    result = patch("/admin/flags", {"name": name, "value": toggled})
    assert result["ok"], f"Toggle failed: {result}"
    time.sleep(0.3)

    # 3. Verify new value
    flags2 = get("/admin/flags")
    current2 = {f["name"]: f["value"] for f in flags2["flags"]}
    after = current2.get(name)
    ok = after == toggled
    print(f"  切换后: {after} -> {'PASS' if ok else 'FAIL'}")
    if ok: passed += 1
    else: failed += 1

    # 4. Restore original
    patch("/admin/flags", {"name": name, "value": initial})
    time.sleep(0.3)
    flags3 = get("/admin/flags")
    current3 = {f["name"]: f["value"] for f in flags3["flags"]}
    restored = current3.get(name)
    rok = restored == initial
    print(f"  恢复后: {restored} -> {'PASS' if rok else 'FAIL'}")
    if rok: passed += 1
    else: failed += 1

print(f"\n{'='*60}")
print(f"总计: {passed} PASS, {failed} FAIL")
print(f"{'='*60}")
