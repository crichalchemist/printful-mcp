"""The polling decisions, and proof the sync and async drivers cannot diverge.

The drivers are the reason this module exists: if the MCP server's loop can
settle a task differently from the CLI's, moving the loops into the core bought
nothing. Every driver test therefore runs both colours over the same responses
and compares what they produced, message text included.
"""

import pytest

from printful_core.errors import PrintfulError
from printful_core.polling import (
    classify_task,
    poll_estimation_task,
    poll_estimation_task_async,
    poll_mockup_task,
    poll_mockup_task_async,
    task_body,
)
from printful_core.request import Request

PENDING = {"data": {"id": "t1", "status": "pending"}}
REQUEST = Request("GET", "/mockup-tasks")


def make_sender(responses, tail=PENDING):
    """Replays `responses`, then repeats `tail` forever.

    A finite sender cannot be used on the timeout path: `interval=0` against a
    wall-clock deadline runs an unbounded number of iterations, and a sender
    that runs dry fails the test for a reason that has nothing to do with the
    timeout being tested.
    """
    queued = list(responses)
    sent = []

    def send(request):
        sent.append(request)
        return queued.pop(0) if queued else tail

    send.sent = sent
    return send


def make_async_sender(responses, tail=PENDING):
    inner = make_sender(responses, tail)

    async def send(request):
        return inner(request)

    send.sent = inner.sent
    return send


def raised(fn, *args, **kwargs):
    with pytest.raises(PrintfulError) as caught:
        fn(*args, **kwargs)
    return caught.value


async def raised_async(fn, *args, **kwargs):
    with pytest.raises(PrintfulError) as caught:
        await fn(*args, **kwargs)
    return caught.value


# --------------------------------------------------------------------------
# The pure decisions, exercised with no transport at all
# --------------------------------------------------------------------------


def test_task_body_unwraps_the_data_envelope():
    assert task_body({"data": {"status": "completed"}}) == {"status": "completed"}


def test_task_body_unwraps_a_single_element_list():
    """Printful returns the mockup task inside a list; the task is element 0."""
    assert task_body({"data": [{"status": "failed"}]}) == {"status": "failed"}


def test_task_body_reads_an_unenveloped_task():
    assert task_body({"status": "pending"}) == {"status": "pending"}


def test_task_body_of_an_empty_list_is_not_a_task():
    assert task_body({"data": []}) == {}


def test_task_body_of_a_non_dict_response_is_not_a_task():
    assert task_body(["nope"]) == {}


def test_classify_reads_the_two_terminal_states():
    assert classify_task({"status": "completed"}) == "completed"
    assert classify_task({"status": "failed"}) == "failed"


def test_classify_treats_anything_unsettled_as_pending():
    """Keep polling on a status we do not recognize rather than returning it."""
    assert classify_task({"status": "pending"}) == "pending"
    assert classify_task({"status": "in_progress"}) == "pending"
    assert classify_task({}) == "pending"


# --------------------------------------------------------------------------
# Estimation: both drivers settle the task the same way
# --------------------------------------------------------------------------

DONE = {"data": {"id": "t1", "status": "completed", "costs": {"total": "25.00"}}}
FAILED = {"data": {"id": "t1", "status": "failed", "failure_reasons": ["bad variant", "no stock"]}}


async def test_estimation_drivers_return_the_same_completed_task():
    sync_send = make_sender([PENDING, PENDING, DONE])
    async_send = make_async_sender([PENDING, PENDING, DONE])

    from_sync = poll_estimation_task(REQUEST, sync_send, "t1", {}, 5.0, 0)
    from_async = await poll_estimation_task_async(REQUEST, async_send, "t1", {}, 5.0, 0)

    assert from_sync == from_async == DONE
    assert len(sync_send.sent) == len(async_send.sent) == 3


async def test_estimation_drivers_report_the_same_failure():
    sync_error = raised(
        poll_estimation_task, REQUEST, make_sender([PENDING, FAILED]), "t1", {}, 5.0, 0
    )
    async_error = await raised_async(
        poll_estimation_task_async, REQUEST, make_async_sender([PENDING, FAILED]), "t1", {}, 5.0, 0
    )

    assert sync_error.message == async_error.message
    assert sync_error.detail == async_error.detail == FAILED["data"]
    assert sync_error.message == "Order estimation failed: bad variant; no stock"


def test_estimation_failure_says_so_when_printful_gives_no_reason():
    error = raised(
        poll_estimation_task,
        REQUEST,
        make_sender([{"data": {"status": "failed"}}]),
        "t1",
        {},
        5.0,
        0,
    )
    assert error.message == "Order estimation failed: no reason given"


async def test_estimation_drivers_report_the_same_timeout():
    sync_error = raised(poll_estimation_task, REQUEST, make_sender([]), "t9", {}, 0.01, 0)
    async_error = await raised_async(
        poll_estimation_task_async, REQUEST, make_async_sender([]), "t9", {}, 0.01, 0
    )

    assert sync_error.message == async_error.message
    assert sync_error.detail == async_error.detail
    assert sync_error.message == "Order estimation task t9 still pending after 0.01s."
    assert sync_error.detail == {"task_id": "t9", "last_response": PENDING}


async def test_estimation_timeout_before_the_first_reread_reports_the_created_task():
    """An already-spent deadline still has something to show the caller."""
    created = {"data": {"id": "t9", "status": "pending"}}
    sync_error = raised(poll_estimation_task, REQUEST, make_sender([]), "t9", created, 0, 0)
    async_error = await raised_async(
        poll_estimation_task_async, REQUEST, make_async_sender([]), "t9", created, 0, 0
    )

    assert sync_error.detail == async_error.detail
    assert sync_error.detail["last_response"] is created


async def test_estimation_drivers_both_read_a_task_delivered_in_a_list():
    """Widened in task 15: this shape used to raise AttributeError here."""
    listed = {"data": [{"id": "t1", "status": "completed"}]}
    from_sync = poll_estimation_task(REQUEST, make_sender([listed]), "t1", {}, 5.0, 0)
    from_async = await poll_estimation_task_async(
        REQUEST, make_async_sender([listed]), "t1", {}, 5.0, 0
    )
    assert from_sync == from_async == listed


# --------------------------------------------------------------------------
# Mockups: both drivers settle the task the same way
# --------------------------------------------------------------------------

MOCKUP_DONE = {"data": [{"id": "t1", "status": "completed"}]}
MOCKUP_FAILED = {"data": [{"id": "t1", "status": "failed", "reason": "bad file"}]}
MOCKUP_PENDING = {"data": [{"id": "t1", "status": "pending"}]}


async def test_mockup_drivers_return_the_same_completed_task():
    sync_send = make_sender([MOCKUP_PENDING, MOCKUP_DONE], tail=MOCKUP_PENDING)
    async_send = make_async_sender([MOCKUP_PENDING, MOCKUP_DONE], tail=MOCKUP_PENDING)

    from_sync = poll_mockup_task(REQUEST, sync_send, "t1", 5.0, 0)
    from_async = await poll_mockup_task_async(REQUEST, async_send, "t1", 5.0, 0)

    assert from_sync == from_async == MOCKUP_DONE
    assert len(sync_send.sent) == len(async_send.sent) == 2


async def test_mockup_drivers_report_the_same_failure():
    sync_error = raised(poll_mockup_task, REQUEST, make_sender([MOCKUP_FAILED]), "t1", 5.0, 0)
    async_error = await raised_async(
        poll_mockup_task_async, REQUEST, make_async_sender([MOCKUP_FAILED]), "t1", 5.0, 0
    )

    assert sync_error.message == async_error.message
    assert sync_error.detail == async_error.detail == MOCKUP_FAILED["data"][0]
    assert sync_error.message == "Mockup task t1 failed: bad file"


def test_mockup_failure_says_so_when_printful_gives_no_reason():
    error = raised(
        poll_mockup_task, REQUEST, make_sender([{"data": [{"status": "failed"}]}]), "t1", 5.0, 0
    )
    assert error.message == "Mockup task t1 failed: no reason given"


HINT = "Re-check with: mockup status t7"


async def test_mockup_drivers_report_the_same_timeout_with_the_recovery_hint():
    """The hint is the only way a user recovers a task the CLI stopped watching."""
    sync_error = raised(
        poll_mockup_task, REQUEST, make_sender([], tail=MOCKUP_PENDING), "t7", 0.01, 0, HINT
    )
    async_error = await raised_async(
        poll_mockup_task_async,
        REQUEST,
        make_async_sender([], tail=MOCKUP_PENDING),
        "t7",
        0.01,
        0,
        HINT,
    )

    assert sync_error.message == async_error.message
    assert sync_error.detail == async_error.detail
    assert sync_error.message == (
        "Mockup task t7 still pending after 0.01s. Re-check with: mockup status t7"
    )
    assert sync_error.detail == {"task_id": "t7", "last_response": MOCKUP_PENDING}


async def test_mockup_timeout_without_a_hint_does_not_trail_a_space():
    """A caller with no recovery advice gets a sentence, not a sentence plus room."""
    sync_error = raised(
        poll_mockup_task, REQUEST, make_sender([], tail=MOCKUP_PENDING), "t7", 0.01, 0
    )
    async_error = await raised_async(
        poll_mockup_task_async, REQUEST, make_async_sender([], tail=MOCKUP_PENDING), "t7", 0.01, 0
    )

    assert sync_error.message == async_error.message
    assert sync_error.message == "Mockup task t7 still pending after 0.01s."


def test_mockup_timeout_joins_the_hint_with_exactly_one_space():
    error = raised(
        poll_mockup_task, REQUEST, make_sender([], tail=MOCKUP_PENDING), "t7", 0.01, 0, "Do X."
    )
    assert error.message == "Mockup task t7 still pending after 0.01s. Do X."


def test_the_core_names_no_cli_command():
    """The MCP server has no shell; a core default must not send it to one."""
    import inspect

    import printful_core.polling as polling_module

    assert "mockup status" not in inspect.getsource(polling_module)


async def test_mockup_timeout_before_the_first_reread_has_no_response_to_show():
    sync_error = raised(poll_mockup_task, REQUEST, make_sender([]), "t7", 0, 0)
    async_error = await raised_async(
        poll_mockup_task_async, REQUEST, make_async_sender([]), "t7", 0, 0
    )

    assert sync_error.detail == async_error.detail
    assert sync_error.detail == {"task_id": "t7", "last_response": {}}
