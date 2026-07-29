#!/usr/bin/env python3
"""Send a test message through mailrelay and print what happened.

Run from a container attached to the mailrelay `mailnet` network (mailrelay
publishes no ports to the host, so this won't work from the host directly --
see README for how to run it via `docker compose run`).

Usage:
    python send_test_email.py <to-address> [--host mailrelay] [--port 25]
"""
import argparse
import smtplib
import sys
from email.message import EmailMessage
from email.utils import make_msgid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("to_addr", help="Recipient, e.g. someone@mailpit.test")
    parser.add_argument("--from-addr", default="no-reply@psc.gov.vu")
    parser.add_argument("--host", default="mailrelay")
    parser.add_argument("--port", type=int, default=25)
    parser.add_argument("--subject", default="mailrelay test message")
    args = parser.parse_args()

    msg = EmailMessage()
    msg["Subject"] = args.subject
    msg["From"] = args.from_addr
    msg["To"] = args.to_addr
    msg["Message-ID"] = make_msgid()
    msg.set_content(
        "This is a test message sent through the local mailrelay (Postfix + "
        "OpenDKIM) container to verify DKIM signing before production deployment."
    )

    print(f"Connecting to {args.host}:{args.port} ...")
    with smtplib.SMTP(args.host, args.port, timeout=15) as smtp:
        smtp.set_debuglevel(1)
        smtp.send_message(msg)

    print("\nMessage accepted by mailrelay for delivery.")
    print(f"Message-ID: {msg['Message-ID']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
