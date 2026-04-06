#!/usr/bin/env python3
"""
Browser Bookmarks MCP Server

A cross-browser, cross-platform MCP server for Chromium-based browser
bookmarks. Supports automatic detection of bookmark files for multiple
browsers, search, statistics, CRUD operations and optional filesystem
watching (watchdog).

Environment variable to override detected path:
 - BROWSER_BOOKMARKS_PATH

Tools exposed (MCP JSON-RPC):
 - search_bookmarks
 - list_bookmarks
 - get_bookmark_stats
 - add_bookmark
 - update_bookmark
 - delete_bookmark
 - start_watch
 - stop_watch

The server reads/writes the Chromium "Bookmarks" JSON file. Modifying
the bookmarks file while the browser is running may be overwritten by the
browser; use with care.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from typing import Any, Dict, List, Optional
from datetime import datetime

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False

# Candidate paths for multiple Chromium-based browsers across platforms.
_DEFAULT_CANDIDATES = [
    # Windows (LOCALAPPDATA)
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\User Data\Default\Bookmarks"),
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data\Default\Bookmarks"),
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\User Data\Default\Bookmarks"),
    os.path.expandvars(r"%LOCALAPPDATA%\Vivaldi\User Data\Default\Bookmarks"),
    # macOS
    os.path.expanduser("~/Library/Application Support/Microsoft Edge/Default/Bookmarks"),
    os.path.expanduser("~/Library/Application Support/Google/Chrome/Default/Bookmarks"),
    os.path.expanduser("~/Library/Application Support/BraveSoftware/Brave-Browser/Default/Bookmarks"),
    # Linux
    os.path.expanduser("~/.config/microsoft-edge/Default/Bookmarks"),
    os.path.expanduser("~/.config/google-chrome/Default/Bookmarks"),
    os.path.expanduser("~/.config/BraveSoftware/Brave-Browser/Default/Bookmarks"),
]

BOOKMARKS_PATH = os.environ.get("BROWSER_BOOKMARKS_PATH") or next(
    (p for p in _DEFAULT_CANDIDATES if p and os.path.exists(p)),
    _DEFAULT_CANDIDATES[0],
)

LOCK = threading.Lock()


def load_bookmarks(path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Load bookmarks JSON from disk. Returns None on error."""
    path = path or BOOKMARKS_PATH
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def save_bookmarks(data: Dict[str, Any], path: Optional[str] = None) -> bool:
    """Atomically write bookmarks JSON back to disk. Returns True on success."""
    path = path or BOOKMARKS_PATH
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _iter_roots(bookmarks: Dict[str, Any]):
    if not isinstance(bookmarks, dict):
        return
    roots = bookmarks.get("roots", {})
    for k, v in roots.items():
        if k == "sync_transaction_version":
            continue
        yield v


def _find_folder_node(root: Dict[str, Any], path_parts: List[str]) -> Optional[Dict[str, Any]]:
    """Traverse folder hierarchy and return folder node matching path_parts."""
    if not path_parts:
        return root
    name = path_parts[0]
    for child in root.get("children", []):
        if child.get("type") == "folder" and child.get("name", "").lower() == name.lower():
            return _find_folder_node(child, path_parts[1:])
    return None


def search_bookmarks(query: str, limit: int = 20, path: Optional[str] = None) -> List[Dict[str, Any]]:
    data = load_bookmarks(path)
    if not data:
        return []
    results: List[Dict[str, Any]] = []
    q = (query or "").lower()

    def _search(node: Any, folder: str = ""):
        if not isinstance(node, dict):
            return
        t = node.get("type")
        if t == "url":
            name = node.get("name", "")
            url = node.get("url", "")
            if q in name.lower() or q in url.lower():
                results.append({"name": name, "url": url, "folder": folder, "date_added": node.get("date_added")})
        elif t == "folder":
            folder_name = node.get("name", "")
            new_folder = f"{folder}/{folder_name}" if folder else folder_name
            for child in node.get("children", []):
                _search(child, new_folder)

    for root in _iter_roots(data):
        _search(root, root.get("name", ""))
    return results[:limit]


def list_bookmarks(limit: int = 100, path: Optional[str] = None) -> List[Dict[str, Any]]:
    data = load_bookmarks(path)
    if not data:
        return []
    items: List[Dict[str, Any]] = []

    def _list(node: Any, folder: str = ""):
        if not isinstance(node, dict):
            return
        t = node.get("type")
        if t == "url":
            items.append({"name": node.get("name", ""), "url": node.get("url", ""), "folder": folder})
        elif t == "folder":
            folder_name = node.get("name", "")
            new_folder = f"{folder}/{folder_name}" if folder else folder_name
            for child in node.get("children", []):
                _list(child, new_folder)

    for root in _iter_roots(data):
        _list(root, root.get("name", ""))
    return items[:limit]


def get_bookmark_stats(path: Optional[str] = None) -> Dict[str, Any]:
    data = load_bookmarks(path)
    if not data:
        return {"total_bookmarks": 0, "folder_count": 0, "path": path or BOOKMARKS_PATH}
    total = 0
    folders = set()

    def _count(node: Any):
        nonlocal total
        if not isinstance(node, dict):
            return
        t = node.get("type")
        if t == "url":
            total += 1
        elif t == "folder":
            folders.add(node.get("name", ""))
            for child in node.get("children", []):
                _count(child)

    for root in _iter_roots(data):
        _count(root)

    return {"total_bookmarks": total, "folder_count": len(folders), "path": path or BOOKMARKS_PATH}


def add_bookmark(name: str, url: str, folder_path: str = "", path: Optional[str] = None) -> Dict[str, Any]:
    """Add a bookmark under folder_path (e.g. 'Bookmarks Bar/Dev')."""
    path = path or BOOKMARKS_PATH
    with LOCK:
        data = load_bookmarks(path)
        if not data:
            return {"success": False, "error": "Bookmarks file not found or unreadable"}
        # choose first root to append into (Default / Bookmarks Bar etc.)
        root = next(_iter_roots(data), None)
        if not root:
            return {"success": False, "error": "No roots in bookmarks file"}
        # find target folder
        target = root
        if folder_path:
            parts = [p for p in folder_path.strip('/').split('/') if p]
            candidate = None
            for r in _iter_roots(data):
                candidate = _find_folder_node(r, parts)
                if candidate:
                    target = candidate
                    break
            if not candidate:
                return {"success": False, "error": "Folder not found"}
        # create a simple bookmark node
        new_node = {"type": "url", "name": name, "url": url, "date_added": str(int(time.time()*1000000))}
        target.setdefault("children", []).append(new_node)
        ok = save_bookmarks(data, path)
        return {"success": ok}


def update_bookmark(old_url: str, new_name: Optional[str] = None, new_url: Optional[str] = None, path: Optional[str] = None) -> Dict[str, Any]:
    """Update bookmark(s) matching old_url. Returns count."""
    path = path or BOOKMARKS_PATH
    with LOCK:
        data = load_bookmarks(path)
        if not data:
            return {"success": False, "error": "Bookmarks file not found or unreadable"}
        updated = 0

        def _update(node: Any):
            nonlocal updated
            if not isinstance(node, dict):
                return
            if node.get("type") == "url" and node.get("url") == old_url:
                if new_name is not None:
                    node["name"] = new_name
                if new_url is not None:
                    node["url"] = new_url
                updated += 1
            elif node.get("type") == "folder":
                for child in node.get("children", []):
                    _update(child)

        for root in _iter_roots(data):
            _update(root)

        if updated > 0:
            ok = save_bookmarks(data, path)
            return {"success": ok, "updated": updated}
        return {"success": True, "updated": 0}


def delete_bookmark(url: str, path: Optional[str] = None) -> Dict[str, Any]:
    """Delete bookmarks matching url. Returns count deleted."""
    path = path or BOOKMARKS_PATH
    with LOCK:
        data = load_bookmarks(path)
        if not data:
            return {"success": False, "error": "Bookmarks file not found or unreadable"}
        deleted = 0

        def _filter(node: Any):
            nonlocal deleted
            if not isinstance(node, dict):
                return node
            if node.get("type") == "folder":
                children = []
                for child in node.get("children", []):
                    if isinstance(child, dict) and child.get("type") == "url" and child.get("url") == url:
                        deleted += 1
                        continue
                    elif isinstance(child, dict) and child.get("type") == "folder":
                        _filter(child)
                        children.append(child)
                    else:
                        children.append(child)
                node["children"] = children
            return node

        for root in _iter_roots(data):
            _filter(root)

        if deleted > 0:
            ok = save_bookmarks(data, path)
            return {"success": ok, "deleted": deleted}
        return {"success": True, "deleted": 0}


# Watcher implementation
class _WatcherHandler(FileSystemEventHandler):
    def __init__(self, callback):
        self.callback = callback

    def on_modified(self, event):
        if event and not event.is_directory:
            try:
                self.callback()
            except Exception:
                pass


class BookmarksWatcher:
    def __init__(self, path: str, callback):
        self.path = path
        self.callback = callback
        self.observer = None

    def start(self):
        if not WATCHDOG_AVAILABLE:
            raise RuntimeError("watchdog not available")
        if not os.path.exists(self.path):
            raise FileNotFoundError(self.path)
        handler = _WatcherHandler(self.callback)
        self.observer = Observer()
        directory = os.path.dirname(self.path)
        self.observer.schedule(handler, directory, recursive=False)
        self.observer.start()

    def stop(self):
        if self.observer:
            self.observer.stop()
            self.observer.join()
            self.observer = None


_WATCHER: Optional[BookmarksWatcher] = None


def handle_request(request: Dict[str, Any]) -> Dict[str, Any]:
    global _WATCHER
    request_id = request.get("id")
    method = request.get("method")
    params = request.get("params", {})
    response: Dict[str, Any] = {"jsonrpc": "2.0", "id": request_id}

    if method == "initialize":
        response["result"] = {"protocolVersion": "2026-04-06", "serverInfo": {"name": "browser-bookmarks-mcp", "version": "0.1.0"}}
        return response

    if method == "tools/list":
        response["result"] = {"tools": [
            {"name": "search_bookmarks", "description": "Search bookmarks", "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "limit": {"type": "number", "default": 20}}, "required": ["query"]}},
            {"name": "list_bookmarks", "description": "List bookmarks", "inputSchema": {"type": "object", "properties": {"limit": {"type": "number", "default": 100}}}},
            {"name": "get_bookmark_stats", "description": "Get stats", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "add_bookmark", "description": "Add bookmark", "inputSchema": {"type": "object", "properties": {"name": {"type": "string"}, "url": {"type": "string"}, "folder": {"type": "string"}} , "required": ["name","url"]}},
            {"name": "update_bookmark", "description": "Update bookmark by url", "inputSchema": {"type": "object", "properties": {"old_url": {"type": "string"}, "new_name": {"type": "string"}, "new_url": {"type": "string"}}, "required": ["old_url"]}},
            {"name": "delete_bookmark", "description": "Delete bookmark by url", "inputSchema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]}},
            {"name": "start_watch", "description": "Start filesystem watcher", "inputSchema": {"type": "object", "properties": {}}},
            {"name": "stop_watch", "description": "Stop filesystem watcher", "inputSchema": {"type": "object", "properties": {}}},
        ]}
        return response

    if method == "tools/call":
        tool_name = params.get("name")
        arguments = params.get("arguments", {})
        # dispatch
        try:
            if tool_name == "search_bookmarks":
                q = arguments.get("query", "")
                limit = int(arguments.get("limit", 20))
                res = search_bookmarks(q, limit)
                response["result"] = {"success": True, "results": res}
                return response
            if tool_name == "list_bookmarks":
                limit = int(arguments.get("limit", 100))
                res = list_bookmarks(limit)
                response["result"] = {"success": True, "results": res}
                return response
            if tool_name == "get_bookmark_stats":
                res = get_bookmark_stats()
                response["result"] = {"success": True, "stats": res}
                return response
            if tool_name == "add_bookmark":
                name = arguments.get("name")
                url = arguments.get("url")
                folder = arguments.get("folder", "")
                res = add_bookmark(name, url, folder)
                response["result"] = res
                return response
            if tool_name == "update_bookmark":
                old_url = arguments.get("old_url")
                new_name = arguments.get("new_name")
                new_url = arguments.get("new_url")
                res = update_bookmark(old_url, new_name, new_url)
                response["result"] = res
                return response
            if tool_name == "delete_bookmark":
                url = arguments.get("url")
                res = delete_bookmark(url)
                response["result"] = res
                return response
            if tool_name == "start_watch":
                if _WATCHER is None:
                    _WATCHER = BookmarksWatcher(BOOKMARKS_PATH, lambda: print(f"[{datetime.now().isoformat()}] Bookmarks changed", file=sys.stderr))
                    try:
                        _WATCHER.start()
                        response["result"] = {"success": True, "message": "Watcher started", "path": BOOKMARKS_PATH}
                    except Exception as e:
                        response["result"] = {"success": False, "error": str(e)}
                else:
                    response["result"] = {"success": True, "message": "Watcher already running"}
                return response
            if tool_name == "stop_watch":
                if _WATCHER is not None:
                    _WATCHER.stop()
                    _WATCHER = None
                    response["result"] = {"success": True, "message": "Watcher stopped"}
                else:
                    response["result"] = {"success": True, "message": "Watcher not running"}
                return response
            response["result"] = {"success": False, "error": f"Tool not found: {tool_name}"}
            return response
        except Exception as e:
            response["result"] = {"success": False, "error": str(e)}
            return response

    response["error"] = {"code": -32600, "message": f"Method not found: {method}"}
    return response


def main() -> None:
    print("Browser Bookmarks MCP Server 0.1.0", file=sys.stderr)
    print(f"Detected bookmarks path: {BOOKMARKS_PATH}", file=sys.stderr)
    print("Watchdog available:" , WATCHDOG_AVAILABLE, file=sys.stderr)
    print("Ready for JSON-RPC messages...", file=sys.stderr)
    print("", file=sys.stderr, flush=True)

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
            print(json.dumps(response, ensure_ascii=False))
            sys.stdout.flush()
        except json.JSONDecodeError as e:
            error_response = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": f"Parse error: {e}"}}
            print(json.dumps(error_response))
            sys.stdout.flush()
        except Exception as e:
            import traceback
            error_response = {"jsonrpc": "2.0", "id": request.get("id") if isinstance(request, dict) else None, "error": {"code": -32603, "message": f"Internal error: {e}", "data": traceback.format_exc()}}
            print(json.dumps(error_response))
            sys.stdout.flush()


if __name__ == "__main__":
    main()
