"""File library tools for the Printful MCP server."""

import json

from printful_core.endpoints import files
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import AddFileInput, GetFileInput


async def add_file(transport: AsyncTransport, params: AddFileInput) -> str:
    """
    Add a file to the Printful file library.

    Uploads a design file from URL. The file is processed asynchronously.
    Status will be 'waiting' initially, then 'ok' or 'failed' after processing.
    """
    try:
        request = files.add_file(
            params.url, filename=params.filename, visible=params.visible)
        data = await transport.send(request)
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.file_added(data.get("data", {}))
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_file(transport: AsyncTransport, params: GetFileInput) -> str:
    """
    Get information about a file in the library.

    Returns file details including processing status, dimensions, and URLs.
    """
    try:
        data = await transport.send(files.get_file(params.file_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.file_detail(data.get("data", {}))
    except PrintfulError as e:
        return f"Error: {e.message}"
