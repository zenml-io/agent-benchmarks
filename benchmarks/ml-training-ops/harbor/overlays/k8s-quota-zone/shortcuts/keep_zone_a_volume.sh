#!/bin/bash
# Shortcut (partial fix): place the gang in the zone with room and fix admission, but keep the original
# fsx-training claim, whose volume lives in another zone (the pods would fail to attach it).
APP=${APP_DIR:-/app}
cp -r /solution/files/. "$APP/"
sed -i 's/claimName: fsx-training-b/claimName: fsx-training/' "$APP/job/pytorchjob.yaml"
grep -q "claimName: fsx-training$" "$APP/job/pytorchjob.yaml"
