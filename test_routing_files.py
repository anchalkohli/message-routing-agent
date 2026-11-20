from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from routing_agent import ARTRULES, FININROUT, search_routes
from routing_files import draft_csv, load_routing_files, message_intervals, read_local_files, review_batch

SAMPLES = Path(__file__).with_name("samples")


class RoutingFileTests(unittest.TestCase):
    def setUp(self):
        self.routes, self.copies = read_local_files(SAMPLES)
        self.dataset = load_routing_files(self.routes, self.copies)

    def test_fixtures_match_agent_evidence(self):
        self.assertEqual(self.dataset.rules, FININROUT)
        self.assertEqual({key: tuple(items) for key, items in self.dataset.copies.items()}, ARTRULES)
        self.assertIn("NAM,RR1,DEMOUS33,103,0101", self.dataset.route_source[12])

    def test_local_directory_with_optional_copy_file(self):
        with TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "fininrout.csv"):
                read_local_files(directory)
            shutil.copyfile(SAMPLES / "fininrout.csv", Path(directory) / "fininrout.csv")
            routes, copies = read_local_files(directory)
            self.assertEqual(routes, self.routes)
            self.assertIsNone(copies)
            dataset = load_routing_files(routes)
            match, = search_routes("NAM", "DEMOUS33", ((103, 103),), False,
                                   rules=dataset.rules, copy_rules=dataset.copies)["matches"]
            self.assertEqual(match["copy_routing_found"], "Unavailable")

    def test_range_filters_and_wildcard(self):
        intervals = message_intervals("MT103, 203-204, 211:220")
        rows = search_routes("NAM", "DEMOUS33", intervals, True,
                             rules=self.dataset.rules, copy_rules=self.dataset.copies)["matches"]
        self.assertEqual([row["line"] for row in rows], [12, 13, 14, 21])
        self.assertEqual([row["copy_routing_found"] for row in rows], ["Yes", "No", "Yes", "No"])

    def test_bad_csv_reports_physical_line(self):
        malformed = self.routes.replace(b"DEMOUS33", b"invalid", 1)
        with self.assertRaisesRegex(ValueError, "FININROUT line 12"):
            load_routing_files(malformed)

    def test_multiline_csv_preserves_next_record_line(self):
        routes = (b"region,rule_type,bic,message_type,gcn,sender,action\r\n"
                  b'NAM,RR1,DEMOUS33,"103\r\n",0101,,rtecode\r\n'
                  b"NAM,RR1,DEMOUS33,105,0202,,rtecode\r\n")
        dataset = load_routing_files(routes)
        self.assertEqual([rule.line for rule in dataset.rules], [2, 4])
        self.assertIn("\r\n", dataset.route_source[2])

    def test_batch_blocks_entire_draft_if_any_rule_conflicts(self):
        result = review_batch("NAM", "RR1", "DEMOUS33", "500,204", "0202",
                              None, self.dataset.rules)
        self.assertEqual(result["status"], "Blocked")
        self.assertEqual(result["findings"][0]["line"], 13)
        self.assertNotIn("draft_rules", result)

    def test_new_bic_batch_generates_one_catch_all(self):
        result = review_batch("NAM", "RR1", "DEMOUS55", "103,105", "0101",
                              None, self.dataset.rules)
        drafts = result["draft_rules"]
        self.assertEqual([rule["first_mt"] for rule in drafts], [103, 105, 100])
        self.assertIn("100 TO 999,0101", draft_csv(drafts))


if __name__ == "__main__":
    unittest.main()
