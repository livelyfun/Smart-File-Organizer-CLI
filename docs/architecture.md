# Smart File Organizer - Architecture & Technical Design

## Overview
Smart File Organizer is a lightweight, cross-platform CLI tool built on standard Python and `watchdog`. It monitors the user's Downloads directory and automatically moves completed files into category folders (`Images/`, `Videos/`, `Audio/`, `PDFs/`, `Documents/`, `Spreadsheets/`, `Presentations/`, `Archives/`, `Code/`, `Applications/`, `Others/`).

## Architecture Layers

```text
                smart-organizer (CLI)
                       │
                       ▼
                   CLI (cli.py)
                       │
                       ▼
              Platform & Configuration
         (platform_utils.py, config.py)
                       │
                       ▼
            Organizer (organizer.py)
            ┌──────────┴──────────┐
            ▼                     ▼
     Directory Watcher    Batch Organizer
       (watcher.py)       (organizer.py)
            │                     │
            ▼                     ▼
   Stability Detector     Classifier (classifier.py)
     (stability.py)               │
            │                     │
            └──────────┬──────────┘
                       ▼
                 File Manager
               (file_manager.py)
                       │
                       ▼
               Filesystem & Logger
             (pathlib, shutil, logger.py)
```

## Module Responsibilities

- **`platform_utils.py`**: Isolates all OS-specific paths (Linux XDG, macOS `Library/Application Support`, Windows `%APPDATA%`, and standard Downloads directory resolution).
- **`config.py`**: Loads JSON configuration, provides automatic default config generation, validates values, and manages custom extension overrides.
- **`classifier.py`**: Houses the centralized extension lookup table for 11 categories and identifies temporary/incomplete download extensions.
- **`stability.py`**: Provides asynchronous, non-blocking size check loops to guarantee files are finished writing before organization.
- **`file_manager.py`**: Atomic safe movement with automatic collision protection (`photo (1).jpg`), directory creation, and non-crashing filesystem error handling.
- **`watcher.py`**: Non-recursive `watchdog` monitoring of the root watched directory only.
- **`logger.py`**: Dual-output logger supporting aligned console status and persistent file logging.
- **`organizer.py`**: Service orchestrating the organization loop and collecting metrics.
- **`cli.py`**: User-facing command line interface and signal handling.
