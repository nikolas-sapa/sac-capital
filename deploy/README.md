# launchd Scheduling — macOS Paper-Trading Phase

Several launchd agents drive the paper-trading loop locally.

| Agent | Plist | Cadence |
|---|---|---|
| Polymarket scanner | `com.polymarketbot.runner.plist` | Disabled/no-op (`/usr/bin/true`) |
| Resolution poller | `com.polymarketbot.resolve.plist` | Nightly at 02:00 (`StartCalendarInterval`) |
| Equity mark/exits | `com.polymarketbot.equities.mark.plist` | Every 60 min (`StartInterval 3600`) |
| Equity scan/analysis | `com.polymarketbot.equities.scan.plist` | Daily 16:00, 17:00, and 22:30 local time (`StartCalendarInterval` array) |
| Nightly harness | `com.polymarketbot.nightly.plist` | Nightly at 02:30 (`StartCalendarInterval`) |

Both invoke the venv Python binary directly (no bare `uv`/`python` in PATH) and set `WorkingDirectory` so relative paths like `data/ledger.db` and `.env` resolve correctly.

---

## Prerequisites

1. `data/` directory must exist. The runner creates it on first use, but you can pre-create it:
   ```sh
   mkdir -p /Users/nikolassapalidis/sapa_fund/data
   ```
2. `.env` at the project root must contain real credentials for live runs (API key, private key, etc.). Without it the bot runs in dry-run/dummy mode only.

---

## Install

```sh
# Copy plists into the user LaunchAgents directory
cp deploy/com.polymarketbot.runner.plist  ~/Library/LaunchAgents/
cp deploy/com.polymarketbot.resolve.plist ~/Library/LaunchAgents/
cp deploy/com.polymarketbot.equities.mark.plist ~/Library/LaunchAgents/
cp deploy/com.polymarketbot.equities.scan.plist ~/Library/LaunchAgents/
cp deploy/com.polymarketbot.nightly.plist ~/Library/LaunchAgents/

# Load and enable both agents
launchctl load -w ~/Library/LaunchAgents/com.polymarketbot.runner.plist
launchctl load -w ~/Library/LaunchAgents/com.polymarketbot.resolve.plist
launchctl load -w ~/Library/LaunchAgents/com.polymarketbot.equities.mark.plist
launchctl load -w ~/Library/LaunchAgents/com.polymarketbot.equities.scan.plist
launchctl load -w ~/Library/LaunchAgents/com.polymarketbot.nightly.plist
```

Alternatively, symlink instead of copy (changes to the repo take effect on next reload):

```sh
ln -sf "$(pwd)/deploy/com.polymarketbot.runner.plist"  ~/Library/LaunchAgents/
ln -sf "$(pwd)/deploy/com.polymarketbot.resolve.plist" ~/Library/LaunchAgents/
ln -sf "$(pwd)/deploy/com.polymarketbot.equities.mark.plist" ~/Library/LaunchAgents/
ln -sf "$(pwd)/deploy/com.polymarketbot.equities.scan.plist" ~/Library/LaunchAgents/
ln -sf "$(pwd)/deploy/com.polymarketbot.nightly.plist" ~/Library/LaunchAgents/
```

---

## Manage

```sh
# Check whether agents are loaded
launchctl list | grep polymarketbot

# Unload (disable + stop)
launchctl unload -w ~/Library/LaunchAgents/com.polymarketbot.runner.plist
launchctl unload -w ~/Library/LaunchAgents/com.polymarketbot.resolve.plist
launchctl unload -w ~/Library/LaunchAgents/com.polymarketbot.equities.mark.plist
launchctl unload -w ~/Library/LaunchAgents/com.polymarketbot.equities.scan.plist
launchctl unload -w ~/Library/LaunchAgents/com.polymarketbot.nightly.plist

# Reload after editing a plist
launchctl unload ~/Library/LaunchAgents/com.polymarketbot.runner.plist
launchctl load -w ~/Library/LaunchAgents/com.polymarketbot.runner.plist

# Tail logs
tail -f /Users/nikolassapalidis/sapa_fund/data/runner.log
tail -f /Users/nikolassapalidis/sapa_fund/data/runner.err.log
tail -f /Users/nikolassapalidis/sapa_fund/data/equities_mark.log
tail -f /Users/nikolassapalidis/sapa_fund/data/equities_scan.log
tail -f /Users/nikolassapalidis/sapa_fund/data/nightly.log
tail -f /Users/nikolassapalidis/sapa_fund/data/resolve.log
tail -f /Users/nikolassapalidis/sapa_fund/data/resolve.err.log
```

---

## Tuning the scan cadence

Edit `StartInterval` in `com.polymarketbot.runner.plist` (seconds), then reload:

```sh
# e.g. change to 600 for 10-min cadence
# edit the plist, then:
launchctl unload ~/Library/LaunchAgents/com.polymarketbot.runner.plist
launchctl load -w ~/Library/LaunchAgents/com.polymarketbot.runner.plist
```

---

## NOTE: VPS + systemd

systemd unit files for a VPS/Linux deployment are **not included here**. They will be added at go-live when a persistent server is provisioned. Do NOT attempt to host this on Hugging Face free Spaces — ephemeral storage wipes `data/ledger.db` on every container restart, destroying the paper-trading ledger.

---

## NOTE: Geo-block — VPN required for live scans

This machine is geo-blocked from Polymarket's API. launchd will load and fire the agents normally, but every scan that attempts a live network call will fail with a connection error until the machine is on a VPN or in an unrestricted region.

**Step 3 (unattended fill check)** — confirming that a launchd-triggered scan lands a paper fill — is **BLOCKED pending VPN access**. Do not attempt it from this machine without a VPN.
