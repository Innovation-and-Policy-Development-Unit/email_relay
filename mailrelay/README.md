# mailrelay — self-hosted outbound MTA for SCDMS

Postfix + OpenDKIM, direct-to-MX (no third-party SMTP provider). Built and
tested locally in this folder; designed to be merged into SCDMS's real
`docker-compose.yml` once validated.

Image: `boky/postfix` (actively maintained, last built 2026-01-01 as of this
writing). Pinned by digest in `docker-compose.yml` for reproducibility —
see "Updating the image" below.

## How it's configured

- **Outbound only.** No inbound mail acceptance for a domain — this relay
  only sends. Listens on `25` and `587` (both are actual image defaults,
  restricted by `mynetworks` to RFC1918 + loopback, i.e. sibling containers
  only — not published to the host or internet).
- **Direct-to-MX.** No `RELAYHOST` is set, so Postfix looks up the
  recipient domain's MX records and delivers straight there.
- **DKIM signing via OpenDKIM**, milter-integrated with Postfix. Keypair is
  auto-generated on first start (`DKIM_AUTOGENERATE=1`) and persisted to
  `./dkim-keys/` so restarts don't silently invalidate your published DNS
  record.
- **TLS**: `smtp_tls_security_level=may` — opportunistic STARTTLS to
  receiving MX servers that offer it, plaintext fallback otherwise (direct
  delivery can't require TLS since not every receiver supports it).

## Local testing

1. `cp .env.example .env` and fill in your real sending domain (already
   defaulted to `psc.gov.vu` / `mail.psc.gov.vu` for this project).
2. `docker compose up -d`
3. Watch the first-boot logs for the generated DKIM key and DNS record:
   ```bash
   docker logs mailrelay | grep -A6 "DKIM keys have been generated"
   ```
4. Send a test message. mailrelay publishes no ports to the host, so run
   the test script from a container on the same compose network:
   ```bash
   docker run --rm --network mailrelay_mailnet \
     -v "$(pwd)/scripts:/scripts" python:3.12-slim \
     python /scripts/send_test_email.py someone@mailpit.test \
       --host mailrelay --port 25
   ```
   `*.mailpit.test` is a fake TLD that `postfix-init/10-transport.sh`
   routes to a local Mailpit container instead of attempting real MX
   delivery — this proves signing/queuing/delivery work correctly without
   depending on real internet reachability. Point it at any Mailpit
   reachable on the same Docker network as `mailpit:1025` (SCDMS's stack
   already runs one; attach with
   `docker network connect <scdms_app_network> mailrelay` for local testing,
   or just merge mailrelay into SCDMS's compose file directly and it
   resolves automatically).
5. Inspect the captured message in Mailpit's UI (`http://localhost:8025`)
   or its API (`/api/v1/message/<id>/raw`) and confirm the
   `DKIM-Signature:` header is present.
6. To also try real direct-to-MX delivery (likely to fail from a
   home/office network — that's expected, see below), point the script at
   a real address instead: `... send_test_email.py you@realdomain.com`.
   Check the result with `docker exec mailrelay postqueue -p`; if it's
   stuck, deferred, or "Connection refused" on port 25, that confirms this
   network blocks outbound 25 — informational, not a config bug.

### What we actually verified in this environment

Sent through mailrelay to the real SCDMS mailpit container. Raw captured
headers:

```
DKIM-Signature: v=1; a=rsa-sha256; c=relaxed/simple; d=psc.gov.vu; s=mail;
	t=1785299068; bh=vm8mnWlS+9aE7Bjmor5RYqIypmJBLd8b8UBU/NykppU=;
	h=Subject:From:To:Message-ID:Content-Type:MIME-Version:From:Sender:
	 To:CC:Subject:Message-Id:Date:MIME-Version:Content-Type:Reply-To;
	b=fn/WxP/biQ+5JRTnLAIDbnZCtChC7cdZyB305pA8ElYKVtlYBd0npuLDRWCkEo2Eh
	 QaaRkQe0Nc2kIhNPBPVJdPR0LDvA9yHwO8uMDJGZZkDsbQpVtZ4MhjXkCCsRHOXD7W
	 zafDOWBhmb3Zm9talJnMzrIlwAK2R1XWc86qU7CcS/1gVi7hd+5eaR36BoSZRlQoFn
	 bUc6/gv7zA5bqqZ++mkc473sGrF8+pRagZqqoFIREhr5mCCuOW0ct3cwfGv070MD56
	 qaP9jRcosxeditZlDTj8g2Fu5Y64Ocj6AjO3JDwPpUu+yph1yRc4pE3acf0GtSG77o
	 2V+BcsbTTiXpw==
```

Well-formed, correct domain (`d=`) and selector (`s=`), valid body hash
(`bh=`). Postfix's mail log also confirmed the signing step directly:

```
opendkim[...]: 442D16C6DB: DKIM-Signature field added (s=mail, d=psc.gov.vu)
postfix/smtp[...]: 442D16C6DB: to=<...>, relay=mailpit[...]:1025, ... status=sent
```

We also attempted real direct-to-MX delivery to a Gmail address. Postfix
correctly resolved Gmail's real MX (`alt4.gmail-smtp-in.l.google.com`) and
attempted delivery, but got `Connection refused` on port 25 — this
network blocks outbound port 25, exactly the class of problem this whole
project exists to route around on the production server. The config
itself is correct; only network reachability is missing here, as expected.

## Env vars / secrets

| Variable | Meaning | Secret? |
|---|---|---|
| `MAIL_DOMAIN` | Domain you send FROM | No |
| `MAIL_HOSTNAME` | HELO/EHLO hostname; **must match production PTR record** | No |
| `DKIM_SELECTOR` | DKIM selector (`<selector>._domainkey.<domain>`) | No |
| `ALLOWED_SENDER_DOMAINS` | Domains this relay accepts as MAIL FROM | No |
| *(none)* | The DKIM private key itself is the only real secret here | **Yes** |

The DKIM private key lives in `./dkim-keys/<domain>.private` — never commit
it (already gitignored). It's the one thing that must be backed up and
carried over to production untouched (regenerating it means republishing
DNS and losing signing continuity).

## DNS record to publish

From the local run above (selector `mail`, domain `psc.gov.vu` — regenerate
and re-copy this if you ever wipe `./dkim-keys/`):

```
mail._domainkey.psc.gov.vu.  IN  TXT  "v=DKIM1; h=sha256; k=rsa; s=email; p=MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvt6x5Pt4KkFo4RzIMjssJzZKZ5FpoIu+6o1vbfdqWldKndpOtqpPavPsXiEVIdm1V95Ih7UWFXLL9ebWZ0VoB1+69F09SWenfubDh5BFyHI/FtQLKkc2hRhU2aNqt69Ka++CZ4QNS8AZo7LM2QjniERjDkODHLRsCz5yJQMrhTbXUaQomdTaas7a+fm9tOKGzs5TPBa57RRVS1Fkq6HloA0aBj9pqRvvrkJuvRkNhiXwSU3vQcqRnw2jlljl5inCreaudV/gJcBLC0falGbkx3IuJ8lJ4/kR5PA5o0qponepDB4Kw+lQycOVVIyzjCfSqXSIZsYr/+fqGkGAZ/lqlwIDAQAB"
```

The exact text (with DNS-provider-friendly line splits) is also always
available at `./dkim-keys/psc.gov.vu.txt` after the container's first boot.

**This key was generated for local testing.** Generate a fresh one on the
production host (or copy this same keypair over, private key included, if
you want continuity) — see checklist below.

## Production deployment checklist

- [ ] **Persist `./dkim-keys/`** on the production host the same way (bind
      mount or named volume) — losing it means every previously-published
      DNS record goes stale.
- [ ] **PTR (reverse DNS)** on the server's public IP must resolve to
      `MAIL_HOSTNAME` (e.g. `mail.psc.gov.vu`). Most receiving MTAs
      (Gmail, Outlook) reject or heavily penalize mail from IPs with no
      matching PTR. This is set via your hosting provider/ISP, not DNS you
      control on your own domain.
- [ ] **SPF record** on `psc.gov.vu`:
      `v=spf1 ip4:<production-server-public-ip> -all`
      (or `mx` if the server's own MX matches its sending IP).
- [ ] **DMARC record** at `_dmarc.psc.gov.vu`, e.g. to start in monitor-only
      mode: `v=DMARC1; p=none; rua=mailto:dmarc-reports@psc.gov.vu`.
      Tighten to `p=quarantine`/`p=reject` once SPF+DKIM alignment is
      confirmed clean.
- [ ] **Confirm outbound TCP/25 is actually open** on the production
      network — the specific failure mode we designed around. Test with
      `nc -zv smtp.gmail.com 25` or similar from the production host before
      assuming this fixes anything.
- [ ] **DKIM key file permissions** — the "key data is not secure"
      warning seen locally is a Windows-bind-mount artifact; on the real
      Linux host confirm `/etc/opendkim/keys/*.private` is `0600`, owned by
      the container's `opendkim` user (uid 101 in this image).
- [ ] **Swap placeholder → real values** — `psc.gov.vu` is already the real
      domain here, so this is mostly about double-checking `MAIL_HOSTNAME`
      matches whatever hostname you actually get PTR-delegated for.
- [ ] **Pin the image** — this compose file pins `boky/postfix` by digest.
      Re-verify and update that digest periodically (`docker pull
      boky/postfix:latest` on a trusted machine, then `docker inspect
      --format '{{.RepoDigests}}'`), don't float on `:latest` in production.
- [ ] **External validation once DNS + PTR + SPF/DMARC are live**: send a
      message to `check-auth@verifier.port25.com` or run it through
      mail-tester.com and confirm SPF/DKIM/DMARC all show as pass and
      aligned. Not meaningfully testable from here since real MX delivery
      isn't reachable from this network.

## Merging into SCDMS's docker-compose.yml

Add this service. Note `mailpit` today is dual-homed on both `internal`
and `app` — that's specifically what lets `celery_beat` (which only joins
`internal`) reach it, the same way `celery_worker` is dual-homed for its
own outbound Anthropic API calls. `mailrelay` needs the same treatment:
`app` for real internet egress (`internal` is `internal: true`, no route
out), *and* `internal` so every service that currently reaches `mailpit`
keeps reaching mail the same way with no other wiring changes:

```yaml
  mailrelay:
    image: boky/postfix@sha256:aafc772384232497bed875e1eb66b4d3e54ba1ebc86e2e185a6dc1dbc48182ef
    hostname: ${MAIL_HOSTNAME:-mail.psc.gov.vu}
    restart: unless-stopped
    environment:
      ALLOWED_SENDER_DOMAINS: ${ALLOWED_SENDER_DOMAINS:-psc.gov.vu}
      DKIM_AUTOGENERATE: "1"
      DKIM_SELECTOR: ${DKIM_SELECTOR:-mail}
      POSTFIX_myhostname: ${MAIL_HOSTNAME:-mail.psc.gov.vu}
      POSTFIX_smtp_tls_security_level: may
    volumes:
      - mailrelay_dkim_keys:/etc/opendkim/keys
    networks:
      - internal   # so backend/celery_worker/celery_beat can all reach it, same as mailpit today
      - app        # real internet egress for direct-to-MX delivery
```

And add `mailrelay_dkim_keys` to the top-level `volumes:` block.

Then in `backend`, `celery_worker`, and `celery_beat`'s environment
(already generic `SMTP_*` vars, no code changes needed), swap:

```yaml
SMTP_HOST: ${SMTP_HOST:-mailrelay}   # was mailpit
SMTP_PORT: ${SMTP_PORT:-25}          # was 1025
SMTP_TLS: ${SMTP_TLS:-false}
SMTP_SSL: ${SMTP_SSL:-false}
DEFAULT_FROM_EMAIL: ${DEFAULT_FROM_EMAIL:-PSC Tracker <no-reply@psc.gov.vu>}
```

Since `mailrelay` doesn't require auth (trusted-network relay, same as
`mailpit` today), `SMTP_USER`/`SMTP_PASSWORD` stay empty — no change from
the current pattern.
