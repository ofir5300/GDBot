# GDBot Raspberry Pi deploy

Pull-based deploy: a systemd timer on the Pi runs `update.sh`, which fetches `origin/main`, fast-forwards via `git reset --hard`, reinstalls deps if `requirements.txt` changed, and restarts the bot service.

- **Service**: `gdbot.service` — runs `python -m gdbot.main` under user `rpi`
- **Updater**: `gdbot-update.service` (oneshot) + `gdbot-update.timer` (daily + 2 min after boot, with `Persistent=true` so missed runs catch up)
- **Manual deploy**: `sudo systemctl start gdbot-update.service`

## One-time bootstrap on the Pi

```bash
sudo apt update && sudo apt install -y git python3-venv

git clone https://github.com/ofir5300/gdbot.git /home/rpi/gdbot
cd /home/rpi/gdbot

python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# Env file lives outside the repo so `git reset --hard` can never wipe it
cat > /home/rpi/gdbot.env <<'EOF'
TELEGRAM_BOT_TOKEN=REPLACE_ME
EOF
chmod 600 /home/rpi/gdbot.env

# Allow the updater to restart the bot without a sudo password
echo 'rpi ALL=(root) NOPASSWD: /bin/systemctl restart gdbot.service' \
  | sudo tee /etc/sudoers.d/gdbot
sudo chmod 440 /etc/sudoers.d/gdbot

# Install systemd units
sudo cp deploy/gdbot.service deploy/gdbot-update.service deploy/gdbot-update.timer \
  /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gdbot.service gdbot-update.timer

# Optional: handy alias for forcing an immediate deploy
echo "alias gdbot-deploy='sudo systemctl start gdbot-update.service && journalctl -u gdbot-update -n 30 --no-pager'" >> ~/.bashrc
```

## Verify

```bash
systemctl status gdbot
journalctl -u gdbot -f          # bot logs
systemctl list-timers | grep gdbot
sudo systemctl start gdbot-update.service   # force deploy now
journalctl -u gdbot-update -n 30 --no-pager
```

The SQLite DB at `gdbot/data/gdbot.db` is gitignored, so it survives `git reset --hard`. The `.env` is also gitignored, but is kept at `/home/rpi/gdbot.env` to be fully decoupled from the checkout.
