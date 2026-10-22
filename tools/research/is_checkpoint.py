"""Exit 0 when a downloaded page is a bot check / block page, 1 when it is a normal page.

Strong signs (any one is enough): the challenge pages of Cloudflare, Incapsula, PerimeterX, DDoS-Guard, Akamai and
the like, or a page title that says so. A mere mention of "captcha" (sites load reCAPTCHA / hCaptcha scripts for their
forms) only counts on a page with almost no readable text.
Usage: python3 -I is_checkpoint.py FILE
"""

import re
import sys

raw = open(sys.argv[1], "rb").read(400000).decode("utf-8", "replace")
low = raw.lower()
title = (re.search(r"<title[^>]*>(.*?)</title>", raw, re.I | re.S) or [None, ""])[1].strip().lower()
STRONG = ("cf-chl", "cf_chl_opt", "_incapsula_resource", "request unsuccessful. incapsula",
          "px-captcha", "perimeterx", "ddos-guard", "verify you are human", "are you a robot", "automation tools",
          "unusual traffic from your computer", "client challenge", "please enable js and disable any ad blocker")
TITLES = ("just a moment", "attention required", "access denied", "client challenge", "captcha", "security check",
          "are you a robot", "bot verification", "request rejected", "pardon our interruption")
if any(s in low for s in STRONG) or any(t in title for t in TITLES):
    sys.exit(0)
text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", raw)))
# weak signs (reCAPTCHA / hCaptcha for forms, Cloudflare's passive challenge-platform script) count only on an almost
# empty page
if ("captcha" in low or "challenge-platform" in low) and len(text.strip()) < 1500:
    sys.exit(0)
sys.exit(1)
