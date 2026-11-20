"""Run a real hosted LLM smoke test using the fictional routing files."""
import json
from routing_agent import run_agent

def main():
    metrics = []
    answer, trace = run_agent(
        "Find NAM MT103 for DEMOUS33 without wildcard. Then review recreating the exact specific RR1 rule using its destination GCN.",
        metrics=metrics,
    )
    print(answer)
    print(json.dumps({"trace": trace, "api": metrics}, indent=2))
    assert any(m.get("response_id") for m in metrics), "No API response identifier"
    assert any(t["tool"] == "lookup_routes" and t["result"].get("matches") for t in trace), "Lookup missing"
    assert any(t["tool"] == "review_rule" and t["result"].get("status") == "Blocked"
               and any(f["type"] == "Duplicate" and f["line"] == 12 for f in t["result"]["findings"])
               for t in trace), "Expected duplicate evidence missing"
    print("LIVE LLM SMOKE TEST PASSED")

if __name__ == "__main__":
    main()
