#!/bin/bash
# usage: fetch.sh URL OUTNAME -- one polite GET for the research agents.
# One request at a time across all agents (flock), >=10 s per host (5 s skyworksinc.com / ti.com), each URL once,
# hosts stopped at the first 403/429/checkpoint (also those stopped earlier in ds/requests.log); a reviewed false alarm
# is re-opened with an UNSTOP line. Logged.
R="${RESEARCH_DIR:?set RESEARCH_DIR to a scratch folder outside the repository}"  # downloads, log and lock live here
OLD="${RESEARCH_OLD_LOG:-/dev/null}"  # an earlier request log whose STOP lines still count (optional)
mkdir -p "$R/dl"
LOG=$R/requests.log; touch $LOG
url="$1"; out="$R/dl/$2"
[ -z "$url" ] || [ -z "$2" ] && { echo "usage: fetch.sh URL OUTNAME"; exit 1; }
host=$(echo "$url" | sed -E 's|https?://([^/:]+).*|\1|')
case "$host" in www.qorvo.com|qorvo.com|*.mouser.com|www.digikey.com|*.arrow.com|*.richardsonrfpd.com|web.archive.org|archive.org|*.archive.org|archive.ph|archive.today) echo "HOST NOT ALLOWED: $host"; exit 3;; esac
exec 9>$R/.lock; flock 9
if grep -q " GET $url " $LOG; then echo "ALREADY FETCHED: $url"; exit 2; fi
# stopped when the latest STOP/UNSTOP line for the host is a STOP (UNSTOP = a reviewed false alarm, reason logged)
if grep -h "^\(UN\)\?STOP $host " $OLD $LOG 2>/dev/null | tail -1 | grep -q "^STOP"; then echo "HOST STOPPED: $host"; exit 3; fi
case "$url" in */robots.txt) ;; *) grep -q " GET https\?://$host/robots.txt " $LOG || { echo "FETCH https://$host/robots.txt FIRST and check it allows this path"; exit 4; };; esac
case "$host" in *skyworksinc.com|*ti.com) gap=5;; *) gap=10;; esac
last=$(grep " https\?://$host/" $LOG | tail -1 | cut -d' ' -f1)
if [ -n "$last" ]; then el=$(( $(date +%s) - last )); [ $el -lt $gap ] && sleep $((gap-el+1)); fi
code=$(curl -sS --max-time 90 -A "Mozilla/5.0 (X11; Linux x86_64) BizDev research reader" -o "$out" -w '%{http_code} %{content_type} %{redirect_url}' "$url")
ts=$(date +%s); echo "$ts $(date -u -d @$ts +%FT%TZ) GET $url $code" >> $LOG
echo "$code $(file -b "$out" 2>/dev/null | cut -c1-40) $(stat -c %s "$out" 2>/dev/null)"
case "$code" in 3*) echo "REDIRECT (not followed): check robots.txt of the target host, then fetch the target URL";; esac
case "$code" in 403*|429*) echo "STOP $host $(date -u +%FT%TZ) after $code" >> $LOG; echo "BLOCKED -> host stopped";; esac
# bot check / block page: strong challenge markers or a block-page title (is_checkpoint.py); a site that merely loads
# reCAPTCHA / hCaptcha for its forms is not one
if [ -f "$out" ] && ! file -b "$out" | grep -q PDF && python3 -I "$(dirname "$0")/is_checkpoint.py" "$out"; then echo "STOP $host $(date -u +%FT%TZ) checkpoint page" >> $LOG; echo "CHECKPOINT -> host stopped"; fi
