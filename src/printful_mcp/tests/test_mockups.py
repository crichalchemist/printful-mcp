"""The mockups adapter."""
from printful_mcp.models.inputs import (
    CreateMockupTaskInput,
    GetMockupTaskInput,
    ListMockupStylesInput,
)
from printful_mcp.tools import mockups


def _create(**over):
    base = dict(product_id=71, variant_ids="4011,4012",
                design_url="https://example.com/art.png")
    base.update(over)
    return CreateMockupTaskInput(**base)


async def test_the_image_format_field_is_not_the_response_format(transport):
    """`format` on this model means jpg or png, and feeds image_format.

    Every other tool's `format` selects markdown or json. Mapping this one to
    the wrong core parameter produces a request asking for a mockup in
    "markdown".
    """
    await mockups.create_mockup_task(transport, _create(format="png"))
    assert transport.last.json["format"] == "png"


async def test_omitted_style_ids_are_left_out_of_the_request(transport):
    """Printful picks its own defaults only when the key is absent.

    An empty `mockup_style_ids` list is not the same as no key: the API reads
    it as "these zero styles" and returns nothing.
    """
    await mockups.create_mockup_task(transport, _create())
    product = transport.last.json["products"][0]
    assert "mockup_style_ids" not in product


async def test_supplied_style_ids_arrive_as_integers(transport):
    """The model takes a comma-separated string; the API takes numbers."""
    await mockups.create_mockup_task(transport, _create(mockup_style_ids="7, 9"))
    assert transport.last.json["products"][0]["mockup_style_ids"] == [7, 9]


async def test_a_task_returned_as_a_one_element_list_is_unwrapped(transport):
    """/mockup-tasks returns the task inside a list.

    Reading `data` directly renders a list where a dict is expected.
    """
    transport._responses.append({"data": [{"id": "m1", "status": "pending"}]})
    out = await mockups.get_mockup_task(transport, GetMockupTaskInput(task_id="m1"))
    assert "# Mockup Task m1" in out
    assert "in progress" in out


async def test_a_missing_task_says_so(transport):
    transport._responses.append({"data": []})
    out = await mockups.get_mockup_task(transport, GetMockupTaskInput(task_id="nope"))
    assert out == "No task found with ID nope"


async def test_styles_are_fetched_per_product(transport):
    await mockups.list_mockup_styles(transport, ListMockupStylesInput(product_id=71))
    assert transport.last.path == "/catalog-products/71/mockup-styles"
