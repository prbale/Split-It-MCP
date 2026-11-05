"""
Split-It — a very simple MCP server for learning.

This project is intentionally short so you can see the core idea of MCP in one file.
MCP = Model Context Protocol. It lets an AI app (like Claude Desktop or Claude Code)
connect to tools, data, and reusable prompts that live outside the model.

Think of it like this:
    - Tool: a function the AI can call to do work (example: add_expense)
    - Resource: a read-only data source the AI can read (example: splitit://expenses)
    - Prompt: a reusable instruction template the AI can use (example: trip_summary)

This file demonstrates all three.

The app itself is a shared-expense tracker:
    - add_expense: record an expense
    - list_expenses: view all expenses
    - get_balances: calculate who owes whom
    - settle_up: compute the minimal payments to settle
    - clear_expenses: reset the trip

Run it:
    python server.py          (normally your MCP client starts it for you)
"""

import json
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

# --------------------------------------------------------------------------------------------
# 1. Create the server. The name is what MCP clients (Claude Desktop, Claude Code) show.
# --------------------------------------------------------------------------------------------
mcp = MCPServer(
    name="split-it",
    instructions="Track shared expenses and work out who owes whom. Amounts are in rupees.",
)

# --------------------------------------------------------------------------------------------
# 2. Storage. A JSON file next to this script, so data survives restarts. No database needed.
# --------------------------------------------------------------------------------------------
DATA_FILE = Path(__file__).with_name("expenses.json")


def load() -> list[dict]:
    """Read expenses from the JSON file, or return an empty list if it doesn't exist yet."""
    return json.loads(DATA_FILE.read_text()) if DATA_FILE.exists() else []


def save(expenses: list[dict]) -> None:
    """Write expenses to the JSON file in a readable, indented format."""
    DATA_FILE.write_text(json.dumps(expenses, indent=2))


def balances(expenses: list[dict]) -> dict[str, float]:
    """Calculate each person's net balance across all expenses.

    Each payer is credited with the full amount, then each participant is charged
    an equal share. Positive means the person should receive money; negative means
    the person owes money.
    """
    result: dict[str, float] = {}
    for e in expenses:
        share = e["amount"] / len(e["split_between"])
        result[e["paid_by"]] = result.get(e["paid_by"], 0) + e["amount"]
        for person in e["split_between"]:
            result[person] = result.get(person, 0) - share
    return {name: round(value, 2) for name, value in result.items()}


# --------------------------------------------------------------------------------------------
# 3. TOOLS. A tool is a normal Python function with @mcp.tool().
#    - The docstring becomes the description the AI reads.
#    - The type hints become the JSON Schema for the arguments.
# --------------------------------------------------------------------------------------------
READ_ONLY = ToolAnnotations(readOnlyHint=True)


@mcp.tool()
def add_expense(description: str, amount: float, paid_by: str, split_between: list[str]) -> str:
    """Record a shared expense.

    Args:
        description: What it was for, e.g. "Dinner at Lonavala".
        amount: Total amount in rupees.
        paid_by: Name of the person who paid.
        split_between: Everyone who shares this cost (include the payer if they share it).
    """
    # Raise ToolError for bad input: the AI receives isError=true plus this message, and can retry.
    if amount <= 0:
        raise ToolError("amount must be greater than 0")
    if not split_between:
        raise ToolError("split_between needs at least one name")

    names = [n.strip().title() for n in split_between]  # "rahul " → "Rahul"
    expenses = load()
    expenses.append(
        {"description": description, "amount": round(amount, 2), "paid_by": paid_by.strip().title(), "split_between": names}
    )
    save(expenses)
    return f"Added '{description}' (₹{amount:,.2f}) paid by {paid_by.title()}, split {len(names)} ways."


@mcp.tool(annotations=READ_ONLY)
def list_expenses() -> list[dict]:
    """List every recorded expense."""
    return load()


@mcp.tool(annotations=READ_ONLY)
def get_balances() -> dict[str, float]:
    """Each person's balance. Positive means they should get money back; negative means they owe."""
    return balances(load())


@mcp.tool(annotations=READ_ONLY)
def settle_up() -> list[str]:
    """The fewest payments needed so that everyone is even."""
    owes = sorted([[n, -b] for n, b in balances(load()).items() if b < 0], key=lambda x: -x[1])
    gets = sorted([[n, b] for n, b in balances(load()).items() if b > 0], key=lambda x: -x[1])

    payments = []
    while owes and gets:  # match the biggest debtor with the biggest creditor
        amount = round(min(owes[0][1], gets[0][1]), 2)
        payments.append(f"{owes[0][0]} pays {gets[0][0]} ₹{amount:,.2f}")
        owes[0][1] -= amount
        gets[0][1] -= amount
        if owes[0][1] < 0.01:
            owes.pop(0)
        if gets[0][1] < 0.01:
            gets.pop(0)
    return payments or ["Everyone is settled up."]


@mcp.tool(annotations=ToolAnnotations(destructiveHint=True))
def clear_expenses() -> str:
    """Delete ALL expenses to start a new trip. Ask the user to confirm before calling this."""
    save([])
    return "All expenses cleared."


# --------------------------------------------------------------------------------------------
# 4. RESOURCE. Read-only data identified by a URI. The user (or AI) can attach it as context.
# --------------------------------------------------------------------------------------------
@mcp.resource("splitit://expenses", mime_type="application/json", description="All expenses as JSON")
def expenses_resource() -> str:
    return json.dumps(load(), indent=2)


# --------------------------------------------------------------------------------------------
# 5. PROMPT. A reusable instruction the user can pick from the client's prompt menu.
# --------------------------------------------------------------------------------------------
@mcp.prompt()
def trip_summary(trip_name: str = "our trip") -> str:
    """Summarise spending and say how to settle up."""
    return (
        f"Summarise the expenses for {trip_name}. Use list_expenses, get_balances and settle_up. "
        "Show a short table of expenses, the total spent, and the final list of payments."
    )


# --------------------------------------------------------------------------------------------
# 6. Start.
#    python server.py          → stdio: the client (Claude Code / Desktop) starts us as a child process.
#                                Never print() in stdio mode — stdout is reserved for protocol messages.
#    python server.py --http   → Streamable HTTP on http://127.0.0.1:8000/mcp, for remote clients such as
#                                a claude.ai custom connector (put an HTTPS tunnel in front, see README).
# --------------------------------------------------------------------------------------------
if __name__ == "__main__":
    import os
    import sys

    if "--http" in sys.argv:
        from mcp.server.transport_security import TransportSecuritySettings

        # The SDK rejects requests whose Host or Origin header is not on these lists (DNS-rebinding protection).
        # A tunnel forwards requests with its own host name (e.g. abc.trycloudflare.com), and claude.ai may send
        # an Origin header, so both must be allowed.
        public_host = os.getenv("PUBLIC_HOST", "").removeprefix("https://").removesuffix("/mcp").strip("/")
        allowed_hosts = ["127.0.0.1:*", "localhost:*"] + ([public_host] if public_host else [])
        allowed_origins = ["http://127.0.0.1:*", "http://localhost:*", "https://claude.ai", "https://claude.com"]
        if public_host:
            allowed_origins.append(f"https://{public_host}")
        print(f"Split-It HTTP server: local http://127.0.0.1:8000/mcp, public host: {public_host or '(none)'}")
        mcp.run(
            "streamable-http",
            host="127.0.0.1",
            port=8000,
            transport_security=TransportSecuritySettings(allowed_hosts=allowed_hosts, allowed_origins=allowed_origins),
        )
    else:
        mcp.run("stdio")
