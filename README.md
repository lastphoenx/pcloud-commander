# pcloud-commander

A terminal-first file commander for pCloud, built with Textual and powered by the high-performance binary API backend.

## Why this project exists

Generic file explorers do not understand pCloud's binary protocol features out of the box.
This project focuses on a tailored workflow for:

- fast remote listing and navigation
- remote search at scale
- upload/download operations with binary API speed
- pCloud-specific actions such as share links and crypto-aware workflows

## Planned UI concept

- Left pane: local filesystem browser
- Right pane: pCloud folder view
- Bottom bar: command/search input
- Hotkeys for core operations (copy, move, refresh, upload, download)

## Initial roadmap

1. Bootstrap Textual app skeleton
2. Implement pCloud client adapter around `pcloud_bin_lib.py`
3. Add two-pane navigation and table rendering
4. Add transfer jobs with progress + error states
5. Add search, share links, and optional crypto operations

## Project status

Early bootstrap phase. The repository currently contains foundational project docs and repository hygiene settings.

## Development principles

- Keep operations explicit and auditable
- Prefer robust error handling over hidden retries
- Maintain deterministic behavior for sync operations
- Keep shell scripts and Python code portable

## License

TBD
