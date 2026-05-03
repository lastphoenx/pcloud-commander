# Developer Guide: pcloud-commander

Living technical documentation for development and operations.
Please update this guide when architecture or workflows change.

## Overview

pcloud-commander is a Textual TUI for local and remote file operations on pCloud.
The app deliberately reuses core backend capabilities from pcloud-tools and script metadata from script-manager-ui.

Core pillars:

1. UI and interaction layer
   - File: pcloud_commander.py
   - Provides two-pane navigation, modals, forms, action menus, confirmations
2. pCloud backend access
   - Source: pcloud_bin_lib.py from pcloud-tools
   - Provides list, copy, move, delete, upload, download APIs
3. Script catalog integration
   - Source: scripts.yaml from script-manager-ui
   - Provides dashboard entries and parameter schemas
4. Safety model
   - High-risk script defaults and confirmation dialogs
   - Root-path guardrails for destructive or broad operations

## Runtime Architecture

### Startup flow

1. Python process starts pcloud_commander.py (usually via pcloud-commander.sh).
2. load_pcloud_lib() resolves pcloud_bin_lib.py from known search paths.
3. find_env_file() resolves .env from known search paths.
4. PCloudCommander initializes:
   - effective_config() via pcloud_bin_lib
   - selected theme registration and activation
   - external script catalog loading from scripts.yaml
5. UI mounts and initializes local and pCloud pane states.

### Dependency resolution strategy

pcloud_commander.py uses defensive path resolution for production and dev setups.
The relevant targets are:

- pcloud-tools library:
  - ../pcloud-tools/main/pcloud_bin_lib.py
  - ../pcloud-tools/pcloud_bin_lib.py
  - /opt/apps/pcloud-tools/main/pcloud_bin_lib.py
- script catalog:
  - ../script-manager-ui/scripts.yaml
  - /opt/apps/script-manager-ui/scripts.yaml
- env file:
  - ./.env
  - ../pcloud-tools/main/.env
  - ../pcloud-tools/.env
  - /opt/apps/pcloud-tools/main/.env

## UI Structure

### Main app

Class: PCloudCommander

Responsibilities:

- Render and keep both panes in sync
- Track active pane and apply focus behavior
- Bridge UI actions to backend API calls
- Load and run script catalog entries

Main bindings:

- q: quit
- r: refresh
- backspace/u: go up in pCloud tree
- tab: switch active pane
- d: download selected pCloud file
- f8: delete selected pCloud item
- a: file actions menu
- s: scripts dashboard

### Screens and modals

- ConfirmModal: yes/no confirmations
- TextInputModal: generic text input
- ActionMenu: list-based command chooser
- QuickUploadModal: source/destination wizard for upload and folder sync
- NewFolderScreen: create folders from browser contexts
- PathBrowserScreen: local path selection (folder-only or file/folder)
- PCloudBrowserScreen: pCloud path selection (folder-only or full)
- ScriptDashboardScreen: quick actions plus script catalog overview
- ScriptFormScreen: parameter editor generated from scripts.yaml definitions

## File Operations

### Local-side operations

Available from file actions when the left pane is active:

- create subfolder
- copy item
- move item
- rename item
- delete item

Guardrails:

- destination validation stays inside local_root
- explicit confirmation before delete

### pCloud-side operations

Available from file actions when the right pane is active:

- refresh list
- create subfolder
- copy item
- move item
- delete item

Guardrails:

- root folder deletion is blocked
- explicit confirmation before delete
- folder move fallback uses copy + delete

## Script Catalog Integration

### Data source

The catalog is loaded read-only from scripts.yaml.
Entries without valid name/cmd fields are ignored.

### Parameter processing

ScriptFormScreen supports:

- string/path/int/bool/select-like inputs
- browse actions for local and pCloud paths
- bool toggles with clear visual feedback

Command construction behavior:

- param names are normalized to CLI flags via --name-with-dashes
- bool true emits flag only
- empty values are skipped
- positional mode is supported

### Context autofill

Autofill derives defaults from current selection context:

- local source-like params from selected local path
- remote target-like params from selected pCloud folder/path

## Safety Model

High-risk scripts are detected by metadata and naming heuristics.
Before execution:

- safe defaults are enforced (for dry-run/execute pairs)
- a dedicated confirmation dialog is shown

Quick upload/sync guardrails include:

- explicit source/destination fields
- browse-based selection support
- protection against accidental broad root-source uploads in wizard flow

## Installation and Start (Operational Baseline)

Current baseline:

- pcloud-commander: /opt/apps/pcloud-commander/main
- pcloud-tools: /opt/apps/pcloud-tools/main
- script-manager-ui: /opt/apps/script-manager-ui

Start command:

```bash
sudo /opt/apps/pcloud-commander/main/pcloud-commander.sh
```

The launcher expects:

- pcloud-tools venv at /opt/apps/pcloud-tools/venv
- textual and pyyaml installed in that venv
- valid pcloud-tools .env

## Development Workflow

### Typical local loop

1. Edit pcloud_commander.py
2. Start via pcloud-commander.sh
3. Validate local and pCloud actions manually
4. Validate script dashboard and at least one high-risk flow
5. Commit with focused message

### Regression checklist

Run these checks before release:

1. App starts and both panes render
2. Active pane switching and highlighting are correct
3. Local actions use local browser and local destination constraints
4. pCloud actions use pCloud browser and do not route to wrong pane
5. Quick upload wizard can browse both sides and complete execution
6. High-risk script requires explicit confirmation
7. Root-folder deletion stays blocked

## Troubleshooting

### pcloud_bin_lib.py not found

- Verify pcloud-tools path
- Verify file exists at /opt/apps/pcloud-tools/main/pcloud_bin_lib.py

### scripts.yaml unavailable

- Verify script-manager-ui is deployed
- Verify file exists at /opt/apps/script-manager-ui/scripts.yaml
- Verify pyyaml is installed

### .env not found or auth fails

- Verify .env location and permissions
- Verify required pCloud credentials in pcloud-tools config

### Colors/theme issues in terminal

The launcher sets sane defaults:

- COLORTERM=truecolor
- TERM=xterm-256color

If colors still look wrong, test another terminal emulator and check TERM support.

## Security and Secret Hygiene

### Repository-level hygiene

- .env and .env.* are ignored by .gitignore
- do not hardcode credentials in Python or shell scripts
- use environment files outside versioned source when possible

### Local pre-push checks

Recommended quick checks from repo root:

```bash
# scan working tree for common secret patterns
rg -n -i "token|secret|api[_-]?key|password|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|ghp_|github_pat_|AKIA|ASIA"

# optional: scan git history for the same patterns
for c in $(git rev-list --all); do
  git grep -n -I -E "AKIA|ASIA|ghp_|github_pat_|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY|secret|api[_-]?key|token|password" "$c"
done
```

For production-grade scanning in CI, add gitleaks or trufflehog as a dedicated job.

### GitHub Web UI settings (public repos)

Recommended settings in repository Security:

1. Enable Secret scanning
2. Enable Push protection for secret scanning
3. Enable Dependabot alerts
4. Enable Dependabot security updates
5. Enable Code scanning (CodeQL default setup)

Optional org-level hardening:

- enforce push protection at org level
- require pull requests and status checks before merge
- enable branch protection for main

## Change Management

When updating behavior in modals, file actions, or safety defaults:

1. Update README if user-visible behavior changes
2. Update this guide section for architecture/safety changes
3. Add a concise changelog note in commit message
4. Re-test wizard and high-risk script flow end-to-end
