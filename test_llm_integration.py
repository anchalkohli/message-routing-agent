import json
import unittest
from unittest.mock import patch
from routing_agent import Rule, run_agent
from routing_files import RoutingFiles

class FileBackedAgentTests(unittest.TestCase):
    def test_agent_uses_loaded_dataset_and_exposes_telemetry(self):
        fixture = RoutingFiles((Rule(99, "NAM", "RR1", "TESTUS33", 103, 103, "1234"),),
                               {("NAM", "1234"): [{"line": 8, "copy_gcn": "5678"}]}, {}, {})
        def respond(payload):
            outputs = [x for x in payload["input"] if x.get("type") == "function_call_output"]
            if outputs:
                match = json.loads(outputs[0]["output"])["matches"][0]
                self.assertEqual(match["line"], 99)
                self.assertEqual(match["artrules"][0]["copy_gcn"], "5678")
                result = [{"type": "message", "content": [{"type": "output_text", "text": "Found"}]}]
            else:
                result = [{"type": "function_call", "name": "lookup_routes", "call_id": "c1",
                           "arguments": json.dumps({"region": "NAM", "bic": "TESTUS33",
                                                    "message_type": 103, "include_wildcard": False})}]
            return {"status": "completed", "output": result, "id": "mock", "model": "mock",
                    "usage": {"total_tokens": 10}}
        metrics = []
        with patch("routing_files.load_routing_files", return_value=fixture):
            answer, trace = run_agent("Look up MT103", respond, metrics=metrics)
        self.assertEqual(answer, "Found")
        self.assertEqual(trace[0]["arguments"]["bic"], "TESTUS33")
        self.assertEqual(len(metrics), 2)
        self.assertEqual(sum(x["usage"]["total_tokens"] for x in metrics), 20)
