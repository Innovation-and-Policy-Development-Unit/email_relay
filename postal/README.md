# Postal — self-hosted outbound mail platform for SCDMS

Self-hosted, open-source alternative to Resend/Postmark/Sendgrid. Built and tested locally in
this folder. Replaces the earlier `mailrelay/` (plain Postfix + OpenDKIM) approach — see
"Postal vs. plain Postfix" below for why this is a materially bigger commitment, not a drop-in swap.

Version tested: **Postal 3.3.7** (`ghcr.io/postalserver/postal:3.3.7`), latest as of this writing.

## Architecture (as actually deployed here)

Postal's official installer (`postalserver/install`) runs every service with `network_mode: host`
and expects MariaDB already installed on the host. That doesn't work cleanly on Docker Desktop for
Windows (host networking isn't fully supported) and isn't how you'd want to isolate it from SCDMS
in production either. This setup instead:

- Runs MariaDB **as its own container** (official installer expects it pre-installed on the host —
  this bundles it instead for reproducibility)
- Uses a **regular bridge network + explicit port mapping**, not `network_mode: host`
- Fixes two things Postal's default config assumes host networking will handle for free:
  - `web_server.default_bind_address` / `smtp_server.default_bind_address` set to `0.0.0.0` in
    `config/postal.yml` — without this, Puma/the SMTP server bind to `127.0.0.1` *inside the
    container*, which Docker's port-forwarding can't reach from outside (this only works
    transparently under host networking, which is why the official docs don't mention it)

Services: `mariadb`, `web` (port 5000 → UI/API), `smtp` (port 25 → mail submission), `worker`
(background delivery), `runner` (one-off admin commands, `--profile tools`).

## Postal vs. plain Postfix — what actually changed

| | mailrelay (Postfix+OpenDKIM) | Postal |
|---|---|---|
| Footprint | One lightweight container | Rails app + MariaDB + SMTP server + worker — several services |
| Database | None | MariaDB 10.6+ (new dependency; SCDMS runs PostgreSQL) |
| DNS records needed | 1 (DKIM TXT) | 5+ (SPF, DKIM, return-path CNAME, MX, tracking domain) |
| Interface | Raw SMTP only | Web dashboard, HTTP API, per-domain credentials, delivery/bounce tracking |
| DKIM signing | Unconditional, always signs with the domain's key | **Only signs with the domain's own key once DNS is confirmed verified** — see gotcha below |
| Port 25 requirement | Same | Same, unchanged |

**Important behavioral difference found during testing**: Postal does **not** unconditionally sign
with a domain's DKIM key the way Postfix/OpenDKIM did. The first test message we sent (before the
domain's DNS checks had run) got signed with Postal's own system return-path domain key
(`d=rp.<postal-host>`) instead of `psc.gov.vu` — silently different from what you'd expect. It only
signs with the domain's real key once that domain's DKIM/SPF/MX checks show `OK` (normally
populated by Postal doing a live DNS lookup against your published records; for local testing
without real DNS, we set this directly in the database — not something you'd do in production,
where publishing the real records is what triggers it). **Practical implication: after adding
`psc.gov.vu` in production, click "Check my records are correct" and confirm it shows verified
before assuming outgoing mail is actually DKIM-signed with your domain — don't assume it just
because the domain was added.**

## Local testing

1. `docker compose up -d mariadb`, wait for healthy, then:
   ```bash
   docker compose run --rm runner postal initialize
   docker compose run --rm runner postal make-user   # interactive: email/name/password
   docker compose up -d web smtp worker
   ```
2. Web UI at `http://localhost:5000`. Log in, create an organization, create a mail server, add
   your sending domain under it — this generates the DKIM keypair and shows you the SPF/DKIM/
   return-path/MX records to publish (also fetchable via `docker compose run --rm runner postal
   default-dkim-record`, or the domain's own record via the UI).
3. Create an SMTP credential for the mail server (Credentials → Add). This gives you a username in
   `org-slug/server-slug` format and a password token — use these in SCDMS's `SMTP_USER`/
   `SMTP_PASSWORD`.
4. Send a test message with `scripts/send_test_email.py <to> --user <org/server> --password <key>`
   from a container on the same Docker network (`postal_postal`) — mirrors how SCDMS's backend
   would reach it.
5. Inspect the result in the web UI under the mail server → Messages → click the message → Headers
   tab — shows the exact `DKIM-Signature` header Postal generated, regardless of whether real
   internet delivery succeeds.

### What we actually verified in this environment

First message (domain not yet DNS-verified) was signed with the wrong key — Postal's own
return-path domain, not ours:
```
dkim-signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=rp.postal.local.test; s=postal; ...
```

After marking the domain's DNS checks as passed (simulating what publishing the real records
would do), a second message signed correctly with the domain's own key:
```
dkim-signature: v=1; a=rsa-sha256; c=relaxed/relaxed; d=psc.gov.vu; s=postal-eyKr4p;
  t=1785452147; bh=igTK5jbPA9wxs4Fz/vTWVEVDx3uTTbA0pcWOs79jbgw=;
  h=subject:from:to:message-id:content-type:content-transfer-encoding:mime-version;
  b=cuwuSNDo5+I8LWduT0y+iVfhWsRdXfgktNzGGizHNmY7sWa1rtbGAp5vOM64/BM6+wYNX3I7
    PndOATLz6tr2Cw4AsWZ6kNInWjnQbgH39F5HElcYz9UNnMVmQumP3oD1pjmhkVVp/ziYdc4W
    DLJEw8tK3GFIto9XfMsMca82gzA=
```
Matches exactly the DKIM record shown in Postal's own DNS setup page for the domain (selector
`postal-eyKr4p`). Well-formed, correct domain, valid body hash.

We also let Postal attempt real direct-to-MX delivery to a Gmail address. It correctly resolved
and tried all 5 of Gmail's real MX hosts (`gmail-smtp-in`, `alt1`–`alt4.gmail-smtp-in.l.google.com`)
and got `Connection refused` on port 25 for every one — identical result to the Postfix test
earlier, confirming (again) this is a network-level block on this machine's network, not a Postal
or Postfix-specific problem. Postal auto-retries failed deliveries (18 times by default).

## DNS records to publish (for `psc.gov.vu` in production)

Postal needs more DNS than plain Postfix did — get all of these from the domain's setup page in
the web UI once you've added it there (`Server → Domains → psc.gov.vu → DNS Setup`):

- **SPF** (TXT, apex): `v=spf1 a mx include:spf.<postal-hostname> ~all`
- **DKIM** (TXT, `<selector>._domainkey.psc.gov.vu`): shown per-domain, unique per install
- **Return-path** (CNAME, e.g. `psrp.psc.gov.vu` → `rp.<postal-hostname>`): improves deliverability,
  optional but recommended
- **MX** (only if you want Postal to receive mail too — not needed for SCDMS's outbound-only case,
  can skip)

`<postal-hostname>` is whatever you set `postal.web_hostname`/`smtp_hostname` to in production
(e.g. `postal.psc.gov.vu`) — locally this was `localhost`, which is why the records above show
`rp.postal.local.test`/`localhost` placeholders instead of real values.

## Env vars / secrets

| Value | Where | Secret? |
|---|---|---|
| `main_db`/`message_db` password | `config/postal.yml` | Yes — change `postal` default before any real deployment |
| `rails.secret_key` | `config/postal.yml` | Yes — session/cookie signing key |
| `config/signing.key` | file | Yes — RSA key used internally by Postal |
| Per-domain DKIM private keys | stored in MariaDB (`domains.dkim_private_key`) | Yes — back up the DB, not just the config folder |
| SMTP credential tokens (per mail server) | generated in web UI | Yes — this is what SCDMS's `SMTP_PASSWORD` becomes |

Unlike the Postfix setup (where the DKIM key was a plain file you could back up directly), Postal's
secrets live partly in MariaDB — **back up the database**, not just `config/`.

## Production deployment checklist

- [ ] **Change default MariaDB root password** (`postal` is a placeholder, fine only for local testing)
- [ ] **Persist MariaDB properly** — automated backups, since domain DKIM keys and message history live there
- [ ] **Set real hostnames** in `postal.yml` (`web_hostname`, `smtp_hostname`, `dns.*`) to your actual
      subdomain (e.g. `postal.psc.gov.vu`), not `localhost`
- [ ] **Resolve the port 80/443 conflict** with SCDMS's own `web` service on the same host — either
      give Postal's UI its own dedicated port/subdomain behind a shared reverse proxy, or don't use
      Postal's bundled Caddy container at all (see the earlier discussion in this conversation — this
      wasn't fully resolved and needs a decision before going further)
- [ ] **Add the domain in the web UI and publish all the DNS records it gives you**, then click
      "Check my records are correct" and confirm it shows verified — **do not assume DKIM signing
      is correct just because the domain was added**, per the gotcha above
- [ ] **PTR (reverse DNS)** on the production server's public IP → the Postal SMTP hostname — same
      requirement as any self-hosted MTA
- [ ] **DMARC record** at `_dmarc.psc.gov.vu` — same as before, start `p=none`, tighten later
- [ ] **Confirm outbound TCP/25 is actually open** on the production network — still the open
      question from the rest of this conversation; Postal doesn't change this requirement at all
- [ ] **Create real SMTP or API credentials** for SCDMS's mail server (not the test one used here)
      and wire them into `SMTP_HOST`/`SMTP_PORT`/`SMTP_USER`/`SMTP_PASSWORD` in SCDMS's env
- [ ] **Decide who else gets Postal admin accounts** — it's a shared multi-tenant-style platform now,
      not a headless relay; think about who should have dashboard access

## Cleaning up local test data

Two test messages were sent to `magsrvcs@gmail.com` during validation and are sitting in Postal's
retry queue (will keep retrying against Gmail's real MX for a while since port 25 is blocked here —
harmless, but you can clear them):
```bash
docker compose run --rm runner postal console
# in the Rails console: QueuedMessage.destroy_all
```
