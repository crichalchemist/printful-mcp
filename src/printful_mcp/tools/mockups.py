"""Mockup generator tools for the Printful MCP server."""

import json

from printful_core import polling
from printful_core.endpoints import mockups
from printful_core.errors import PrintfulError
from printful_core.format import markdown
from printful_core.transport import AsyncTransport

from ..models.inputs import (
    CreateMockupTaskInput,
    GetMockupTaskInput,
    ListMockupStylesInput,
    ListMockupTemplatesInput,
)


def _ids(raw: str) -> list:
    return [int(v.strip()) for v in raw.split(",") if v.strip()]


async def create_mockup_task(transport: AsyncTransport,
                             params: CreateMockupTaskInput) -> str:
    """
    Create a mockup generation task.

    Generates product mockups asynchronously. Returns a task ID; read the result
    with printful_get_mockup_task. Generation usually takes 10-30 seconds.

    Mockup creation is limited to 10 requests/60s (established stores) or
    2 requests/60s (new stores), with a 60s lockout when exceeded. Do not retry
    in a loop.
    """
    try:
        variant_ids = _ids(params.variant_ids)
        style_ids = _ids(params.mockup_style_ids) if params.mockup_style_ids else None
    except ValueError as e:
        return f"Error: {e}"

    try:
        request = mockups.create_task(
            params.product_id, variant_ids, params.design_url,
            placement=params.placement, technique=params.technique,
            style_ids=style_ids, image_format=params.format)
        data = await transport.send(request)
        body = polling.task_body(data)
        if not body:
            return json.dumps(data, indent=2)
        return (f"Mockup task created!\n\nTask ID: {body['id']}\n"
                f"Status: {body['status']}\n\n"
                "Use printful_get_mockup_task with this ID to check status and "
                "get mockup URLs.")
    except ValueError as e:
        return f"Error: {e}"
    except PrintfulError as e:
        return f"Error: {e.message}"


async def get_mockup_task(transport: AsyncTransport, params: GetMockupTaskInput) -> str:
    """
    Get mockup task status and results.

    Check whether mockup generation is complete and retrieve image URLs. Status
    is pending, completed, or failed.
    """
    try:
        data = await transport.send(mockups.get_task(params.task_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        body = polling.task_body(data)
        if not body:
            return f"No task found with ID {params.task_id}"
        return markdown.mockup_task(body)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_mockup_styles(transport: AsyncTransport,
                             params: ListMockupStylesInput) -> str:
    """
    List the mockup styles available for a catalog product.

    Style IDs are what printful_create_mockup_task takes in mockup_style_ids.
    """
    try:
        data = await transport.send(mockups.list_styles(params.product_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.mockup_styles(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"


async def list_mockup_templates(transport: AsyncTransport,
                                params: ListMockupTemplatesInput) -> str:
    """
    List the print-area templates for a catalog product.

    Templates give the printable dimensions a design must fit.
    """
    try:
        data = await transport.send(mockups.list_templates(params.product_id))
        if params.format == "json":
            return json.dumps(data, indent=2)
        return markdown.mockup_templates(data, params.product_id)
    except PrintfulError as e:
        return f"Error: {e.message}"
