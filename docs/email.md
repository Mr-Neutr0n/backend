# Email sending domain

This page tells a maintainer how to set up the domain OPEN sends email from. It covers the Resend setup, every DNS record, the DMARC rollout, how to check the records, and the app settings. How the app sends email (the outbox, the `email` queue, retries) is in ADR 0016 and the Email section of `README.md`.

## Sending domain

- Sending domain: `mail.openpb.org`
- From address: `OPEN <noreply@mail.openpb.org>`
- DMARC aggregate reports go to `dmarc@openpb.org`.

OPEN sends from a subdomain, not from `openpb.org`. Mailbox providers track sender reputation per domain. If the sending domain ever has a deliverability problem (a bounce spike, spam complaints, a block list entry), it stays on `mail.openpb.org` and does not affect `openpb.org`, which is the project's website. The subdomain also gets its own DMARC policy, so it can be tightened without touching the root domain.

The `openpb.org` DNS zone is on Cloudflare. Before this setup, none of the sending records under `mail.openpb.org` below existed.

## Resend setup

1. In the Resend dashboard, add the domain `mail.openpb.org`.
2. Pick the region. The default is `us-east-1` (North Virginia). The others are `eu-west-1`, `sa-east-1`, and `ap-northeast-1`. The region sets the bounce host in the records, so pick it before you add them.
3. Resend shows the records for the domain in its Records tab. Add exactly those records in Cloudflare, as described in [DNS records](#dns-records). Resend may show CNAME records for sending instead of the MX and TXT pair. For the sending records and DKIM, where the dashboard and this page differ, the dashboard is right: update this page. The DMARC record is the exception: always use this page's value, with `rua=mailto:dmarc@openpb.org`, even if the dashboard suggests another.
4. Set up the DMARC report mailbox (see [The report mailbox](#the-report-mailbox)), then add the DMARC record.
5. In the Resend dashboard, verify the domain. DNS changes can take a few minutes to a few hours to show up. Use [Verify with dig](#verify-with-dig) to check them yourself.
6. Keep open tracking and click tracking off for `mail.openpb.org`, and add no tracking subdomain CNAME. Click tracking rewrites every link through Resend's tracking host, including the verification and reset links that carry keys. Both kinds of tracking also report player behavior to a third party. The Resend row of `docs/privacy/personal-data-inventory.md` requires both to stay off.
7. Create an API key with sending access only, limited to `mail.openpb.org`. Store it only in the deploy environment (see [App settings](#app-settings)). Never commit it, paste it in an issue, or put it in `.env.example`.

## DNS records

Add the records in Cloudflare, in the `openpb.org` zone. Each record has three forms of its name:

- The full name of every record here ends in `.mail.openpb.org`, such as `send.mail.openpb.org`. The dashboard may show a name relative to `openpb.org` (such as `send.mail`) or relative to `mail.openpb.org` (such as `send`). Complete it so it ends in `.mail.openpb.org`: `send.mail` and `send` both become `send.mail.openpb.org`. A completed name that does not end in `.mail.openpb.org`, such as `send.openpb.org`, is wrong.
- The Cloudflare name is the full name minus `.openpb.org`, such as `send.mail`. Cloudflare takes names relative to the zone, so enter this one.
- The `dig` checks below use the full name.

Add exactly the sending and DKIM records the Resend dashboard shows. The DMARC record always uses the value in the table below, even if the dashboard suggests another (for example one with no `rua`), because the rollout needs the reports. For the sending records, expect one of two layouts:

- The older layout: an MX record and an SPF TXT record on `send.mail.openpb.org`, as in the table below.
- The CNAME layout: Resend may give CNAME records for sending instead. Resend says this can happen for domains created after August 2026, which includes `mail.openpb.org`. Add each CNAME with the target the dashboard shows, under its Cloudflare name (see the name forms above). With CNAMEs, add no MX or TXT record at the same name: a CNAME cannot share its name with any other record. Each CNAME verifies on its own, so the domain can show `partially_verified` until all of them resolve. Resend says a partially verified domain can still send, but without a fallback sending server, so wait until every CNAME verifies before production use.

Every record must be DNS only. Cloudflare never proxies MX or TXT records. It proxies a new CNAME by default, and a proxied CNAME never verifies, so set every CNAME to DNS only (grey cloud) when you add it.

`<region>` is the region picked in Resend, such as `us-east-1`.

| Purpose | Type | Full name | Cloudflare name | Value |
| --- | --- | --- | --- | --- |
| Bounces and feedback (older layout) | MX | `send.mail.openpb.org` | `send.mail` | `feedback-smtp.<region>.amazonses.com`, priority `10` |
| SPF (older layout) | TXT | `send.mail.openpb.org` | `send.mail` | `v=spf1 include:amazonses.com ~all` |
| DKIM | TXT | `resend._domainkey.mail.openpb.org` | `resend._domainkey.mail` | The public key from the Resend dashboard |
| DMARC | TXT | `_dmarc.mail.openpb.org` | `_dmarc.mail` | `v=DMARC1; p=none; rua=mailto:dmarc@openpb.org` |

Notes:

- The DKIM value is a public key that Resend makes for this domain. Copy it from the dashboard exactly, in one piece. This page does not hold it, and the private key never leaves Resend.
- In the older layout, the MX and SPF records are on `send.mail.openpb.org`, the return path Resend uses for bounces. In the CNAME layout, the dashboard shows the names. Either way, no record is on `mail.openpb.org` itself, so `mail.openpb.org` does not receive mail.
- If the dashboard shows the DKIM record as a CNAME, add it as a CNAME, DNS only, with the target the dashboard shows.
- Leave TTL on Auto.

### DMARC alignment

DMARC passes when SPF or DKIM passes and is aligned with the From domain, `mail.openpb.org`.

- DKIM: Resend signs each message with `d=mail.openpb.org`. That is the From domain itself, so DKIM is aligned under strict or relaxed alignment. This is the check DMARC relies on.
- SPF: SPF is checked on the return path, `send.mail.openpb.org` in the older layout (in the CNAME layout, a name under `mail.openpb.org` that the dashboard shows). It shares the organizational domain `openpb.org` with the From domain, so SPF is aligned under relaxed alignment, the DMARC default. Do not add `aspf=s` to the DMARC record: strict SPF alignment would fail.

### The report mailbox

DMARC reports are sent by email to `dmarc@openpb.org`, so that address must receive mail before the DMARC record is published. Cloudflare Email Routing is on for `openpb.org` and receives its mail. Before publishing the DMARC record, confirm in the Email Routing settings that a route for `dmarc@openpb.org` exists and forwards to a maintainer's mailbox. DNS cannot show a route, so check the settings, not `dig`. If Email Routing is ever off, turn it on first: Cloudflare then adds the MX and SPF records it needs on `openpb.org` itself. Those records do not affect the sending records above.

The report address is on `openpb.org`, the same organizational domain as `mail.openpb.org`. So no external report authorization record (`mail.openpb.org._report._dmarc.openpb.org`) is needed.

## DMARC rollout

1. Start with `p=none`, as in the table above. Receivers then send reports but do not act on failures.
2. Read the reports for at least four weeks, and through at least one stretch of normal sending. Free DMARC report viewers can turn the XML reports into a summary.
3. Move on only when the reports show that every message from Resend passes DKIM aligned with `mail.openpb.org`, and every source that fails is one that should not send as OPEN. If a real sender fails, fix it first and wait for a clean week.
4. Change the record to `v=DMARC1; p=quarantine; rua=mailto:dmarc@openpb.org`. Do not ramp up with `pct`: the successor to RFC 7489 (DMARCbis) removes it, so receivers that follow it ignore `pct` and apply the policy to all mail.
5. Later, and only if wanted: `p=reject`, after some months at `p=quarantine` with clean reports.

The root domain `openpb.org` has no DMARC record, and its SPF record comes from Cloudflare Email Routing. This setup does not need a DMARC record there. A DMARC record on `openpb.org` would stop others from sending as the root domain only with an enforcing policy (`p=quarantine` or `p=reject`), not with `p=none`. That is a separate, optional change. Keep the SPF record Email Routing adds; do not replace it with `-all`.

## Verify with dig

Run each command after adding the records. Before setup, each command for a record under `mail.openpb.org` prints nothing.

For the older layout:

```bash
dig +short send.mail.openpb.org MX
```

Expected: `10 feedback-smtp.us-east-1.amazonses.com.` (with your region).

```bash
dig +short send.mail.openpb.org TXT
```

Expected: `"v=spf1 include:amazonses.com ~all"`

For the CNAME layout, run this for each CNAME the dashboard shows, with its full name (see the name forms in [DNS records](#dns-records)):

```bash
dig +short <full name> CNAME
```

Expected: the target the dashboard shows for that name, with a trailing dot. Empty output means the record is missing or proxied: a proxied CNAME returns no CNAME answer. To tell them apart, run `dig +short <full name>` (no type). If that returns addresses, the record is proxied: switch it to DNS only.

For the DKIM record (if it is a CNAME, use `dig +short resend._domainkey.mail.openpb.org CNAME` and expect the dashboard's target):

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

Expected while Cloudflare Email Routing is on: three Cloudflare MX hosts with their priorities, such as `11 route1.mx.cloudflare.net.`, plus `route2` and `route3`. This is for the report mailbox, not for sending.

## App settings

Set these in the deploy environment (DigitalOcean App Platform), with `DJANGO_DEBUG` off:

- `EMAIL_BACKEND=anymail.backends.resend.EmailBackend`
- `RESEND_API_KEY`: the key from step 7 of [Resend setup](#resend-setup). Set it as an encrypted environment variable in App Platform. It is required with this backend and DEBUG off.
- `DEFAULT_FROM_EMAIL=OPEN <noreply@mail.openpb.org>`. Required with DEBUG off. `SERVER_EMAIL` follows it.

Settings refuse to start when a required value is missing, and the error names the variable, not its value. To check the whole path, sign up with an address you control on a deployment that sends from `mail.openpb.org` and confirm the verification email arrives. In the received message's headers, `Authentication-Results` should show `dkim=pass` with `header.d=mail.openpb.org`, `spf=pass`, and `dmarc=pass`.
