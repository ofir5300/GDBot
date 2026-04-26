#!/usr/bin/env bash
set -euo pipefail

cd /home/rpi/gdbot

OLD=$(git rev-parse HEAD)
git fetch --quiet origin main
NEW=$(git rev-parse origin/main)

if [ "$OLD" = "$NEW" ]; then
    echo "Already up to date at $OLD"
    exit 0
fi

if ! git diff --quiet "$OLD" "$NEW" -- requirements.txt; then
    REQS_CHANGED=1
else
    REQS_CHANGED=0
fi

echo "Updating $OLD -> $NEW"
git reset --hard "$NEW"

if [ "$REQS_CHANGED" = "1" ]; then
    echo "requirements.txt changed, reinstalling deps"
    /home/rpi/gdbot/.venv/bin/pip install -r requirements.txt
fi

echo "Restarting gdbot.service"
sudo /bin/systemctl restart gdbot.service
