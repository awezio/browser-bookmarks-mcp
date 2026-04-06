# Browser Bookmarks MCP

A Model Context Protocol (MCP) server for managing Chromium-based browser bookmarks across platforms. A lightweight, mcporter-friendly service to search, list, and manage bookmarks programmatically.

Features

- ✅ Cross-browser support for Chromium-based browsers (Edge, Chrome, Brave, Vivaldi, Arc)
- ✅ Cross-platform: works on Windows, macOS, and Linux
- ✅ Fast full-text search of bookmarks and folders
- ✅ CRUD operations: add, update, delete bookmarks
- ✅ Usage statistics and simple analytics (counts, domain breakdown)
- ✅ Realtime watch mode to observe external bookmark file changes
- ✅ MCP-compatible over stdin/stdout for easy integration with OpenClaw/mcporter

Supported Browsers

Browser | Windows | macOS | Linux
---|:---:|:---:|:---:
Google Chrome | ✅ | ✅ | ✅
Microsoft Edge | ✅ | ✅ | ✅
Brave | ✅ | ✅ | ✅
Vivaldi | ✅ | ✅ | ✅
Arc | ❌ | ✅ | ❌

Note: Support depends on the browser using the Chromium bookmark format and the host OS providing a readable Bookmarks file.

Installation

1. Clone or copy the repository

2. (Optional) Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Optionally override auto-detection of bookmark file:

```bash
export BROWSER_BOOKMARKS_PATH=/path/to/Bookmarks
```

Quick Start

Run the server:

```bash
python3 src/server.py
```

Register with mcporter (example):

```bash
mcporter config add browser-bookmarks python3 src/server.py
mcporter list browser-bookmarks --schema
mcporter call browser-bookmarks.search_bookmarks --query "github" --limit 5
```

Configuration

The server attempts to locate common Chromium bookmark files automatically. Set BROWSER_BOOKMARKS_PATH to override detection when needed.

Tools (MCP)

- search_bookmarks {query, limit}
- list_bookmarks {limit}
- get_bookmark_stats {}
- add_bookmark {name, url, folder}
- update_bookmark {old_url, new_name?, new_url?}
- delete_bookmark {url}
- start_watch {}
- stop_watch {}

Tools API Reference

search_bookmarks
- Description: Search bookmarks by text query. Returns a list of matching bookmarks with name, url, folder, and last_modified (if available).
- Parameters: {"query": string, "limit": integer}
- Example request (JSON):

```json
{ "method": "search_bookmarks", "params": { "query": "openclaw", "limit": 10 } }
```

- Example response (JSON):

```json
{
  "result": [
    {"name": "OpenClaw Home", "url": "https://openclaw.example/", "folder": "Dev/Tools", "last_modified": "2024-12-01T12:34:56Z"},
    {"name": "mcporter docs", "url": "https://mcporter.example/docs", "folder": "Dev/Tools", "last_modified": "2024-11-20T09:10:11Z"}
  ],
  "count": 2
}
```

get_bookmark_stats
- Description: Return aggregated statistics about the bookmark set (total count, unique domains, top domains).
- Parameters: {} (none)
- Example request (JSON):

```json
{ "method": "get_bookmark_stats", "params": {} }
```

- Example response (JSON):

```json
{
  "total_bookmarks": 1243,
  "unique_domains": 312,
  "top_domains": [
    {"domain": "github.com", "count": 213},
    {"domain": "stackoverflow.com", "count": 98},
    {"domain": "example.com", "count": 45}
  ]
}
```

Other tools (brief)

- list_bookmarks {"limit": number} — List bookmarks in traversal order, limited by count.
- add_bookmark {"name": string, "url": string, "folder": string} — Add a new bookmark. Returns the created bookmark object.
- update_bookmark {"old_url": string, "new_name"?: string, "new_url"?: string} — Update an existing bookmark matching old_url.
- delete_bookmark {"url": string} — Delete a bookmark by URL. Returns success boolean.
- start_watch {} / stop_watch {} — Start or stop realtime watching of the bookmark file. Emits file change events when active.

Warning

> Important: Many Chromium browsers overwrite their Bookmarks file while running (for example during an orderly shutdown or profile sync). Writing directly to a live bookmarks file may be overwritten by the browser process. Use the watch mode or communicate with the browser's sync APIs when possible. Always keep backups of bookmarks before performing bulk writes.

Development

- Entrypoint: src/server.py
- Tests: lightweight tests in tests/
- Packaging metadata: pyproject.toml

Contributing

Contributions are welcome. Please open issues or pull requests against the repository. Keep changes focused and include tests for new behavior.

Authors

- awezio

License

This project is licensed under the Apache License, Version 2.0 - see the LICENSE file for details.

