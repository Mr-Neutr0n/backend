"""A provider timeout is retried, not cut off by the time limit (#35).

anymail's HTTP backends wait 30 seconds to connect and 30 more for each
read by default. A slow provider could then outlast the send task's
60-second soft time limit, and the timeout would end the task as an
unexpected error instead of a retried timeout. The request timeout must
end well before the soft limit.
"""

from anymail.backends.resend import EmailBackend

from apps.emails.tasks import send_queued_email


def _total_seconds(timeout: object) -> float:
    """The longest a request can wait: connect plus one read.

    requests applies a single number to the connect and to the read
    separately, so it counts twice.
    """
    if isinstance(timeout, tuple):
        connect, read = timeout
        return float(connect + read)
    assert isinstance(timeout, int | float)
    return 2 * float(timeout)


def test_the_resend_request_timeout_ends_before_the_soft_limit() -> None:
    backend = EmailBackend(api_key="re_made_up_test_only")

    total = _total_seconds(backend.timeout)

    assert send_queued_email.soft_time_limit is not None
    assert total <= send_queued_email.soft_time_limit / 2
