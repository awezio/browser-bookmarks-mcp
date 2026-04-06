# Setup

1. Create a Python virtualenv (recommended):

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. If you run in Windows/WSL, set EDGE_BOOKMARKS_PATH to your Bookmarks file path.

3. Run the MCP server with:

```bash
python3 src/server.py
```

4. Use mcporter to register or call the server (optional).