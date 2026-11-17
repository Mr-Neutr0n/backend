# 0016. Email through an outbox and the email queue

- Status: Proposed
- Date: 2026-11-17

## Context

Sign-up, email verification, and password reset send email (ADR 0014). Until issue #35, allauth sent each message inside the request, and with DEBUG off every message was discarded, so nobody could verify an address in a deployed environment. #35 adds a real provider, Resend, through django-anymail, and moves sending onto the `email` queue (ADR 0006), so a slow or failing provider never slows or fails a request.

Every account email carries the recipient's address, and most carry a verification or reset key. ADR 0009 and the Celery rules forbid personal data and secrets in task arguments and return values: messages sit in the broker, and the worker logs them. allauth also needs the request to render its messages, so the task cannot render them itself.

## Decision

- The account adapter's `send_mail` renders the message as allauth does, then calls `apps.emails.services.queue_email`. That stores the rendered message as a `QueuedEmail` row in the request's transaction and, once the transaction commits, queues `send_queued_email` with only the row's id. Every email OPEN sends goes through `queue_email`.
- `send_queued_email` claims the row with a ten-minute lease (`select_for_update(skip_locked=True)`, then `last_attempt_at`), sends outside any transaction, and deletes the row once the message is sent or has finally failed. A missing row and a row another run holds are skipped, so a task that runs twice sends once.
- Network errors, timeouts, rate limits (429), and server errors (5xx) from anymail, and SMTP and socket errors from other backends, are retried up to five times with exponential backoff from 30 seconds and up to 30 seconds of jitter, each wait at most 600 seconds. Any other provider error is final. A final failure logs one ERROR line with the row id, the template, the error class, and the status code, and deletes the row. An error that is not the provider's (a bug) keeps the row and fails the task.
- No log line the task or Celery writes holds the address, the subject, the body, or the provider's error text. Retries and failures carry sanitized exceptions (`EmailSendRetry`, `EmailSendFailed`) with only the id, template, class, and status code.
- A beat task, `sweep_queued_emails`, runs every 15 minutes. It deletes rows older than three days (allauth's keys have expired by then) and queues again, by id, rows older than an hour with no send attempt in the last hour. Before a retry, and when the sweep queues a row, the attempt time is set to one lease ago instead of cleared: the task can claim the row at once, but the sweep skips it for most of an hour. So a row has one retry chain, and a worker that is down or behind does not collect one more task per row at each sweep.
- anymail's request timeout is 5 seconds to connect and 20 for the answer, well under the send task's 60-second soft time limit, so a slow provider is a timeout the task retries. This recovers a row whose task never reached the broker: the commit hook is robust, so a broker that is down at commit never fails the request.
- `EMAIL_BACKEND` is a backend path from the environment, passed through as is. With DEBUG on and no value, messages print to the console. With DEBUG off a value is required, and backends that print or keep messages are refused. Resend needs `RESEND_API_KEY` with DEBUG off. `DEFAULT_FROM_EMAIL` is required with DEBUG off.
- Only `django-anymail[resend]` is installed. Switching to Amazon SES is `uv add "django-anymail[amazon-ses]"`, `EMAIL_BACKEND=anymail.backends.amazon_ses.EmailBackend`, and boto3's standard AWS variables: no code change.

## Consequences

- Delivery is at least once, not exactly once. A worker that crashes after the provider accepted a message but before the row is deleted leaves the row behind. The sweep queues it again about an hour later (an hour with no attempt, then its next 15-minute run), and the message is sent twice.
- A row holds the address and a key at rest until delivery, at most three days. No admin is registered for it, and its `__str__` shows only its id. The personal data inventory lists it. It has no link to the Account, so Account deletion (#116) must delete the rows addressed to the Account's addresses.
- The provider keeps its own copy of each message. Resend keeps email data for 30 days on every plan below Enterprise. The inventory records this.
- A deployment with DEBUG off must set `EMAIL_BACKEND` and `DEFAULT_FROM_EMAIL`, or it does not start.
- The issue named a `send_templated_email` task. Messages are rendered in the request, so the task sends a stored message and is named `send_queued_email`.
- Tests run in a transaction that never commits, so the accounts tests run each request's commit hooks when it returns.

## Alternatives considered

- **Pass the address and context to the task, and render there.** It puts the address and the key in the broker and the worker log, and allauth's rendering needs the request.
- **Send in the request.** A slow or failing provider would slow or fail sign-up and password reset.
- **Keep sent rows for a record of delivery.** It would keep addresses and keys longer than delivery needs. The provider keeps its own record.
- **Install every anymail provider extra.** Only Resend is used. Another provider is a dependency change when it is needed.
