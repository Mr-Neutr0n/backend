# Email sending domain

This page tells a maintainer how to set up the domain OPEN sends email from. It covers the Resend setup, every DNS record, the DMARC rollout, how to check the records, and the app settings. How the app sends email (the outbox, the `email` queue, retries) is in ADR 0016 and the Email section of `README.md`.

## Sending domain

- Sending domain: `mail.openpb.org`
- From address: `OPEN <noreply@mail.openpb.org>`
- DMARC aggregate reports go to `dmarc@openpb.org`.

OPEN sends from a subdomain, not from `openpb.org`. Mailbox providers track sender reputation per domain. If the sending domain ever has a deliverability problem (a bounce spike, spam complaints, a block list entry), it stays on `mail.openpb.org` and does not affect `openpb.org`, which is the project's website. The subdomain also gets its own DMARC policy, so it can be tightened without touching the root domain.

The `openpb.org` DNS zone is on Cloudflare. Before this setup, it has no MX, SPF, or DMARC record, and none of the records below exist.

## Resend setup

1. In the Resend dashboard, add the domain `mail.openpb.org`.
2. Pick the region. The default is `us-east-1` (North Virginia). The others are `eu-west-1`, `sa-east-1`, and `ap-northeast-1`. The region sets the MX host, so pick it before you add the records.
3. Resend shows the records for the domain. Add them in Cloudflare as listed in [DNS records](#dns-records). Where the dashboard and this page differ, the dashboard is right: update this page.
4. Set up the DMARC report mailbox (see [The report mailbox](#the-report-mailbox)), then add the DMARC record.
5. In the Resend dashboard, verify the domain. DNS changes can take a few minutes to a few hours to show up. Use [Verify with dig](#verify-with-dig) to check them yourself.
6. Create an API key with sending access only, limited to `mail.openpb.org`. Store it only in the deploy environment (see [App settings](#app-settings)). Never commit it, paste it in an issue, or put it in `.env.example`.

## DNS records

Add these records in Cloudflare, in the `openpb.org` zone. Cloudflare takes names relative to the zone, so enter the name in the "Cloudflare name" column. Every record is DNS only: Cloudflare never proxies MX or TXT records, so there is no proxy setting to change.

`<region>` is the region picked in Resend, such as `us-east-1`.

| Purpose | Type | Full name | Cloudflare name | Value |
| --- | --- | --- | --- | --- |
| Bounces and feedback | MX | `send.mail.openpb.org` | `send.mail` | `feedback-smtp.<region>.amazonses.com`, priority `10` |
| SPF | TXT | `send.mail.openpb.org` | `send.mail` | `v=spf1 include:amazonses.com ~all` |
| DKIM | TXT | `resend._domainkey.mail.openpb.org` | `resend._domainkey.mail` | The public key from the Resend dashboard |
| DMARC | TXT | `_dmarc.mail.openpb.org` | `_dmarc.mail` | `v=DMARC1; p=none; rua=mailto:dmarc@openpb.org` |

Notes:

- The DKIM value is a public key that Resend makes for this domain. Copy it from the dashboard exactly, in one piece. This page does not hold it, and the private key never leaves Resend.
- The MX and SPF records are on `send.mail.openpb.org`, the return path Resend uses for bounces. They are not on `mail.openpb.org` itself, so `mail.openpb.org` does not receive mail.
- Leave TTL on Auto.

### DMARC alignment

DMARC passes when SPF or DKIM passes and is aligned with the From domain, `mail.openpb.org`.

- DKIM: Resend signs each message with `d=mail.openpb.org`. That is the From domain itself, so DKIM is aligned under strict or relaxed alignment. This is the check DMARC relies on.
- SPF: SPF is checked on the return path, `send.mail.openpb.org`. It shares the organizational domain `openpb.org` with the From domain, so SPF is aligned under relaxed alignment, the DMARC default. Do not add `aspf=s` to the DMARC record: strict SPF alignment would fail.

### The report mailbox

DMARC reports are sent by email to `dmarc@openpb.org`, so that address must receive mail before the DMARC record is published. `openpb.org` has no MX record today, so set up receiving first. Cloudflare Email Routing is one way: turn it on for `openpb.org` and forward `dmarc@openpb.org` to a maintainer's mailbox. Cloudflare adds the MX and SPF records it needs on `openpb.org` itself. Those records do not affect the sending records above.

The report address is on `openpb.org`, the same organizational domain as `mail.openpb.org`. So no external report authorization record (`mail.openpb.org._report._dmarc.openpb.org`) is needed.

## DMARC rollout

1. Start with `p=none`, as in the table above. Receivers then send reports but do not act on failures.
2. Read the reports for at least four weeks, and through at least one stretch of normal sending. Free DMARC report viewers can turn the XML reports into a summary.
3. Move on only when the reports show that every message from Resend passes DKIM aligned with `mail.openpb.org`, and every source that fails is one that should not send as OPEN. If a real sender fails, fix it first and wait for a clean week.
4. Change the record to `v=DMARC1; p=quarantine; pct=25; rua=mailto:dmarc@openpb.org`. After a week of clean reports, raise `pct` to `100` (or drop the `pct` tag, which means 100).
5. Later, and only if wanted: `p=reject`, after some months at `p=quarantine; pct=100` with clean reports.

The root domain `openpb.org` has no SPF or DMARC record. This setup does not need one. Adding `v=spf1 -all` and a DMARC record on `openpb.org` would stop others from sending as the root domain, but that is a separate, optional change. If Cloudflare Email Routing is on, keep the SPF record it adds instead of `-all`.

## Verify with dig

Run each command after adding the records. Before setup, each one prints nothing.

```bash
dig +short send.mail.openpb.org MX
```

Expected: `10 feedback-smtp.us-east-1.amazonses.com.` (with your region).

```bash
dig +short send.mail.openpb.org TXT
```

Expected: `"v=spf1 include:amazonses.com ~all"`

```bash
dig +short resend._domainkey.mail.openpb.org TXT
```

Expected: one quoted string that starts with `p=`, the same public key the Resend dashboard shows. A long key can come back as several quoted strings in a row; that is normal.

```bash
dig +short _dmarc.mail.openpb.org TXT
```

Expected: `"v=DMARC1; p=none; rua=mailto:dmarc@openpb.org"`

```bash
dig +short openpb.org MX
```

Expected after Cloudflare Email Routing is on: Cloudflare's MX hosts (`route1.mx.cloudflare.net.` and others). This is for the report mailbox, not for sending.

## App settings

Set these in the deploy environment (DigitalOcean App Platform), with `DJANGO_DEBUG` off:

- `EMAIL_BACKEND=anymail.backends.resend.EmailBackend`
- `RESEND_API_KEY`: the key from step 6 of [Resend setup](#resend-setup). Set it as an encrypted environment variable in App Platform. It is required with this backend and DEBUG off.
- `DEFAULT_FROM_EMAIL=OPEN <noreply@mail.openpb.org>`. Required with DEBUG off. `SERVER_EMAIL` follows it.

Settings refuse to start when a required value is missing, and the error names the variable, not its value. To check the whole path, sign up with an address you control on staging and confirm the verification email arrives. In the received message's headers, `Authentication-Results` should show `dkim=pass` with `header.d=mail.openpb.org`, `spf=pass`, and `dmarc=pass`.
