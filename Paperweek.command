#!/usr/bin/env bash
cd "$(dirname "$0")" || exit 1
printf '\nPaperweek\n  1  Demo\n  2  Google calendar\n  3  Connect / choose calendars\n\n'
read -r -p 'Choose [1]: ' choice
case "$choice" in
  2) bash run.sh google ;;
  3) bash run.sh connect ;;
  *) bash run.sh demo ;;
esac
status=$?
if [[ "$status" != 0 ]]; then read -r -p 'Press Return to close. ' _; fi
exit "$status"
