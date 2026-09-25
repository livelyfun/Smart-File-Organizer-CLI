# Smart File Organizer - Architecture & Technical Design

## Overview
Smart File Organizer is a lightweight, cross-platform file organizing utility built on standard Python and `watchdog`. It monitors watched directories (originally the user's Downloads folder) and automatically moves completed files into category folders (`Images/`, `Videos/`, `Audio/`, `PDFs/`, `Documents/`, `Spreadsheets/`, `Presentations/`, `Archives/`, `Code/`, `Applications/`, `Others/`).

The application is a **Python core** shared by two frontends: a classic **CLI** and a future **PySide6 desktop GUI**. The GUI and CLI share the same core; neither frontend calls the other or parses terminal output.

## Architecture Layers

```text
        PySide6 Desktop GUI (Phase 3)
                    |
                    v
        Application / Service Layer
        (application/services)
        - OrganizerService, EventBus, events
                    |
                    v
              Python Core (core/)
        watcher  organizer  classifier  file_manager  stability
                config . platform_utils . logger
                    |
                    v
            Filesystem & Logging
         (pathlib, shutil, watchdog)

CLI (cli/) ----------------------------
```

- **`core/`**: Platform-independent engine. No console or UI logic. Everything here is reusable by any frontend.
- **`application/services/`**: Frontend-agnostic services on top of the core. Long-running operations (monitoring) run off the caller's thread, and all outcomes are surfaced as structured **events** through the `EventBus`.
- **`cli/`**: Console frontend. Entry point: `smart-organizer = smart_organizer.cli:main`.
- **`gui/`**: Desktop frontend (PySide6). Structure established in Phase 0; UI implemented in Phase 3.

## Module Responsibilities

### Core engine (`src/smart_organizer/core/`)
- **`platform_utils.py`**: Isolates all OS-specific paths (Linux XDG, macOS `Library/Application Support`, Windows `%APPDATA%`, and standard Downloads directory resolution).
- **`config.py`**: Loads JSON configuration, provides automatic default config generation, validates values, and manages custom extension overrides.
- **`classifier.py`**: Houses the centralized extension lookup table for the built-in categories and identifies temporary/incomplete download extensions.
- **`stability.py`**: Provides asynchronous, non-blocking size check loops to guarantee files are finished writing before organization.
- **`file_manager.py`**: Atomic safe movement with automatic collision protection (`photo (1).jpg`), directory creation, and non-crashing filesystem error handling.
- **`watcher.py`**: Non-recursive `watchdog` monitoring of the watched directory root.
- **`logger.py`**: Dual-output logger supporting aligned console status and persistent file logging. Defines the logger protocol that frontends can also implement to capture events.
- **`organizer.py`**: Service orchestrating the organization loop and collecting metrics.

### Application services (`src/smart_organizer/application/services/`)
- **`events.py`**: Structured domain events (`file_organized`, `file_skipped`, `file_error`, `monitoring_started`, `monitoring_stopped`, `batch_complete`, `info`).
- **`event_bus.py`**: Thread-safe publish/subscribe bus with listener error isolation.
- **`event_logger.py`**: Duck-typed `OrganizerLogger` that publishes events instead of printing; optionally forwards to a persistent file logger.
- **`application_service.py`**: `OrganizerService` - the shared entry point for frontends. Provides non-blocking `start()`/`stop()` for live monitoring, `organize_existing()`, `organize_file()`, and `status()`.

### Frontends
- **`cli/`**: User-facing command line interface and signal handling.
- **`gui/`**: Desktop GUI placeholder (Phase 3).

## Design Rules
- Filesystem business logic never lives in GUI widgets - it stays in the core engine.
- The GUI must never invoke the CLI or parse its output; both frontends share the core/services layer.
- Files are never overwritten or deleted silently; moves are collision-safe and reversible.
- Long filesystem/hash operations always run off the UI thread (services already do this).

## Backward Compatibility
Moved modules retain thin re-export shims at the original `smart_organizer.*` paths (e.g. `smart_organizer.config` re-exports `smart_organizer.core.config`), so third-party imports, the package entry points, and the test suite keep working unchanged.