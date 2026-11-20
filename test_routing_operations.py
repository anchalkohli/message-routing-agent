from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from routing_files import review_batch
from routing_operations import init_audit, load_release, log_review, publish_release

SAMPLES = Path(__file__).with_name("samples")


class ProductionTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.active = self.root / "current"
        self.audit = self.root / "reviews.sqlite3"

    def test_publish_switches_release_and_rejects_invalid_replacement(self):
        old_revision = publish_release(SAMPLES, self.root)
        old_release = self.active.resolve()
        source = shutil.copytree(SAMPLES, self.root / "incoming")
        routes = source / "fininrout.csv"
        routes.write_bytes(routes.read_bytes().replace(b",0101,", b",0102,"))
        new_revision = publish_release(source, self.root)
        self.assertNotEqual(old_revision, new_revision)
        self.assertTrue(old_release.is_dir())
        self.assertEqual(load_release(self.active)[1], new_revision)
        routes.write_text("invalid", encoding="utf-8")
        with self.assertRaises(ValueError):
            publish_release(source, self.root)
        self.assertEqual(load_release(self.active)[1], new_revision)

    def test_manifest_rejects_modified_file_and_supports_missing_copy_file(self):
        source = shutil.copytree(SAMPLES, self.root / "incoming")
        (source / "artrules.csv").unlink()
        publish_release(source, self.root)
        self.assertIsNone(load_release(self.active)[0].copies)
        (self.active / "fininrout.csv").write_text("corrupted", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "checksums"):
            load_release(self.active)

    def test_concurrent_reviews_log_unique_records_and_reject_missing_reference(self):
        revision = publish_release(SAMPLES, self.root)
        dataset, _ = load_release(self.active)
        proposal = dict(region="NAM", kind="RR1", bic="DEMOUS33", message_types="204",
                        gcn="0202", sender=None)
        outcome = review_batch(**proposal, rules=dataset.rules)
        init_audit(self.audit)

        def submit(index):
            return log_review(self.audit, revision, f"BRD-{index}", "Reviewed", proposal, outcome)

        with ThreadPoolExecutor(max_workers=4) as workers:
            ids = list(workers.map(submit, range(12)))
        with self.assertRaisesRegex(ValueError, "change reference"):
            log_review(self.audit, revision, "", "Reviewed", proposal, outcome)
        with sqlite3.connect(self.audit) as connection:
            records = connection.execute(
                "SELECT review_id, dataset_revision, outcome FROM rule_reviews"
            ).fetchall()
        self.assertEqual(set(records), {(item, revision, "Blocked") for item in ids})


if __name__ == "__main__":
    unittest.main()
