#!/bin/bash
set -euo pipefail

shopt -s nullglob

for f in /etc/systemd/system/lawnberry-*.service; do
  echo "== $f =="
  awk '
    BEGIN{in=0}
    /^\[Install\]/{in=1; next}
    /^\[.*\]/{in=0}
    in && /(Protect|Restrict|SystemCall|UMask|NoNewPrivileges|PrivateTmp|ProtectKernel|ReadWritePaths|DeviceAllow|LockPersonality)/ {
      print "  [Install] has:", $0
    }
  ' "$f"
done

echo "Done. If any lines were reported under [Install], fix the unit by moving them into [Service] and run: sudo systemctl daemon-reload"
