import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import orchestrate_build as ob

def test_write_usage_creates_and_merges(tmp_path):
    p = tmp_path / "usage.json"
    ob.write_usage({"rateLimitType": "five_hour", "utilization": 0.99,
                    "resetsAt": 1000, "status": "allowed_warning"}, path=p)
    ob.write_usage({"rateLimitType": "seven_day", "utilization": 0.31,
                    "resetsAt": 2000, "status": "allowed"}, path=p)
    data = json.loads(p.read_text())
    assert data["windows"]["five_hour"]["utilization"] == 0.99
    assert data["windows"]["seven_day"]["resets_at"] == 2000

def test_write_usage_recovers_from_corrupt(tmp_path):
    p = tmp_path / "usage.json"; p.write_text("{oops")
    ob.write_usage({"rateLimitType": "five_hour", "utilization": 0.5}, path=p)
    assert json.loads(p.read_text())["windows"]["five_hour"]["utilization"] == 0.5

def test_record_segment(tmp_path):
    p = tmp_path / "history.jsonl"
    res = ob.SegmentResult(); res.num_turns = 3; res.billed_tokens = 500
    res.duration_s = 12.0; res.session_id = "abc"
    ob.record_segment("phase6 cp1", res, "ok", path=p)
    rec = json.loads(p.read_text().splitlines()[0])
    assert (rec["label"], rec["phase"], rec["kind"], rec["outcome"]) == ("phase6 cp1", 6, "build", "ok")
    assert rec["billed_tokens"] == 500 and rec["session_id"] == "abc"

def test_record_segment_kinds(tmp_path):
    p = tmp_path / "history.jsonl"; res = ob.SegmentResult()
    for label, kind in [("phase6 plan", "plan"), ("phase7 cp1 repair", "repair")]:
        ob.record_segment(label, res, "ok", path=p)
    kinds = [json.loads(l)["kind"] for l in p.read_text().splitlines()]
    assert kinds == ["plan", "repair"]
