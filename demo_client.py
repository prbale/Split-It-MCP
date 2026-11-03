"""
A tiny MCP *client* that starts server.py and calls its tools — no AI needed.

This script is a simple demonstration of how an AI app talks to an MCP server:
    1. start the server
    2. open a communication channel
    3. initialize the session
    4. ask for available tools
    5. call tools with arguments
    6. read a resource for extra context

Why this matters:
    The AI client does not directly call Python functions. It uses the MCP protocol, which
    standardizes how tools, prompts, and resources are exposed to the model.

Run:  python demo_client.py
"""

import json
import sys
from pathlib import Path

import anyio
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# This tells the client how to launch the MCP server as a local child process.
# It uses the same Python interpreter and starts server.py as a subprocess.
SERVER = StdioServerParameters(command=sys.executable, args=[str(Path(__file__).with_name("server.py"))])


def show(title: str, result) -> None:
    """Print a tool response in a simple readable format."""
    print(f"\n── {title}")
    for block in result.content:
        print(block.text)


async def main() -> None:
    # The client opens a stdio transport to the server process. This is one of the common MCP transports.
    # Once connected, we create a ClientSession to talk to the server using the MCP protocol.
    async with stdio_client(SERVER) as (read, write), ClientSession(read, write) as session:
        # Step 1: a protocol handshake. This tells the server the client supports MCP and fetches metadata.
        info = await session.initialize()
        print(f"Connected to '{info.server_info.name}'")

        # Step 2: list all tools the server exposes. The model can decide which ones to call later.
        tools = await session.list_tools()
        print("Tools the AI can see:")
        for tool in tools.tools:
            print(f"  • {tool.name:15} {tool.description.splitlines()[0]}")

        # Step 3: call a tool. Here we reset the expense list before adding data for the demo.
        await session.call_tool("clear_expenses", {})
        await session.call_tool(
            "add_expense",
            {
                "description": "Hotel in Lonavala",
                "amount": 6000,
                "paid_by": "Prashant",
                "split_between": ["Prashant", "Rahul", "Amit"],
            },
        )
        await session.call_tool(
            "add_expense",
            {"description": "Dinner", "amount": 1800, "paid_by": "Rahul", "split_between": ["Prashant", "Rahul", "Amit"]},
        )
        show(
            "add_expense (cab)",
            await session.call_tool(
                "add_expense", {"description": "Cab", "amount": 900, "paid_by": "Amit", "split_between": ["Rahul", "Amit"]}
            ),
        )
        show("get_balances", await session.call_tool("get_balances", {}))
        show("settle_up", await session.call_tool("settle_up", {}))

        bad = await session.call_tool(
            "add_expense", {"description": "Oops", "amount": -5, "paid_by": "X", "split_between": ["X"]}
        )
        print(f"\n── invalid input → isError={bad.is_error}: {bad.content[0].text}")

        resource = await session.read_resource("splitit://expenses")
        print(f"\n── resource splitit://expenses has {len(json.loads(resource.contents[0].text))} expenses")


anyio.run(main)
