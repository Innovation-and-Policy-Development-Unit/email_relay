#!/bin/sh
# Routes the fake TLD ".mailpit.test" to the local mailpit container instead of
# attempting real MX delivery. This exists purely so local testing has a
# deterministic, always-reachable destination to prove Postfix + DKIM signing
# work correctly, independent of whether this network allows outbound port 25.
#
# Real domains are untouched and still go direct-to-MX as normal.
cat > /etc/postfix/transport <<'EOF'
mailpit.test    smtp:mailpit:1025
EOF
postmap lmdb:/etc/postfix/transport
postconf -e "transport_maps=lmdb:/etc/postfix/transport"
# reject_unknown_recipient_domain does a live DNS check on the recipient
# domain regardless of relay_domains; the exception is domains Postfix
# considers itself authoritative for. mydestination normally means "deliver
# locally", but the transport_maps entry above takes precedence and routes
# it to mailpit instead -- this makes the fake .test domain pass the
# sanity check without weakening it for any real domain.
postconf -e "mydestination=mailpit.test"
# mydestination normally requires the recipient to be a real local Unix
# user; mailpit.test isn't, so disable that check. Safe here because
# mydestination contains ONLY this fake test domain, not any real one.
postconf -e "local_recipient_maps="
