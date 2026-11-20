import json
import unittest

from routing_agent import lookup_routes, review_rule, run_agent


class RoutingTests(unittest.TestCase):
    def test_lookup_and_wildcard(self):
        specific = lookup_routes("NAM", "DEMOUS33", 103, False)["matches"]
        self.assertEqual([row["line"] for row in specific], [12])
        self.assertEqual(specific[0]["artrules"][0]["line"], 7)
        wildcard = lookup_routes("NAM", "DEMOUS33", 103, True)["matches"]
        self.assertEqual([row["line"] for row in wildcard], [12, 14, 21])
        self.assertFalse(wildcard[-1]["catch_all"])
        self.assertEqual(wildcard[-1]["copy_routing_found"], "No")

    def test_copy_join_is_region_scoped(self):
        match, = lookup_routes("EMEA", "DEMOGB22", 103, False)["matches"]
        self.assertEqual(match["copy_routing_found"], "No")

    def test_duplicate_shadow_and_overlap(self):
        cases = [
            ("0202", None, "Duplicate"),
            ("0202", "DEMOUS44", "Shadow GCN"),
            ("0303", None, "Overlap Message Type"),
        ]
        for gcn, sender, expected in cases:
            with self.subTest(expected=expected):
                result = review_rule("NAM", "RR1", "DEMOUS33", 204, 204, gcn, sender)
                self.assertEqual(result["status"], "Blocked")
                self.assertEqual([(item["type"], item["line"]) for item in result["findings"]],
                                 [(expected, 13)])

    def test_catch_all_excluded_but_rrc_included(self):
        allowed = review_rule("NAM", "RR1", "DEMOUS33", 500, 500, "0101", None)
        self.assertEqual(allowed["status"], "Preview only")
        blocked = review_rule("NAM", "RR1RRC", "DEMOUS33", 500, 500, "0303", None)
        self.assertEqual(blocked["findings"][0]["line"], 21)

    def test_new_bic_preview_order(self):
        for rule_type, expected in [("RR1", [103, 100]), ("RR1RRC", [103]), ("RR3", [103])]:
            result = review_rule("NAM", rule_type, "DEMOUS55", 103, 103, "0101", None)
            self.assertEqual([row["first_mt"] for row in result["draft_rules"]], expected)

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            review_rule("NAM", "RR1", "DEMOUS33", 209, 200, "0202", None)

    def test_model_can_use_first_result_for_second_call(self):
        def reply(payload):
            outputs = [item for item in payload["input"] if item.get("type") == "function_call_output"]
            if len(outputs) == 2:
                finding = json.loads(outputs[1]["output"])["findings"][0]
                return {"status": "completed", "output": [{"type": "message", "content": [
                    {"type": "output_text", "text": f"{finding['type']} at FININROUT line {finding['line']}."}
                ]}]}
            if outputs:
                matched = json.loads(outputs[0]["output"])["matches"][0]
                name = "review_rule"
                arguments = {"region": "NAM", "rule_type": matched["rule_type"],
                             "bic": "DEMOUS33", "first_mt": 103, "last_mt": 103,
                             "gcn": matched["gcn"], "sender": None}
            else:
                name = "lookup_routes"
                arguments = {"region": "NAM", "bic": "DEMOUS33", "message_type": 103,
                             "include_wildcard": False}
            return {"status": "completed", "output": [{
                "type": "function_call", "name": name, "arguments": json.dumps(arguments),
                "call_id": str(len(outputs)),
            }]}

        answer, trace = run_agent("Find the MT103 rule and review recreating it.", reply)
        self.assertEqual([step["tool"] for step in trace], ["lookup_routes", "review_rule"])
        self.assertEqual(answer, "Duplicate at FININROUT line 12.")


if __name__ == "__main__":
    unittest.main()
