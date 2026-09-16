"""Every tool's json branch returns the body, not prose.

An agent asking for format="json" is going to parse the result. A tool that
falls through to its markdown renderer hands back something that raises on
json.loads -- and the failure surfaces in the caller, not here, unless this
asserts it.

The two tools without the branch are excluded by the property, not by name:
`printful_list_countries` takes no arguments at all, and
`CreateMockupTaskInput.format` is `Literal["jpg", "png"]`, an *image* format
and the documented exception. A name list would go stale silently.
"""

import json

import pytest

from printful_mcp.tests.toolsamples import REGISTERED, sample_input, tool_function

# The body every tool is handed. Shallow on purpose: this asserts the branch
# returns the body verbatim, not that any renderer can format it.
BODY = {"data": {"id": 1, "marker": "verbatim-body"}}


def test_the_json_branch_is_asserted_across_the_whole_surface():
    """A builder returning None for everything would skip every case below.

    Each skip is silent and the file would still report green, so the count of
    inputs actually built is the only thing standing between this test and a
    file that asserts nothing. A floor, not an equality: a tool added later
    should not have to come back here.
    """
    built = [name for name in REGISTERED if sample_input(name, fmt="json") is not None]
    assert len(built) >= 30, (
        f"built a json input for only {len(built)} of {len(REGISTERED)} tools, so "
        f"the rest of this file skipped: missing {sorted(set(REGISTERED) - set(built))}"
    )


@pytest.mark.parametrize("tool_name", sorted(REGISTERED))
async def test_the_json_branch_returns_the_body_and_not_prose(tool_name, transport):
    params = sample_input(tool_name, fmt="json")
    if params is None:
        pytest.skip(f"{tool_name} has no markdown/json format field")

    transport._responses.append(BODY)
    out = await tool_function(tool_name)(transport, params)

    parsed = json.loads(out)
    assert parsed == BODY, f"{tool_name} returned something other than the body"
