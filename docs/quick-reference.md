# Quick Reference

Tools exposed by the MCP server (JSON-RPC via stdin/stdout):

- search_bookmarks {query: string, limit?: number}
- list_bookmarks {limit?: number}
- get_bookmark_stats {}

Example JSON-RPC call:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"search_bookmarks","arguments":{"query":"github","limit":5}}}
```

The server will reply with a JSON-RPC response on stdout.