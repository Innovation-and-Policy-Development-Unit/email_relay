#!/usr/bin/env python3
"""Send a test message through Postal's SMTP endpoint with SMTP AUTH.

Usage:
    python send_test_email.py <to-address> --user psc/scdms --password <key> [--host smtp] [--port 25]
"""
import argparse
import smtplib
import sys
from email.message import EmailMessage
from email.utils import make_msgid


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("to_addr")
    parser.add_argument("--from-addr", default="no-reply@psc.gov.vu")
    parser.add_argument("--host", default="smtp")
    parser.add_argument("--port", type=int, default=25)
    parser.add_argument("--user", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--subject", default="Postal test message")
    args = parser.parse_args()

    msg = EmailMessage()
    msg["Subject"] = args.subject
    msg["From"] = args.from_addr
    msg["To"] = args.to_addr
    msg["Message-ID"] = make_msgid()
    msg.set_content(
        "This is a test message sent through the local Postal container "
        "to verify DKIM signing and SMTP submission before production deployment."
    )

    print(f"Connecting to {args.host}:{args.port} ...")
    with smtplib.SMTP(args.host, args.port, timeout=15) as smtp:
        smtp.set_debuglevel(1)
        smtp.ehlo()
        if smtp.has_extn("starttls"):
            smtp.starttls()
            smtp.ehlo()
        smtp.login(args.user, args.password)
        smtp.send_message(msg)

    print("\nMessage accepted by Postal.")
    print(f"Message-ID: {msg['Message-ID']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
