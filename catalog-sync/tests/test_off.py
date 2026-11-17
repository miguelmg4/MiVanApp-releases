import gzip
import io
import unittest

from sync.health import off
from sync.health.score import OffRow
from tests.util import load


def lines():
    return load("off_sample.csv").splitlines(keepends=True)


class OffTest(unittest.TestCase):
    def test_extract_only_wanted(self):
        rows = off.extract(lines(), {"8402001027109", "8410173001018"})
        self.assertEqual(set(rows), {"8402001027109", "8410173001018"})
        self.assertEqual(rows["8402001027109"],
                         OffRow("8402001027109", "e", 24, 4, ["en:e330", "en:e621"], ["en:no-gluten"]))

    def test_codes_match_ignoring_leading_zeros(self):
        rows = off.extract(lines(), {off.norm_code("8480000612380")})
        self.assertEqual(rows["8480000612380"].nutriscore_grade, "a")

    def test_empty_fields(self):
        row = off.extract(lines(), {"8410173001018"})["8410173001018"]
        self.assertEqual((row.nutriscore_grade, row.nutriscore_score, row.nova_group, row.additives_tags),
                         (None, None, None, []))
        self.assertEqual(row.labels_tags, ["en:organic", "en:eu-organic"])

    def test_download_extract_streams_gzip(self):
        payload = gzip.compress(load("off_sample.csv").encode("utf-8"))
        seen = {}

        def opener(request, timeout):
            seen["ua"] = request.get_header("User-agent")
            return io.BytesIO(payload)

        rows = off.download_extract({"3017620422003"}, opener=opener)
        self.assertEqual(rows["3017620422003"].additives_tags, ["en:e322"])
        self.assertEqual(seen["ua"], off.USER_AGENT)

    def test_row_json_roundtrip(self):
        row = OffRow("1", "b", 2, 3, ["en:e330"], [])
        self.assertEqual(off.row_from_json("1", off.row_to_json(row)), row)

    def test_norm_code(self):
        self.assertEqual(off.norm_code(" 0012345 "), "12345")
