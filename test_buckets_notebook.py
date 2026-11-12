"""Run the notebook's export example with synthetic data only."""
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

import validate


class NotebookExport(unittest.TestCase):
    def test_export_has_labels_and_counts_without_an_index(self):
        notebook = json.loads((validate.HERE / "buckets.ipynb").read_text())
        exports = [
            "".join(cell["source"])
            for cell in notebook["cells"]
            if cell["cell_type"] == "code" and "to_csv(" in "".join(cell["source"])
        ]
        self.assertEqual(len(exports), 1)
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exec(compile(exports[0], "buckets.ipynb export", "exec"), {
                    "DATASET": folder,
                    "buckets": pd.DataFrame({"year": ["001", "1956"], "count": [0, 201]}),
                })
            csv = output.getvalue().strip()
            self.assertEqual(csv, "year,count\n001,0\n1956,201")
            path = folder / "buckets.csv"
            path.write_text(csv)
            buckets = validate.read_buckets(path)
            self.assertEqual(buckets["errors"], [])
            self.assertEqual(buckets["rows"], [["001", "0"], ["1956", "201"]])
