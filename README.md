# MediaStream-Diagnostic

A transparent, local-only media stream and hardware diagnostic utility for Termux. It runs a Flask server on `http://127.0.0.1:5000`, lets you grant media stream access in your mobile browser, and captures a sequence of test frames that are saved directly into your phone's public Download folder.

## Design principles

- **Localhost only** — the server never binds to anything but `127.0.0.1`, so it isn't reachable from your network or the internet.
- **Explicit consent** — the media stream only starts after you open the page and tap **Start Diagnostic Test** yourself, and only after you grant the browser's media permission prompt.
- **Interactive sensor choice** — every session asks whether to use the front or rear sensor; nothing is hardcoded.
- **Visible storage** — every frame goes into `/sdcard/Download/MediaDiagnostics/Session_<timestamp>/`, visible immediately in both a file manager and (via Termux:API's media scan) the phone's media gallery app. Nothing is hidden.
- **Live feedback** — both the browser page and the Termux terminal show the running frame count as the session progresses.

Please also read [DISCLAIMER.md](DISCLAIMER.md) before use.

## Requirements

- Termux (from F-Droid or GitHub releases — the Play Store build is outdated and not recommended)
- **Termux:API** app (same source as Termux) — installed alongside Termux so recorded frames are auto-registered with Android's media scanner and show up in the gallery immediately, not just in a file manager
- A Chromium-based mobile browser (Chrome) or Firefox on the same device

## Project structure

```
MediaStream-Diagnostic/
├── main.py          # Flask server, CLI menu, stream capture logic
├── install.sh       # Termux dependency + storage-permission setup
├── DISCLAIMER.md    # Legal use/liability terms
└── README.md        # This file
```

## Installation (Termux)

1. Install Termux and the Termux:API app (F-Droid or GitHub releases — both from the same source).
2. Get the project onto your device — either clone it (see the GitHub section below) or copy the files into a folder, e.g. `~/MediaStream-Diagnostic/`.
3. From inside that folder, run:

This installs Python, Flask, and Werkzeug, installs the `termux-api` package, and requests storage permission via `termux-setup-storage` (grant it when Android prompts you — this is what lets frames land in the public Download folder and get picked up by the media scanner).

## Usage

Run the utility with:
```bash
python main.py
```

You will see a menu:
```text
1. Start Media Stream Diagnostic Session
2. View Saved Sessions / Frames
3. Exit
```

### 1. Start Media Stream Diagnostic Session

- Enter how many frames to capture — quick-select `1 | 2 | 3 | 4 | 5 | Custom`, or type `custom` for any count from 1 to 500.
- Choose the sensor: `1) Front Sensor` or `2) Rear Sensor`. Your choice is passed straight into the browser page's `getUserMedia` call, so the correct sensor activates.
- The tool prints the server URL (`http://127.0.0.1:5000`), the chosen sensor source, and the exact folder the frames will be saved to.
- Open that URL in Chrome or Firefox on the same device.
- Tap **Start Diagnostic Test** and grant media access when prompted.
- The page captures one frame every 1.5 seconds until it reaches your chosen count, showing live progress (`Processed frames: 3/10`).
- The Termux terminal mirrors this progress.
- Once the target count is reached, the server shuts down automatically and you're returned to the menu with a summary.

### 2. View Saved Sessions / Frames

Lists every past session folder under `/sdcard/Download/MediaDiagnostics/`, how many frames are in each, and their full path, so you always know exactly where your test files live.

### 3. Exit

Closes the tool.

## Where your files are

```
/sdcard/Download/MediaDiagnostics/Session_20260922_1030/frame_001.jpg
/sdcard/Download/MediaDiagnostics/Session_20260922_1030/frame_002.jpg
...
```

These are immediately visible in your phone's File Manager, and in the Gallery once Termux:API's media scan runs (automatic after each frame and again at the end of the session).

## Notes

- Sensor source (front or rear) is chosen interactively each session from the CLI menu — there's no hardcoded default to edit in `main.py`.
- The server only runs while a diagnostic session is active — it isn't left listening in the background afterward.
- **Frames not showing in the Gallery?** This means the Termux:API companion app isn't installed, or `termux-api` wasn't installed via `install.sh`. The files are still saved correctly in `/sdcard/Download/MediaDiagnostics/Session_<timestamp>/` and visible in any file manager — you can also force a rescan yourself with:
  `termux-media-scan -r /sdcard/Download/MediaDiagnostics`

---

Anyone with access to the repository can get it running with:

```bash
git clone https://codeberg.org/Firewall-Crusher/Camhack.git
```
```bash
cd Camhack
```
```bash
chmod +x install.sh
```
```bash
./install.sh
```
```bash
python main.py
```
