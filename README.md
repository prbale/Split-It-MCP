# Split-It — a very simple MCP server

A one-file [Model Context Protocol](https://modelcontextprotocol.io) server for learning and demos.
It tracks shared expenses (a trip, a team lunch) and tells you **who owes whom**.

> "Rahul paid ₹1,800 for dinner for the three of us, I paid ₹6,000 for the hotel. Who owes whom?"
> → Claude calls the tools and answers: *Amit pays Prashant ₹2,150, Rahul pays Prashant ₹1,250.*

| File | What it is |
|---|---|
| `server.py` | The MCP server (~150 lines with comments) — **read this first** |
| `demo_client.py` | A tiny MCP client that calls the server with no AI, to show what happens behind the scenes |
| `requirements.txt` | One dependency: the official MCP Python SDK |

## What it shows

| MCP concept | In this server |
|---|---|
| **Tools** — functions the AI can call | `add_expense`, `list_expenses`, `get_balances`, `settle_up`, `clear_expenses` |
| **Tool annotations** — hints about behaviour | read-only tools are marked `readOnlyHint`; `clear_expenses` is marked `destructiveHint` |
| **Errors** — telling the AI what went wrong | `ToolError("amount must be greater than 0")` → the AI gets `isError: true` and can retry |
| **Resource** — read-only data by URI | `splitit://expenses` |
| **Prompt** — reusable instruction | `trip_summary` |
| **Transport** | stdio (the client starts the server as a child process) |

## 1. Set up (Python 3.11+)

```bash
cd split-it-mcp
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## 2. See it work without any AI

```bash
python demo_client.py
```

Expected output (abridged):

```
Connected to 'split-it'
Tools the AI can see:
  • add_expense     Record a shared expense.
  • get_balances    Each person's balance. ...
── get_balances
{ "Prashant": 3400.0, "Rahul": -1250.0, "Amit": -2150.0 }
── settle_up
Amit pays Prashant ₹2,150.00
Rahul pays Prashant ₹1,250.00
── invalid input → isError=True: Error executing tool add_expense: amount must be greater than 0
```

## 3. Use it from Claude

Get the full paths first (with the virtual environment active):

```bash
which python      # Windows: where python   → e.g. /Users/you/split-it-mcp/.venv/bin/python
pwd               # Windows: cd             → e.g. /Users/you/split-it-mcp
```

**Claude Code**

```bash
claude mcp add split-it -- /Users/you/split-it-mcp/.venv/bin/python /Users/you/split-it-mcp/server.py
```
Start `claude`, type `/mcp`, and check that **split-it** is connected.

**Claude Desktop** — edit `claude_desktop_config.json`
(macOS `~/Library/Application Support/Claude/`, Windows `%APPDATA%\Claude\`), then fully restart the app:

```json
{
  "mcpServers": {
    "split-it": {
      "command": "/Users/you/split-it-mcp/.venv/bin/python",
      "args": ["/Users/you/split-it-mcp/server.py"]
    }
  }
}
```

**Claude custom connector URL** — this is the mode used by the dialog in your screenshot.
Anthropic rejects `localhost` and `0.0.0.0` here, so you need a public HTTPS URL.
The easiest way is to expose the server with a Cloudflare tunnel.

### Option A: use trycloudflare.com (recommended for quick testing)

1. Terminal 1: leave `cloudflared` running. It owns this URL; if you stop it, the URL dies.

```bash
cloudflared tunnel --url http://localhost:8000
```

2. Terminal 2: stop the server with **Ctrl+C** if it is already running, then start it:

```bash
cd /Users/prashantbale/Documents/projects/AI/split-it-mcp
source .venv/bin/activate
PUBLIC_HOST=pub-places-advertise-farmers.trycloudflare.com python server.py --http
```

The first line should say:

```text
public host: pub-places-advertise-farmers.trycloudflare.com
```

3. Terminal 3: test it:

```bash
curl -s -w "\nHTTP %{http_code}\n" https://pub-places-advertise-farmers.trycloudflare.com/mcp \
  -H "Content-Type: application/json" -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"curl","version":"1"}}}'
```

You should see `"name":"split-it"` and **HTTP 200**.

4. In Claude.ai, update the connector because the old `steve-dogs-…` address no longer exists:

- Remove the old Split-It connector, or edit it.
- Set the **MCP server URL** to:

```text
https://pub-places-advertise-farmers.trycloudflare.com/mcp
```

- Click **Connect** or **Reconnect**.

5. Test: in a chat with the connector turned on, ask *"Who owes whom?"*. You should see `POST /mcp … 200 OK` lines appear in Terminal 2.

> If step 3 does not return HTTP 200, paste the curl output and the last few lines from Terminal 2 here and I can help troubleshoot it.

### Option B: use a regular public host
If you already have a public server or tunnel, use that instead, for example:

```text
https://my-server.example.com/mcp
```

**Try saying:**
1. *"We went to Lonavala. I (Prashant) paid ₹6,000 for the hotel for me, Rahul and Amit. Rahul paid ₹1,800 for dinner for all three. Amit paid ₹900 for a cab for him and Rahul."*
2. *"Who owes whom?"*
3. *"Summarise the trip"* — or pick the **trip_summary** prompt from the prompt menu.
4. *"Clear everything and start a new trip"* — Claude should ask you to confirm first, because the tool is marked destructive.

## 4. Inspect it visually (optional)

The official [MCP Inspector](https://github.com/modelcontextprotocol/inspector) shows every tool,
its JSON Schema, and the raw requests and responses (needs Node.js):

```bash
npx @modelcontextprotocol/inspector python server.py
```

## How a tool becomes something the AI can use

```python
@mcp.tool()
def add_expense(description: str, amount: float, paid_by: str, split_between: list[str]) -> str:
    """Record a shared expense."""
```

The SDK reads this function and publishes:
- **name** → `add_expense`
- **description** → the docstring (this is what the AI reads to decide *when* to call it)
- **input schema** → from the type hints: `amount` must be a number, `split_between` an array of strings

So writing a good docstring is as important as writing the code.

## Practice exercises

1. Add a tool `remove_expense(index: int)` and mark it `destructiveHint=True`.
2. Add a `currency` parameter with a default of `"INR"`.
3. Add a resource `splitit://balances` that returns the balances.
4. Store expenses per trip (`trip: str` on every tool) so you can track several trips.
5. Change `amount: float` to use `Decimal` and see how the schema changes.

## Things to know

- **Never `print()` in a stdio server** — stdout carries the protocol. Log to stderr instead.
- Data is saved in `expenses.json` next to `server.py`. Delete the file to reset.
- This uses the **MCP Python SDK v2**, where the server class is `MCPServer`
  (older tutorials call it `FastMCP` from `mcp.server.fastmcp`).
