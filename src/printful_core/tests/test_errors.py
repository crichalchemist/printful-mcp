import pytest

from printful_core.errors import (
    PrintfulAuthError,
    PrintfulError,
    PrintfulRateLimitError,
    extract_message,
    raise_for_status,
)


class TestExtractMessage:
    def test_live_envelope_wins(self):
        body = {"data": "msg", "error": {"reason": "NotFound", "message": "real"}}
        assert extract_message(body) == "real"

    def test_rfc9457_detail(self):
        assert extract_message({"detail": "Bad variant"}) == "Bad variant"

    def test_detail_beats_title_when_both_are_present(self):
        """RFC 9457 sends both, and they are not interchangeable.

        `title` is the generic class of error ("Invalid request"); `detail` is
        the specific one ("Bad variant id 999"). A caller who gets the title
        learns nothing actionable. The real API sends both on every validation
        failure, so the ordering -- not either key alone -- is what matters.
        """
        assert (
            extract_message({"detail": "Bad variant id 999", "title": "Invalid request"})
            == "Bad variant id 999"
        )

    def test_rfc9457_title_fallback(self):
        assert extract_message({"title": "Invalid"}) == "Invalid"

    def test_data_string_only(self):
        assert extract_message({"data": "plain"}) == "plain"

    def test_v1_result_string(self):
        assert extract_message({"code": 404, "result": "Not Found"}) == "Not Found"

    def test_plain_string_body(self):
        assert extract_message("boom") == "boom"

    def test_unrecognized_body(self):
        assert extract_message({"weird": {"nested": 1}}) is None


class TestRaiseForStatus:
    def test_401_mentions_expiry(self):
        with pytest.raises(PrintfulAuthError, match="expire"):
            raise_for_status(401, {}, "https://api.printful.com/v2/orders")

    def test_403_mentions_scope(self):
        with pytest.raises(PrintfulAuthError, match="scope"):
            raise_for_status(403, {}, "https://api.printful.com/v2/orders")

    @pytest.mark.parametrize("status", [429, 419])
    def test_rate_limit_carries_retry_after(self, status):
        with pytest.raises(PrintfulRateLimitError) as exc:
            raise_for_status(status, {}, "url", headers={"Retry-After": "30"})
        assert exc.value.retry_after == "30"

    def test_rate_limit_message_names_mockup_limits(self):
        with pytest.raises(PrintfulRateLimitError, match="2/60s"):
            raise_for_status(429, {}, "url", headers={})

    def test_error_message_and_status_preserved(self):
        body = {"data": "m", "error": {"reason": "BadRequest", "message": "m"}}
        with pytest.raises(PrintfulError) as exc:
            raise_for_status(400, body, "url")
        assert exc.value.message == "m"
        assert exc.value.status_code == 400
        assert exc.value.detail == body

    def test_unrecognized_body_names_the_status(self):
        with pytest.raises(PrintfulError, match="status 500"):
            raise_for_status(500, {"weird": 1}, "https://api.printful.com/v2/x")
