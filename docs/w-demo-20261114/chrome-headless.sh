#!/bin/sh
# Probe harness: real Chrome, headless, no outside network (every name except 127.0.0.1 fails to resolve).
exec /opt/google/chrome/chrome --headless=new --disable-gpu --host-resolver-rules="MAP * ~NOTFOUND , EXCLUDE 127.0.0.1" "$@"
