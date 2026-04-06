import os
import json
import threading
import time
import importlib
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure src is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import server


def make_bookmarks_json(bookmarks=None):
    return {
        "checksum": "",
        "roots": {
            "bookmark_bar": {
                "children": bookmarks or [],
                "name": "Bookmarks bar",
                "type": "folder"
            },
            "other": {"children": [], "name": "Other", "type": "folder"},
            "synced": {"children": [], "name": "Mobile bookmarks", "type": "folder"}
        },
        "version": 1
    }


class TestServer(unittest.TestCase):
    def make_tmp_bookmarks(self, tmpdir):
        p = Path(tmpdir) / "Bookmarks"
        data = make_bookmarks_json([
            {"type": "folder", "name": "Dev", "children": [
                {"type": "url", "name": "MySite", "url": "https://example.com", "date_added": "1"},
                {"type": "url", "name": "Search", "url": "https://search.example?q=python", "date_added": "2"}
            ]},
            {"type": "folder", "name": "中文目录", "children": [
                {"type": "url", "name": "站点😊", "url": "https://例子.测试", "date_added": "3"}
            ]}
        ])
        p.write_text(json.dumps(data, ensure_ascii=False))
        return str(p)

    def test_load_bookmarks_normal(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_tmp_bookmarks(td)
            data = server.load_bookmarks(path)
            self.assertIsNotNone(data)
            self.assertIn("roots", data)

    def test_load_bookmarks_corrupted(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "BadBookmarks"
            p.write_text("{ not valid json")
            self.assertIsNone(server.load_bookmarks(str(p)))

    def test_load_bookmarks_empty(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Empty"
            p.write_text("")
            self.assertIsNone(server.load_bookmarks(str(p)))

    def test_auto_detect_path(self):
        # Skip on non-Windows since %LOCALAPPDATA% won't expand
        import platform
        if platform.system() != "Windows":
            self.skipTest("Auto-detect candidates are Windows paths; skipping on " + platform.system())
        import subprocess
        result = subprocess.run(
            ["python3", "-c", "import sys; sys.path.insert(0,'src'); import server; print(server.BOOKMARKS_PATH)"],
            capture_output=True, text=True, cwd="/home/ezio/edge-bookmarks-mcp"
        )
        detected = result.stdout.strip()
        self.assertTrue(os.path.exists(detected), f"Detected path does not exist: {detected}")

    def test_env_override_path(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "EnvBookmarks"
            p.write_text("{}")
            orig = os.environ.get("BROWSER_BOOKMARKS_PATH")
            try:
                os.environ["BROWSER_BOOKMARKS_PATH"] = str(p)
                importlib.reload(server)
                self.assertEqual(server.BOOKMARKS_PATH, str(p))
            finally:
                if orig is None:
                    os.environ.pop("BROWSER_BOOKMARKS_PATH", None)
                else:
                    os.environ["BROWSER_BOOKMARKS_PATH"] = orig

    def test_search_bookmarks(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_tmp_bookmarks(td)
            results = server.search_bookmarks("example", limit=10, path=path)
            self.assertTrue(any(r["url"].startswith("https://example.com") for r in results))
            results2 = server.search_bookmarks("mysite", path=path)
            self.assertTrue(any(r["name"] == "MySite" for r in results2))

    def test_search_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_tmp_bookmarks(td)
            results = server.search_bookmarks("no-such-term", path=path)
            self.assertEqual(results, [])

    def test_list_bookmarks_and_limit(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_tmp_bookmarks(td)
            items = server.list_bookmarks(limit=1, path=path)
            self.assertEqual(len(items), 1)
            items2 = server.list_bookmarks(limit=10, path=path)
            self.assertTrue(any(i["name"] == "MySite" for i in items2))

    def test_list_empty(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "EmptyBookmarks"
            p.write_text(json.dumps(make_bookmarks_json([]), ensure_ascii=False))
            items = server.list_bookmarks(path=str(p))
            self.assertEqual(items, [])

    def test_get_bookmark_stats(self):
        with tempfile.TemporaryDirectory() as td:
            path = self.make_tmp_bookmarks(td)
            stats = server.get_bookmark_stats(path=path)
            self.assertEqual(stats["total_bookmarks"], 3)
            self.assertGreaterEqual(stats["folder_count"], 2)

    def test_add_bookmark(self):
        with tempfile.TemporaryDirectory() as td:
            src = self.make_tmp_bookmarks(td)
            dest = Path(td) / "BookmarksCopy"
            Path(src).replace(dest)
            res = server.add_bookmark("New", "https://new.example", folder_path="Dev", path=str(dest))
            self.assertTrue(res["success"])
            data = server.load_bookmarks(str(dest))
            found = False
            for root in data.get("roots", {}).values():
                def walk(node):
                    nonlocal found
                    if node.get("type") == "url" and node.get("url") == "https://new.example":
                        found = True
                    elif node.get("type") == "folder":
                        for c in node.get("children", []):
                            walk(c)
                walk(root)
            self.assertTrue(found)

    def test_add_duplicate_url(self):
        with tempfile.TemporaryDirectory() as td:
            src = self.make_tmp_bookmarks(td)
            dest = Path(td) / "Bk"
            Path(src).replace(dest)
            r1 = server.add_bookmark("Dup", "https://example.com", folder_path="Dev", path=str(dest))
            r2 = server.add_bookmark("Dup2", "https://example.com", folder_path="Dev", path=str(dest))
            self.assertTrue(r1["success"] and r2["success"])
            data = server.load_bookmarks(str(dest))
            urls = []
            for root in data.get("roots", {}).values():
                def collect(node):
                    if node.get("type") == "url":
                        urls.append(node.get("url"))
                    elif node.get("type") == "folder":
                        for c in node.get("children", []):
                            collect(c)
                collect(root)
            self.assertGreaterEqual(urls.count("https://example.com"), 2)

    def test_update_bookmark_name_and_url(self):
        with tempfile.TemporaryDirectory() as td:
            src = self.make_tmp_bookmarks(td)
            dest = Path(td) / "Bk2"
            Path(src).replace(dest)
            r = server.update_bookmark("https://example.com", new_name="Updated", new_url="https://updated.example", path=str(dest))
            self.assertTrue(r["success"])
            self.assertGreaterEqual(r["updated"], 1)
            data = server.load_bookmarks(str(dest))
            found = False
            for root in data.get("roots", {}).values():
                def walk(node):
                    nonlocal found
                    if node.get("type") == "url" and node.get("url") == "https://updated.example":
                        found = True
                    elif node.get("type") == "folder":
                        for c in node.get("children", []):
                            walk(c)
                walk(root)
            self.assertTrue(found)

    def test_update_nonexistent(self):
        r = server.update_bookmark("https://does-not-exist.example", new_name="X")
        self.assertFalse(r["success"])

    def test_delete_bookmark(self):
        with tempfile.TemporaryDirectory() as td:
            src = self.make_tmp_bookmarks(td)
            dest = Path(td) / "Bk3"
            Path(src).replace(dest)
            r = server.delete_bookmark("https://example.com", path=str(dest))
            self.assertTrue(r["success"])
            self.assertGreaterEqual(r["deleted"], 1)
            data = server.load_bookmarks(str(dest))
            def present(data):
                for root in data.get("roots", {}).values():
                    def walk(node):
                        if node.get("type") == "url" and node.get("url") == "https://example.com":
                            return True
                        if node.get("type") == "folder":
                            for c in node.get("children", []):
                                if walk(c):
                                    return True
                        return False
                    if walk(root):
                        return True
                return False
            self.assertFalse(present(data))

    def test_delete_nonexistent(self):
        r = server.delete_bookmark("https://nope.example")
        self.assertFalse(r["success"])

    def test_concurrent_operations(self):
        with tempfile.TemporaryDirectory() as td:
            src = self.make_tmp_bookmarks(td)
            dest = Path(td) / "Concurrent"
            Path(src).replace(dest)
            def adder(i):
                server.add_bookmark(f"C{i}", f"https://c{i}.example", folder_path="Dev", path=str(dest))
            def deleter(i):
                server.delete_bookmark(f"https://c{i}.example", path=str(dest))
            threads = []
            for i in range(10):
                t = threading.Thread(target=adder, args=(i,))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            threads = []
            for i in range(10):
                t = threading.Thread(target=deleter, args=(i,))
                threads.append(t)
                t.start()
            for t in threads:
                t.join()
            data = server.load_bookmarks(str(dest))
            self.assertIsNotNone(data)

    def test_corrupted_file_handling(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Bad"
            p.write_text("notjson")
            r = server.add_bookmark("x", "https://x.example", path=str(p))
            self.assertFalse(r["success"])
            r2 = server.update_bookmark("https://x.example", new_name="y", path=str(p))
            self.assertFalse(r2["success"])
            r3 = server.delete_bookmark("https://x.example", path=str(p))
            self.assertFalse(r3["success"])

    def test_unicode_bookmarks(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Uni"
            data = make_bookmarks_json([
                {"type": "folder", "name": "目录", "children": [
                    {"type": "url", "name": "站点😊", "url": "https://例子.测试", "date_added": "1"}
                ]}
            ])
            p.write_text(json.dumps(data, ensure_ascii=False))
            items = server.list_bookmarks(path=str(p))
            self.assertTrue(any("站点" in i["name"] for i in items))
            res = server.search_bookmarks("例子", path=str(p))
            self.assertTrue(any("例子" in r["url"] for r in res))

    def test_nested_folders(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "Nested"
            nested = {"type": "folder", "name": "A", "children": [
                {"type": "folder", "name": "B", "children": [
                    {"type": "url", "name": "Deep", "url": "https://deep.example", "date_added": "1"}
                ]}
            ]}
            p.write_text(json.dumps(make_bookmarks_json([nested]), ensure_ascii=False))
            items = server.list_bookmarks(path=str(p))
            self.assertTrue(any(i["url"] == "https://deep.example" for i in items))

    def test_tools_list_and_initialize(self):
        req = {"jsonrpc": "2.0", "id": 1, "method": "initialize"}
        res = server.handle_request(req)
        self.assertTrue(res["result"]["protocolVersion"].startswith("2026"))
        req2 = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
        res2 = server.handle_request(req2)
        self.assertIn("tools", res2["result"])


if __name__ == '__main__':
    unittest.main()
