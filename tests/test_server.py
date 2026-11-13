import pytest
from mcp import Client

from mcp_contact_me.server import mcp


@pytest.mark.asyncio
async def test_tool_schema_derives_project_from_token() -> None:
    async with Client(mcp) as client:
        result = await client.list_tools()

    tools = {tool.name: tool for tool in result.tools}
    assert set(tools) == {"send_email", "send_telegram"}
    for tool in tools.values():
        properties = tool.input_schema["properties"]
        assert "project" not in properties
        assert properties["urgency"]["enum"] == ["low", "normal", "high"]
