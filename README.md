# Ghost Control Plane (Safe MVP)

A local, **safe-by-default** tuning layer for your machine.

- Observes system health/perf in snapshots
- Recommends low-risk improvements
- Applies only reversible runtime profiles (unless you explicitly extend it)
- Keeps an audit trail

## Design goals

1. **No bricking**: no bootloader/kernel/partition edits.
2. **Reversible**: profile changes are runtime-only by default.
3. **Measured**: recommendations come from collected snapshots.
4. **Auditable**: every action and recommendation is logged.

## Project layout

```text
ghost-control-plane/
  README.md
  config/default.toml
  scripts/
    gcp_snapshot.py      # collect one JSON snapshot
    gcp_recommend.py     # analyze snapshots + suggest actions
    gcp_profile.py       # safe runtime profiles + v1.1 verification/rollback
    gcp_guard.py         # read-only health score from recent snapshots
    gcp_scene.py         # scene-based profile switching (safe)
    gcp_autopilot.py     # safe profile decision engine
    gcp_checkpoint.py    # create/restore local safety checkpoints
    gcp_selfheal.py      # safe self-healing actions
    gcp_soc.py           # read-only drift intelligence + severity
    gcp_repro.py         # export/apply Ghost runtime state as code
    gcp_mesh.py          # AI mesh router + policy gate
    gcp_audio.py         # PipeWire runtime audio profiles + rollback
    gcp_network.py       # DNS network profiles + rollback
    gcp_backup.py        # encrypted backup run/verify + retention
    gcp_qos.py           # network QoS tuning (fq_codel)
    gcp_cache.py         # build cache acceleration setup
    gcp_battle.py        # emergency battle commands
    gcp_dashboard.py     # system dashboard
    gcp_cognition.py     # project cognition layer
  systemd/user/
    gcp-snapshot.service
    gcp-snapshot.timer
    gcp-autopilot.service
    gcp-autopilot.timer
```

## Quick start

```bash
cd ~/\.openclaw/workspace/ghost-control-plane
python scripts/gcp_snapshot.py
python scripts/gcp_recommend.py --last 48
python scripts/gcp_profile.py --list
python scripts/gcp_profile.py --profile balanced --dry-run
python scripts/gcp_guard.py --last 6
python scripts/gcp_scene.py --list
python scripts/gcp_scene.py --scene code --dry-run
python scripts/gcp_autopilot.py --dry-run
python scripts/gcp_selfheal.py --dry-run
python scripts/gcp_checkpoint.py --create --label manual
python scripts/gcp_soc.py --snapshot
python scripts/gcp_soc.py --baseline set-latest
python scripts/gcp_soc.py --diff
python scripts/gcp_repro.py --export
python scripts/gcp_repro.py --dry-run
python scripts/gcp_mesh.py --task "check drift" --run
python scripts/gcp_mesh.py --task "set code performance" --apply --allow-apply --run
./scripts/gcp install
~/.local/bin/gcp status
```

## Enable periodic snapshots (user-level timer)

```bash
mkdir -p ~/.config/systemd/user
cp systemd/user/gcp-snapshot.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gcp-snapshot.timer
systemctl --user list-timers | rg gcp-snapshot
```

## Profiles in this MVP

- `balanced`
- `focus`
- `performance`
- `battery`

Current implementation uses only **safe runtime toggles** (e.g., `powerprofilesctl` if available).
No kernel params, no filesystem layout edits, no boot-chain mutations.

## v1.1 profile apply safety checks and rollback

When a profile is applied (`--apply`), `gcp_profile.py` now:

1. Captures pre-change power profile (`powerprofilesctl get`) when available.
2. Applies selected safe runtime profile steps.
3. Verifies post-apply safety over a window (default `30` seconds):
   - CPU temp from `sensors` (if available), threshold `MAX_CPU_TEMP_C=90.0`
   - Journal priority `0..3` line count, threshold `MAX_P0P3_LINES=10`
4. If regression is detected and rollback is enabled, restores prior power profile and logs rollback.
5. Logs success or rollback events in `~/.local/share/ghost-control-plane/actions.log`.

Missing tools (`sensors`, `powerprofilesctl`, `journalctl`) are handled gracefully and checks are skipped rather than crashing.

### New CLI flags

- `--verify-seconds <int>`: verification window after apply (default: `30`)
- `--rollback-on-regression`: enable rollback on detected regression (default behavior)
- `--no-rollback-on-regression`: disable rollback on detected regression

### Example commands

```bash
# Safe preview (no changes)
python scripts/gcp_profile.py --profile balanced --dry-run

# Apply with default verification window (30s) and rollback enabled
python scripts/gcp_profile.py --profile balanced --apply

# Apply with a custom verification window
python scripts/gcp_profile.py --profile balanced --apply --verify-seconds 45

# Apply but keep changes even if regression is detected
python scripts/gcp_profile.py --profile balanced --apply --no-rollback-on-regression
```

## Guard utility (read-only)

Use `gcp_guard.py` to score recent snapshot health (0-100) using temps, recent errors, and failed units:

```bash
python scripts/gcp_guard.py --last 6
```

Output is compact and reports `PASS`/`WARN`. This script does not write any files.

## Scene system + autopilot (safe foundation)

### Scenes

`gcp_scene.py` maps high-level workflows to bundled power/audio/network profiles:

- `game` -> power: performance, audio: lowlatency, network: latency
- `code` -> power: performance, audio: balanced, network: latency
- `focus` -> power: balanced, audio: balanced, network: latency
- `travel` -> power: battery, audio: powersave, network: isp-auto
- `stream` -> power: balanced, audio: lowlatency, network: latency

Examples:

```bash
python scripts/gcp_scene.py --list
python scripts/gcp_scene.py --scene game --dry-run
python scripts/gcp_scene.py --scene focus --apply
```

### Autopilot

`gcp_autopilot.py` makes a conservative profile decision from:

- AC online status
- battery percentage
- CPU temperature (if available)

By default, use dry-run. Apply is explicit:

```bash
python scripts/gcp_autopilot.py --dry-run
python scripts/gcp_autopilot.py --apply --verify-seconds 15
```

### Optional timer

A user-level timer is included to run **dry-run** autopilot checks every 15 minutes:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/user/gcp-autopilot.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gcp-autopilot.timer
```

This timer does not apply changes by itself (safe monitoring mode).

## Self-healing + rollback checkpoints (Layer 2)

### Checkpoints

Create/restore checkpoints for safe runtime state:

```bash
python scripts/gcp_checkpoint.py --create --label pre-change
python scripts/gcp_checkpoint.py --list
python scripts/gcp_checkpoint.py --restore ~/.local/share/ghost-control-plane/checkpoints/<file>.json
```

Checkpoint data includes current power profile and user timer states.

### Self-healing

`gcp_selfheal.py` performs **safe**, reversible fixes:

- ensure required directories exist
- ensure Ghost scripts are executable
- sync/update user systemd units from repo
- enable/start Ghost timers when missing

Dry-run first (recommended):

```bash
python scripts/gcp_selfheal.py --dry-run
```

Apply fixes (creates a checkpoint first):

```bash
python scripts/gcp_selfheal.py --apply
```

Optional daily dry-run scan timer:

```bash
cp systemd/user/gcp-selfheal.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gcp-selfheal.timer
```

## SOC drift intelligence (Layer 3)

`gcp_soc.py` creates read-only snapshots of:

- listeners (`ss -ltnup`)
- UFW rule lines
- selected service state lines
- pending updates (pacman/AUR/brew)

Then compares latest snapshot against a baseline and emits a severity (`INFO`/`WARN`).

### Workflow

```bash
python scripts/gcp_soc.py --snapshot
python scripts/gcp_soc.py --baseline set-latest
python scripts/gcp_soc.py --report   # snapshot + diff
```

### Optional daily SOC timer

```bash
cp systemd/user/gcp-soc-report.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gcp-soc-report.timer
```

## Reproducible runtime state (Layer 4)

`gcp_repro.py` captures and reapplies Ghost runtime state as code.

### What it exports

- current power profile
- timer enabled/active state for Ghost timers
- user systemd unit file contents + hashes

Export writes into `state/`:

```bash
python scripts/gcp_repro.py --export
```

Preview apply plan (no changes):

```bash
python scripts/gcp_repro.py --dry-run
```

Apply manifest:

```bash
python scripts/gcp_repro.py --apply
```

Safety behavior:
- no unit deletions
- no kernel/bootloader/filesystem mutation
- scope is user-level Ghost runtime state

## AI Mesh Orchestrator (Layer 5)

`gcp_mesh.py` routes freeform tasks into safe Ghost operations with a policy gate.

### Intents

- `health`, `drift`, `snapshot` (read-only)
- `stabilize`, `autopilot`, `scene`, `repro` (apply-capable with explicit gate)
- `ops-round` (bundle: guard + soc + autopilot dry-run)

### Policy gate

Config: `config/mesh-policy.json`

- safe-by-default
- apply disabled by default
- apply requires both:
  - `--apply`
  - `--allow-apply`
  - intent marked apply-capable in policy

Examples:

```bash
# Read-only route+run
python scripts/gcp_mesh.py --task "check network drift" --run

# Apply-capable route (explicit gate required)
python scripts/gcp_mesh.py --task "set code performance" --apply --allow-apply --run
```

### Optional mesh ops timer

```bash
cp systemd/user/gcp-mesh-ops.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gcp-mesh-ops.timer
```

This runs an hourly read-only ops round.

## Unified `gcp` command

Install launcher:

```bash
./scripts/gcp install
```

Examples:

```bash
gcp status
gcp guard --last 12
gcp soc report
gcp scene code --apply
gcp selfheal --dry-run
gcp repro export
gcp mesh --task "check network drift" --run
gcp audio status
gcp audio lowlatency --apply
gcp network status
gcp network latency --apply
gcp backup status
gcp backup init-passphrase
gcp backup run --apply
gcp backup verify
```

## Backup + DR (Layer 7)

Encrypted backup module:

```bash
gcp backup status
gcp backup init-passphrase
gcp backup run --apply
gcp backup verify
```

- Config: `config/backup.json` (override via `~/.config/ghost-control-plane/backup.json`)
- Encrypted archives: `~/Backups/ghost-control-plane/*.tar.zst.gpg`
- Retention: keep last 14 by default

Daily backup timer/unit are included:

```bash
cp systemd/user/gcp-backup.* ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now gcp-backup.timer
```

## Audio + Network tuning (Layer 6)

### Audio profiles (PipeWire runtime)

```bash
gcp audio status
gcp audio balanced --apply
gcp audio lowlatency --apply
gcp audio studio --apply
gcp audio powersave --apply
gcp audio rollback --apply
```

Profiles adjust runtime `clock.force-quantum` / `clock.force-rate` and keep rollback state in `state/audio-last.json`.

### Network DNS profiles (active connection)

```bash
gcp network status
gcp network isp-auto --apply
gcp network latency --apply
gcp network privacy --apply
gcp network rollback --apply
```

Profiles are reversible and keep rollback state in `state/network-last.json`.

## Data location

Snapshots and logs are written under:

```text
~/.local/share/ghost-control-plane/
  snapshots/
  actions.log
```

## Network QoS tuning (Layer 8)

`gcp_qos.py` tunes `fq_codel` for your default interface:

```bash
gcp qos status
gcp qos default --apply
gcp qos gaming --apply
gcp qos streaming --apply
gcp qos rollback
```

Profiles:
- `default`: standard fq_codel
- `gaming`: lower target/interval for responsiveness
- `streaming`: balanced for throughput

Requires sudo for `tc` commands.

## Build cache acceleration (Layer 9)

`gcp_cache.py` sets up compiler/caching wrappers:

```bash
gcp cache status
gcp cache apply
```

Sets up:
- ccache (C/C++ compiler caching)
- sccache (Rust/Cargo caching)
- pnpm store location
- pip cache directory

## Battle mode (Layer 10)

`gcp_battle.py` emergency response commands:

```bash
gcp battle network-reset    # flush DNS, restart network
gcp battle kill-stuck       # kill high-CPU zombies
gcp battle emergency-perf   # force performance profile
gcp battle memory-free      # clear caches
gcp battle fix-wifi         # toggle Wi-Fi radio
gcp battle all              # run reset + perf + memory
```

## Dashboard (Layer 11)

`gcp_dashboard.py` system overview:

```bash
gcp dashboard              # one-shot snapshot
gcp dashboard --live       # auto-refresh every 5s
```

Shows health, power/audio/network state, temps, active timers, quick commands.

## Project Cognition (Layer 12)

`gcp_cognition.py` auto-detects project types and suggests activation:

```bash
gcp cognition detect                    # detect project type
gcp cognition analyze                   # full project analysis
gcp cognition analyze /path/to/project  # analyze specific path
gcp cognition auto-activate             # auto-activate venv/env
```

Supported project types:
- **Python**: detects venv, requirements.txt, pyproject.toml
- **Node**: detects package.json, pnpm/yarn/npm
- **Rust**: detects Cargo.toml
- **Go**: detects go.mod

Fish integration (already active):
- Automatically detects when you `cd` into a project
- Shows `[Ghost] <type> project detected` notification
- Run `gcp-auto` to auto-activate environment

## Next phase ideas

- Before/after scorecards per change
- Workload-aware mode switching (AC vs battery, compile detection)
- Optional advanced module (manual opt-in) for deeper tuning
