"""Run with: python -m unittest test_validate  (from inside _describe/)"""
import json
import tempfile
import unittest
from pathlib import Path

import validate

GOOD = {
    "name": "ds-sample",
    "title": "Sample",
    "description": "A sample dataset.",
    "keywords": ["task:layout", "project:Jawi", "stage:curated"],
    "created": "2026-10-26T00:00:00Z",
    "contributors": [{"title": "A Person", "roles": ["creator"]}],
    "sources": [{"title": "Elsewhere", "path": "https://example.org/not-checked"}],
    "resources": [
        {"name": "input", "path": "input.csv", "format": "csv", "title": "Manifest"},
        {"name": "xml", "path": "xml/", "format": "dir", "title": "Annotations"},
    ],
}
BUCKETS = ",class,regions\n0,text,\"12,342\"\n1,image,736\n"


class Base(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name) / "ds-sample"
        self.dir.mkdir()
        (self.dir / "input.csv").write_text("id,url\n1,a\n2,b\n")
        (self.dir / "xml").mkdir()
        (self.dir / "xml" / "a.xml").write_text("<a/>")
        (self.dir / "xml" / "b.xml").write_text("<a/>")
        (self.dir / "buckets.csv").write_text(BUCKETS)
        self.write(GOOD)

    def write(self, package):
        (self.dir / "datapackage.json").write_text(json.dumps(package))

    def changed(self, **changes):
        package = {**GOOD, **changes}
        self.write(package)
        return validate.validate_folder(self.dir)

    def without(self, key):
        package = {k: v for k, v in GOOD.items() if k != key}
        self.write(package)
        return validate.validate_folder(self.dir)


class Metadata(Base):
    def test_good_package_passes_with_no_warnings(self):
        report = validate.validate_folder(self.dir)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_required_fields(self):
        for key in ("name", "title", "description", "created", "contributors", "keywords"):
            self.assertFalse(self.without(key).ok, key)

    def test_keywords(self):
        self.assertFalse(self.changed(keywords=["task:layout", "stage:curated"]).ok)
        self.assertFalse(self.changed(keywords=["task:layout", "project:Jawi", "stage:final"]).ok)
        self.assertFalse(self.changed(keywords=["task:", "project:Jawi", "stage:curated"]).ok)
        self.assertFalse(self.changed(keywords=["task:a", "task:b", "project:Jawi", "stage:curated"]).ok)
        for stage in ("master", "curated", "annotated", "ground-truth"):
            self.assertTrue(self.changed(keywords=["task:x", "project:y", f"stage:{stage}"]).ok, stage)

    def test_other_keywords_are_errors(self):
        report = self.changed(keywords=["task:layout", "project:Jawi", "stage:curated", "Utusan Melayu"])
        self.assertEqual(len(report.errors), 1)
        self.assertIn("Utusan Melayu", report.errors[0])

    def test_created_format(self):
        for bad in ("2026-10-26", "2026-13-01T00:00:00Z", "2026-10-26T00:00:00+08:00", 20261026):
            self.assertFalse(self.changed(created=bad).ok, bad)

    def test_source_paths_are_never_looked_up(self):
        sources = [{"title": "Gone", "path": "../ds-does-not-exist"}, {"title": "Other", "path": "nowhere/at/all"}]
        report = self.changed(sources=sources)
        self.assertEqual(report.errors, [])
        self.assertEqual(report.warnings, [])

    def test_source_needs_only_a_title(self):
        self.assertTrue(self.changed(sources=[{"title": "No path"}]).ok)
        self.assertFalse(self.changed(sources=[{"path": "no-title"}]).ok)

    def test_sources_are_optional(self):
        self.assertTrue(self.without("sources").ok)
        self.assertTrue(self.changed(sources=[]).ok)
        self.assertFalse(self.changed(sources="not a list").ok)


class Resources(Base):
    def test_undescribed_root_items_fail(self):
        (self.dir / "extra").mkdir()
        (self.dir / "extra" / "x").write_text("x")
        report = validate.validate_folder(self.dir)
        self.assertEqual(report.undescribed, ["extra"])
        self.assertFalse(report.ok)

    def test_subitems_need_no_description(self):
        (self.dir / "xml" / "nested").mkdir()
        self.assertTrue(validate.validate_folder(self.dir).ok)

    def test_template_and_ignored_items_are_skipped(self):
        for name in ("AGENTS.md", "stage.config.json", "input.backup-20261105.csv", "scripts", "dropped-20261105"):
            (self.dir / name).mkdir() if "." not in name or name == "scripts" else (self.dir / name).write_text("")
        self.assertEqual(validate.validate_folder(self.dir).undescribed, [])

    def test_resource_needs_title(self):
        resources = [{"name": "input", "path": "input.csv"}, GOOD["resources"][1]]
        self.assertFalse(self.changed(resources=resources).ok)

    def test_missing_and_unsafe_paths_fail(self):
        for path in ("gone.csv", "../outside", "/etc/passwd", "https://example.org/x"):
            resources = GOOD["resources"] + [{"name": "bad", "path": path, "title": "Bad"}]
            self.assertFalse(self.changed(resources=resources).ok, path)

    def test_stubs(self):
        (self.dir / "My Folder").mkdir()
        (self.dir / "notes.TXT").write_text("x")
        report = validate.validate_folder(self.dir)
        stubs = validate.stub_resources(self.dir, report.undescribed, GOOD)
        self.assertEqual(
            stubs,
            [
                {"name": "my-folder", "path": "My Folder/", "format": "dir", "title": ""},
                {"name": "notes", "path": "notes.TXT", "format": "txt", "title": ""},
            ],
        )


class Buckets(Base):
    def read(self, text):
        path = self.dir / "buckets.csv"
        path.write_text(text)
        return validate.read_buckets(path)

    def test_missing(self):
        (self.dir / "buckets.csv").unlink()
        self.assertFalse(validate.validate_folder(self.dir).ok)

    def test_no_index_fails(self):
        self.assertTrue(self.read("year,count\n1956,201\n")["errors"])

    def test_any_columns_with_index_pass(self):
        for text in (",year,count\n0,1956,201\n", ",class,regions\n0,text,\"12,342\"\n", ",metric,percent\n0,a,7.6\n"):
            self.assertEqual(self.read(text)["errors"], [], text)

    def test_duplicate_index_fails(self):
        self.assertTrue(self.read(",year,count\n0,1956,1\n0,1957,2\n")["errors"])

    def test_empty_fails(self):
        self.assertTrue(self.read(",year,count\n")["errors"])

    def test_chart_uses_first_column_as_label_even_if_numeric(self):
        charts = validate.bucket_charts(self.read(",year,count\n0,1956,201\n"))
        self.assertEqual(len(charts), 1)
        self.assertEqual(charts[0]["column"], "count")
        self.assertEqual(charts[0]["points"][0], {"label": "1956", "value": 201.0, "display": "201"})

    def test_thousands_are_parsed(self):
        self.assertEqual(validate.bucket_charts(self.read(BUCKETS))[0]["points"][0]["value"], 12342.0)

    def test_several_value_columns_give_several_charts(self):
        self.assertEqual(len(validate.bucket_charts(self.read(",k,a,b\n0,x,1,2\n"))), 2)

    def test_text_only_warns(self):
        buckets = self.read(",k,v\n0,x,y\n")
        self.assertEqual(buckets["errors"], [])
        self.assertTrue(buckets["warnings"])


class Warnings(Base):
    def test_name_mismatch(self):
        self.assertTrue(self.changed(name="other").warnings)

    def test_empty_folder_warns_without_failing(self):
        (self.dir / "xml" / "a.xml").unlink()
        (self.dir / "xml" / "b.xml").unlink()
        (self.dir / "xml" / ".DS_Store").write_text("")
        report = validate.validate_folder(self.dir)
        self.assertTrue(report.ok)
        self.assertEqual(report.warnings, ["folder is empty: xml/"])

    def test_suffix_must_match_stage(self):
        for folder, stage, passes in (
            ("ds-sample-atd", "annotated", True),
            ("ds-sample-atd", "curated", False),
            ("ds-sample-gt", "ground-truth", True),
            ("ds-sample-gt", "annotated", False),
        ):
            target = self.dir.parent / folder
            self.dir = self.dir.rename(target)
            self.write({**GOOD, "name": folder, "keywords": ["task:x", "project:y", f"stage:{stage}"]})
            self.assertEqual(validate.validate_folder(self.dir).ok, passes, (folder, stage))

    def test_warnings_do_not_fail(self):
        self.assertTrue(self.changed(name="other").ok)


class Sizes(Base):
    def saved_sizes(self):
        package = json.loads((self.dir / "datapackage.json").read_text())
        return {r["name"]: r.get("size") for r in package["resources"]}

    def add(self, name, path, content=None):
        if content is not None:
            (self.dir / path).write_text(content)
        return {"name": name, "path": path, "title": name}

    def test_csv_rows_and_files_in_folder(self):
        report = validate.process_folder(self.dir)
        self.assertTrue(report.sizes_written)
        self.assertEqual(self.saved_sizes(), {"input": 2, "xml": 2})

    def test_quoted_newline_is_one_row(self):
        (self.dir / "input.csv").write_text('id,text\n1,"two\nlines"\n')
        validate.process_folder(self.dir)
        self.assertEqual(self.saved_sizes()["input"], 1)

    def test_json_counts_top_level_items(self):
        resources = GOOD["resources"] + [self.add("a", "a.json", "[1, 2, 3]"), self.add("b", "b.json", '{"x": {"y": 1}}')]
        self.write({**GOOD, "resources": resources})
        validate.process_folder(self.dir)
        self.assertEqual(self.saved_sizes()["a"], 3)
        self.assertEqual(self.saved_sizes()["b"], 1)

    def test_folder_counts_nested_but_not_hidden_files(self):
        (self.dir / "xml" / "deep").mkdir()
        (self.dir / "xml" / "deep" / "c.xml").write_text("<a/>")
        (self.dir / "xml" / ".DS_Store").write_text("")
        (self.dir / "xml" / ".hidden").mkdir()
        (self.dir / "xml" / ".hidden" / "d.xml").write_text("<a/>")
        validate.process_folder(self.dir)
        self.assertEqual(self.saved_sizes()["xml"], 3)

    def test_other_types_have_no_size(self):
        names = ("a.py", "a.ipynb", "a.md", "a.yaml", "a.toml")
        added = [{**self.add(n, n, "{}"), "size": 99} for n in names]
        self.write({**GOOD, "resources": GOOD["resources"] + added})
        validate.process_folder(self.dir)
        self.assertTrue(all(self.saved_sizes()[n] is None for n in names))

    def test_stale_size_is_recounted(self):
        resources = [{**GOOD["resources"][0], "size": 999}, GOOD["resources"][1]]
        self.write({**GOOD, "resources": resources})
        validate.process_folder(self.dir)
        self.assertEqual(self.saved_sizes()["input"], 2)

    def test_unchanged_sizes_are_not_rewritten(self):
        validate.process_folder(self.dir)
        self.assertFalse(validate.process_folder(self.dir).sizes_written)

    def test_check_mode_writes_nothing(self):
        before = (self.dir / "datapackage.json").read_text()
        validate.process_folder(self.dir, write=False)
        self.assertEqual((self.dir / "datapackage.json").read_text(), before)

    def test_sizes_are_saved_even_when_dataset_fails(self):
        self.write({**GOOD, "title": ""})
        self.assertFalse(validate.process_folder(self.dir).ok)
        self.assertEqual(self.saved_sizes()["input"], 2)

    def test_unreadable_json_is_an_error(self):
        resources = GOOD["resources"] + [self.add("bad", "bad.json", "{oops")]
        self.assertFalse(self.changed(resources=resources).ok)

    def test_readme_shows_sizes(self):
        validate.process_folder(self.dir)
        text = (self.dir / "README.md").read_text()
        self.assertIn("| Manifest | input.csv | csv | 2 rows |", text)
        self.assertIn("| Annotations | xml/ | dir | 2 files |", text)


class Readme(Base):
    def readme(self):
        return (self.dir / "README.md").read_text()

    def test_failing_dataset_keeps_its_readme(self):
        (self.dir / "README.md").write_text("mine")
        self.write({**GOOD, "title": ""})
        self.assertFalse(validate.process_folder(self.dir).readme_written)
        self.assertEqual(self.readme(), "mine")

    def test_check_mode_never_writes(self):
        self.assertFalse(validate.process_folder(self.dir, write=False).readme_written)
        self.assertFalse((self.dir / "README.md").exists())

    def test_generated_content(self):
        self.assertTrue(validate.process_folder(self.dir).readme_written)
        text = self.readme()
        for expected in ("# Sample", "badge/stage-curated-purple", "| A Person | creator |", "Elsewhere", "12,342", validate.NOTES_MARKER):
            self.assertIn(expected, text)
        self.assertNotIn("| 0 |", text)  # the bucket index isn't displayed

    def test_no_sources_section_without_sources(self):
        self.write({k: v for k, v in GOOD.items() if k != "sources"})
        validate.process_folder(self.dir)
        self.assertNotIn("## Sources", self.readme())

    def test_handwritten_readme_moves_below_marker(self):
        (self.dir / "README.md").write_text("# Mine\n\nHand-written.\n")
        validate.process_folder(self.dir)
        self.assertEqual(self.readme().split(validate.NOTES_MARKER)[1].strip(), "# Mine\n\nHand-written.")

    def test_notes_survive_regeneration(self):
        validate.process_folder(self.dir)
        (self.dir / "README.md").write_text(self.readme() + "\nMy note.\n")
        self.write({**GOOD, "title": "Changed"})
        validate.process_folder(self.dir)
        self.assertIn("# Changed", self.readme())
        self.assertIn("My note.", self.readme())

    def test_template_boilerplate_is_dropped(self):
        (self.dir / "README.md").write_text("# Dataset repository template\n\nUse this.\n")
        validate.process_folder(self.dir)
        self.assertNotIn("Use this.", self.readme())

    def test_rerun_does_not_rewrite(self):
        self.assertTrue(validate.process_folder(self.dir).readme_written)
        self.assertFalse(validate.process_folder(self.dir).readme_written)

    def test_pipes_in_values_stay_in_their_cell(self):
        self.write({**GOOD, "description": "a|b\nc"})
        validate.process_folder(self.dir)
        self.assertIn("a\\|b c", self.readme())


if __name__ == "__main__":
    unittest.main()
