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
