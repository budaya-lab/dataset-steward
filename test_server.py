"""Resource count coverage for the local viewer API."""
import json
import threading
from urllib.request import urlopen

import server
from test_validate import Base, GOOD


class ResourceCounts(Base):
    def test_detail_previews_counts_without_writing_metadata(self):
        resources = [{**r, "size": 999} for r in GOOD["resources"]]
        resources[1]["format"] = "dir"
        self.write({**GOOD, "resources": resources})
        before = (self.dir / "datapackage.json").read_text()
        detail = server.App(self.dir.parent).detail(self.dir.name)
        resources = detail["package"]["resources"]
        self.assertEqual([r["count"] for r in resources], [2, 2])
        self.assertTrue(all("size" not in r for r in resources))
        self.assertNotIn("format", resources[1])
        self.assertIn("<th>Count</th>", detail["readme_html"])
        self.assertEqual((self.dir / "datapackage.json").read_text(), before)
        self.assertFalse((self.dir / "README.md").exists())

    def test_save_recounts_and_migrates_legacy_metadata(self):
        app = server.App(self.dir.parent)
        detail = app.detail(self.dir.name)
        package = detail["package"]
        package["resources"][0].update(size=999, count=999)
        package["resources"][1]["format"] = "dir"
        saved = app.save(self.dir.name, {"package": package, "etag": detail["etag"]})
        self.assertTrue(saved["report"]["ok"])
        self.assertTrue(saved["report"]["counts_written"])
        resources = json.loads((self.dir / "datapackage.json").read_text())["resources"]
        self.assertEqual([r["count"] for r in resources], [2, 2])
        self.assertTrue(all("size" not in r for r in resources))
        self.assertNotIn("format", resources[1])
        self.assertTrue(saved["readme_current"])

    def test_http_detail_returns_counts_and_omits_directory_format(self):
        httpd = server.make_server(self.dir.parent, 0)
        self.addCleanup(httpd.server_close)
        httpd.RequestHandlerClass.app.revalidate()
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(thread.join)
        self.addCleanup(httpd.shutdown)
        port = httpd.server_address[1]
        with urlopen(f"http://127.0.0.1:{port}/api/datasets/{self.dir.name}", timeout=5) as response:
            detail = json.load(response)
        self.assertEqual(detail["package"]["resources"][1]["count"], 2)
        self.assertNotIn("format", detail["package"]["resources"][1])
        self.assertTrue(detail["report"]["ok"])
