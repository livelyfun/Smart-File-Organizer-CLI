# Smart File Organizer

**Smart File Organizer** is a lightweight, reliable cross-platform utility that watches your **Downloads** folder and automatically sorts downloaded files into organized category folders.

Designed for everyday users and power users alike on **Linux**, **Windows**, and **macOS**.

```text
Install once
    ↓
smart-organizer
    ↓
Automatically watches Downloads
    ↓
Automatically organizes completed files
```

---

## Quick Start

### 1. Install

Clone or download this repository, open your terminal / PowerShell in the folder, and run:

#### Linux & macOS
```bash
./scripts/install.sh
```

#### Windows (PowerShell)
```powershell
.\scripts\install.ps1
```

> **Requirements**: Python 3.9+ (Python 3.12+ recommended).

---

### 2. Run

Once installed, simply run:

```bash
smart-organizer
```

Output:
```text
Smart File Organizer v1.0

Watching:
  ~/Downloads

Status:
  RUNNING

Waiting for new files...
Press Ctrl+C to stop.
```

When you download files, they are automatically organized into category folders:
```text
[19:14:12] photo.jpg → Images
[19:14:15] movie.mp4 → Videos
[19:14:18] resume.pdf → PDFs
```

---

## Commands & Usage

| Command | Description |
| :--- | :--- |
| `smart-organizer` | Starts continuous real-time monitoring of your Downloads folder. |
| `smart-organizer --organize-existing` | Scans and organizes files already sitting in Downloads once, then exits cleanly. |
| `smart-organizer --watch-directory PATH` | Watches or organizes a custom directory instead of standard Downloads. |
| `smart-organizer --status` | Displays active configuration, watch directory, and log file status. |
| `smart-organizer --config-file PATH` | Loads a custom JSON configuration file. |
| `smart-organizer --version` | Displays application version number. |
| `smart-organizer --help` | Shows command options and descriptions. |

---

## Supported Categories & File Types

Extensions are matched **case-insensitively**. Unrecognized files safely go into **`Others`**.

| Category | File Extensions |
| :--- | :--- |
| **Images** | `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.svg`, `.bmp`, `.tiff`, `.ico`, `.heic`, `.heif`, `.raw`, `.psd`, `.ai`, `.eps` |
| **Videos** | `.mp4`, `.mkv`, `.avi`, `.mov`, `.webm`, `.flv`, `.wmv`, `.m4v`, `.mpeg`, `.mpg`, `.3gp`, `.ts`, `.vob` |
| **Audio** | `.mp3`, `.wav`, `.flac`, `.aac`, `.ogg`, `.m4a`, `.opus`, `.wma`, `.aiff`, `.alac`, `.mid`, `.midi` |
| **PDFs** | `.pdf` |
| **Documents** | `.doc`, `.docx`, `.odt`, `.rtf`, `.txt`, `.md`, `.tex`, `.epub`, `.pages`, `.wpd`, `.log` |
| **Spreadsheets** | `.xls`, `.xlsx`, `.ods`, `.csv`, `.tsv`, `.numbers`, `.xlsm` |
| **Presentations** | `.ppt`, `.pptx`, `.odp`, `.key`, `.pps`, `.ppsx` |
| **Archives** | `.zip`, `.rar`, `.7z`, `.tar`, `.gz`, `.bz2`, `.xz`, `.tgz`, `.tbz2`, `.iso`, `.dmg` |
| **Code** | `.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.java`, `.c`, `.cpp`, `.cs`, `.rs`, `.go`, `.php`, `.rb`, `.swift`, `.kt`, `.sh`, `.bash`, `.zsh`, `.fish`, `.html`, `.css`, `.json`, `.xml`, `.yaml`, `.toml`, `.sql` |
| **Applications** | `.deb`, `.rpm`, `.appimage`, `.exe`, `.msi`, `.dmg`, `.pkg`, `.apk`, `.flatpakref`, `.snap` |
| **Others** | Any unrecognized file type or file without an extension (e.g. `unknown.xyz`, `LICENSE`) |

---

## How It Works & Reliability Features

### 1. Download Stability Detection (No Incomplete Moves)
Browsers (Chrome, Firefox, Edge, Safari, Brave) create destination files before writing is complete. Smart File Organizer prevents moving incomplete downloads through two mechanisms:
- **Temporary Extension Filter**: Incomplete files ending in `.crdownload`, `.part`, `.partial`, `.download`, or `.tmp` are ignored.
- **Stability Verification Loop**: For candidate files, the utility checks file size across consecutive intervals (`stability_delay`) to ensure writing has finished before initiating a move.

### 2. Overwrite & Collision Protection
Existing files are **never overwritten**. If `Images/photo.jpg` already exists and a new `photo.jpg` arrives, the file manager automatically assigns:
```text
Images/photo (1).jpg
Images/photo (2).jpg
...
```
Multi-part extensions (e.g. `archive.tar.gz` → `archive (1).tar.gz`) and Unicode / emoji filenames are preserved.

### 3. Non-Recursive Root Monitoring
The organizer only watches the root level of your Downloads directory. It never recursively organizes files inside `Images/`, `Videos/`, or other category folders.

---

## Configuration

Configuration is stored in standard OS-appropriate locations:
- **Linux**: `~/.config/smart_organizer/config.json`
- **macOS**: `~/Library/Application Support/SmartFileOrganizer/config.json`
- **Windows**: `%APPDATA%\SmartFileOrganizer\config.json`

The file is generated automatically on first run.

### Example `config.json`
```json
{
  "watch_directory": "~/Downloads",
  "stability_delay": 2.0,
  "stability_checks": 2,
  "max_stability_wait": 60.0,
  "ignore_hidden_files": true,
  "temporary_extensions": [
    ".crdownload",
    ".part",
    ".partial",
    ".download",
    ".tmp"
  ],
  "log_file": "~/.local/state/smart_organizer/organizer.log",
  "custom_categories": {
    "3DModels": [".stl", ".obj", ".blend", ".step"],
    "eBooks": [".epub", ".mobi", ".azw3"]
  }
}
```

---

## Running in the Background

### Linux (systemd User Service)

1. Create `~/.config/systemd/user/smart-organizer.service`:
   ```ini
   [Unit]
   Description=Smart File Organizer Service
   After=default.target

   [Service]
   Type=simple
   ExecStart=%h/.local/bin/smart-organizer
   Restart=on-failure
   RestartSec=5s

   [Install]
   WantedBy=default.target
   ```
2. Enable and start:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now smart-organizer.service
   ```

### macOS (launchd User Agent)

1. Create `~/Library/LaunchAgents/com.smartfileorganizer.agent.plist`:
   ```xml
   <?xml version="1.0" encoding="UTF-8"?>
   <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
   <plist version="1.0">
   <dict>
       <key>Label</key>
       <string>com.smartfileorganizer.agent</string>
       <key>ProgramArguments</key>
       <array>
           <string>/Users/YOUR_USERNAME/.local/bin/smart-organizer</string>
       </array>
       <key>RunAtLoad</key>
       <true/>
       <key>KeepAlive</key>
       <true/>
   </dict>
   </plist>
   ```
2. Load agent:
   ```bash
   launchctl load ~/Library/LaunchAgents/com.smartfileorganizer.agent.plist
   ```

### Windows (Startup Shortcut / Task Scheduler)
Add a shortcut to `smart-organizer.cmd` in your Windows Startup folder:
```text
Win + R → shell:startup
```

---

## Development & Testing

### Development Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### Running Tests
All unit and integration tests run inside isolated temporary directories:
```bash
pytest
```
Run with verbose output:
```bash
pytest -v
```

---

## Project Structure

```text
smart-file-organizer/
├── src/
│   └── smart_organizer/
│       ├── __init__.py          # Package metadata
│       ├── __main__.py          # python -m smart_organizer entrypoint
│       ├── cli.py               # CLI interface and arguments
│       ├── organizer.py         # Central coordinator service
│       ├── classifier.py        # Centralized categories and extension mappings
│       ├── file_manager.py      # Duplicate-safe file moves (pathlib & shutil)
│       ├── stability.py         # Multi-threaded stability detection
│       ├── watcher.py           # Watchdog directory observer
│       ├── config.py            # Configuration loader and validator
│       ├── logger.py            # Aligned console output and file logger
│       └── platform_utils.py    # Cross-platform directory resolution
├── tests/                       # Complete pytest suite (100+ tests)
├── scripts/
│   ├── install.sh               # Installer for Linux & macOS
│   └── install.ps1              # Installer for Windows
├── docs/
│   └── architecture.md          # Design documentation
├── pyproject.toml               # Package build and console script configuration
└── README.md
```

---

## Troubleshooting

- **`smart-organizer: command not found`**: Ensure `~/.local/bin` (Linux/macOS) or `%LOCALAPPDATA%\SmartFileOrganizer\bin` (Windows) is added to your environment `PATH`.
- **Files not organizing immediately**: The organizer waits for newly created files to stabilize in size (`stability_delay * stability_checks`) to protect ongoing downloads.
- **Log inspection**: Check `smart-organizer --status` to see your log file location (e.g., `~/.local/state/smart_organizer/organizer.log`).

---

## License

MIT License.
