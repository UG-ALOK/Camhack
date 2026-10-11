#!/usr/bin/env python3
"""
MediaStream-Diagnostic
A transparent, local-only media stream and hardware diagnostic tool.

- Runs strictly on http://127.0.0.1:5000
- Media stream only activates after explicit user click in the browser
- All capture frames saved directly to the public Download folder so they show
  up immediately in Gallery / File Manager:
      /sdcard/Download/MediaDiagnostics/Session_<timestamp>/
- Live progress shown both in the browser and in the terminal
"""

import os
import sys
import time
import base64
import threading
import subprocess
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string
from werkzeug.serving import make_server

# ---------------------------------------------------------------------------
# Storage location: public Downloads folder so files appear in Gallery /
# File Manager immediately, with no hidden or intermediate directories.
# ---------------------------------------------------------------------------
PRIMARY_CAPTURES_ROOT = "/sdcard/Download/MediaDiagnostics"
FALLBACK_CAPTURES_ROOT = os.path.join(os.path.expanduser("~"), "storage", "downloads", "MediaDiagnostics")
LOCAL_FALLBACK_ROOT = os.path.join(os.getcwd(), "captures")

HOST = "127.0.0.1"
PORT = 5000

MIN_FRAMES = 1
MAX_FRAMES = 500

# Real, deliberate gap between each capture -- genuine sequential frames,
# not an instant burst.
CAPTURE_INTERVAL_MS = 1500

# ---------------------------------------------------------------------------
# ANSI colors (used only for the CLI menu -- purely cosmetic, no hidden logic)
# ---------------------------------------------------------------------------
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    MAGENTA = "\033[95m"
    RED = "\033[91m"
    BLUE = "\033[94m"


def colorize(text, color_code):
    return f"{color_code}{text}{C.RESET}"


def trigger_media_scan(path, recursive=False):
    """
    Ask Android's media scanner to index newly written files so they show up
    in Gallery immediately, not just in a file manager. Requires the
    Termux:API app + termux-api package. Silently no-ops if unavailable --
    this is a visibility nicety, not something that should ever break a
    diagnostic session.
    """
    cmd = ["termux-media-scan"]
    if recursive:
        cmd.append("-r")
    cmd.append(path)
    try:
        subprocess.run(
            cmd,
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# HTML / JS served to the browser
# ---------------------------------------------------------------------------
PAGE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MediaStream-Diagnostic</title>
<style>
  body { font-family: sans-serif; background:#111; color:#eee; text-align:center; padding:20px; }
  video, canvas { width:90%; max-width:420px; border-radius:8px; border:2px solid #444; }
  button { padding:14px 28px; font-size:16px; margin-top:16px; border:none; border-radius:8px;
           background:#2e7d32; color:white; cursor:pointer; }
  button:disabled { background:#555; }
  #status { margin-top:16px; font-size:18px; }
  #path { font-size:13px; color:#aaa; word-break:break-all; margin-top:8px; }
  canvas { display:none; }
</style>
</head>
<body>
  <h2>MediaStream Diagnostic</h2>
  <p>Session: {{ session_code }} &mdash; Target: {{ target }} frame(s)</p>
  <video id="video" autoplay playsinline muted></video>
  <canvas id="canvas"></canvas>
  <br>
  <button id="startBtn">Start Diagnostic Test</button>
  <div id="status">Idle. Click the button to initialize media stream.</div>
  <div id="path">Saving to: {{ folder_path }}</div>

<script>
const TARGET = {{ target }};
const CAPTURE_INTERVAL_MS = {{ capture_interval_ms }};

const video = document.getElementById('video');
const canvas = document.getElementById('canvas');
const startBtn = document.getElementById('startBtn');
const statusEl = document.getElementById('status');

let stream = null;
let aborted = false;

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function waitForNextPaintedFrame() {
  return new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
}

async function startStream() {
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "{{ facing_mode }}" },
      audio: false
    });
    video.srcObject = stream;

    await new Promise((resolve, reject) => {
      video.onloadedmetadata = () => resolve();
      video.onerror = (e) => reject(e);
    });
    await video.play();
    await sleep(700);
  } catch (err) {
    statusEl.textContent = "Stream access denied or unavailable: " + err.message;
    throw err;
  }
}

async function captureFrame() {
  await waitForNextPaintedFrame();
  const w = video.videoWidth || 640;
  const h = video.videoHeight || 480;
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  ctx.drawImage(video, 0, 0, w, h);
  return canvas.toDataURL('image/jpeg', 0.9);
}

async function uploadFrame(dataUrl, index) {
  const resp = await fetch('/upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ image: dataUrl, index: index })
  });
  return resp.json();
}

async function runDiagnosticSequence() {
  for (let i = 1; i <= TARGET && !aborted; i++) {
    statusEl.textContent = "Processing frame " + i + "/" + TARGET + "...";
    let dataUrl;
    try {
      dataUrl = await captureFrame();
    } catch (e) {
      statusEl.textContent = "Capture error: " + e.message;
      return;
    }

    let result;
    try {
      result = await uploadFrame(dataUrl, i);
    } catch (e) {
      statusEl.textContent = "Upload error: " + e.message;
      return;
    }

    statusEl.textContent = "Saving frames: " + result.count + "/" + TARGET;

    if (result.count >= TARGET) {
      break;
    }

    await sleep(CAPTURE_INTERVAL_MS);
  }

  statusEl.textContent = "Done. Processed " + TARGET + "/" + TARGET + " frames.";
  if (stream) {
    stream.getTracks().forEach(t => t.stop());
  }
  setTimeout(() => {
    statusEl.textContent += " You can close this tab and return to Termux.";
  }, 500);
}

startBtn.addEventListener('click', async () => {
  startBtn.disabled = true;
  aborted = false;
  statusEl.textContent = "Requesting media permissions...";
  try {
    await startStream();
  } catch (e) {
    startBtn.disabled = false;
    return;
  }

  statusEl.textContent = "Saving frames: 0/" + TARGET;
  await runDiagnosticSequence();
});
</script>
</body>
</html>
"""

# ---------------------------------------------------------------------------
# Server thread wrapper
# ---------------------------------------------------------------------------
class ServerThread(threading.Thread):
    def __init__(self, app, host, port):
        super().__init__()
        self.srv = make_server(host, port, app)
        self.ctx = app.app_context()
        self.ctx.push()
        self.daemon = True

    def run(self):
        self.srv.serve_forever()

    def shutdown(self):
        self.srv.shutdown()


def build_app(session_code, target, folder_path, facing_mode, state, state_lock):
    app = Flask(__name__)

    @app.route("/")
    def index():
        return render_template_string(
            PAGE_TEMPLATE,
            session_code=session_code,
            target=target,
            folder_path=folder_path,
            facing_mode=facing_mode,
            capture_interval_ms=CAPTURE_INTERVAL_MS,
        )

    @app.route("/upload", methods=["POST"])
    def upload():
        data = request.get_json(force=True)
        image_data_url = data.get("image", "")
        if "," in image_data_url:
            header, b64data = image_data_url.split(",", 1)
        else:
            b64data = image_data_url

        with state_lock:
            if state["count"] >= target:
                return jsonify({"count": state["count"], "status": "already_complete"})
            state["count"] += 1
            current_index = state["count"]

        try:
            image_bytes = base64.b64decode(b64data)
        except Exception as exc:
            return jsonify({"error": f"decode_failed: {exc}"}), 400

        filename = f"frame_{current_index:03d}.jpg"
        filepath = os.path.join(folder_path, filename)
        with open(filepath, "wb") as f:
            f.write(image_bytes)

        trigger_media_scan(filepath, recursive=False)

        return jsonify({"count": current_index, "status": "ok", "file": filename})

    return app


def resolve_captures_root():
    for candidate in (PRIMARY_CAPTURES_ROOT, FALLBACK_CAPTURES_ROOT):
        try:
            os.makedirs(candidate, exist_ok=True)
            test_file = os.path.join(candidate, ".write_test")
            with open(test_file, "w") as f:
                f.write("ok")
            os.remove(test_file)
            return candidate
        except Exception:
            continue

    os.makedirs(LOCAL_FALLBACK_ROOT, exist_ok=True)
    print(colorize(
        "  Warning: could not write to /sdcard/Download. "
        "Run 'termux-setup-storage' and grant permission.\n"
        f"  Falling back to local visible folder: {LOCAL_FALLBACK_ROOT}",
        C.YELLOW
    ))
    return LOCAL_FALLBACK_ROOT


def prompt_sensor_choice():
    print(colorize("\n  Select sensor input:", C.BOLD + C.CYAN))
    print(colorize("  " + "-" * 40, C.CYAN))
    cells = [
        colorize("1) Front Sensor", C.GREEN),
        colorize("2) Rear Sensor", C.GREEN),
    ]
    print("  " + "   |   ".join(cells))
    print(colorize("  " + "-" * 40, C.CYAN))

    while True:
        raw = input(colorize("  Choose 1 or 2: ", C.YELLOW)).strip()
        if raw == "1":
            return "user"
        if raw == "2":
            return "environment"
        print(colorize("  Please enter 1 (Front) or 2 (Rear).", C.RED))


def start_diagnostic_test():
    target = prompt_frame_count()
    facing_mode = prompt_sensor_choice()
    session_code = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"Session_{session_code}"

    captures_root = resolve_captures_root()
    folder_path = os.path.join(captures_root, folder_name)
    os.makedirs(folder_path, exist_ok=True)

    state = {"count": 0}
    state_lock = threading.Lock()

    app = build_app(session_code, target, folder_path, facing_mode, state, state_lock)
    server = ServerThread(app, HOST, PORT)

    url = f"http://{HOST}:{PORT}"

    print("\n" + colorize("=" * 60, C.CYAN))
    print(colorize(f"  MediaStream-Diagnostic -- Session {folder_name}", C.BOLD + C.GREEN))
    print(colorize("=" * 60, C.CYAN))
    print(f"  Target frames : {colorize(target, C.YELLOW)}")
    print(f"  Sensor source : {colorize('Front Sensor' if facing_mode == 'user' else 'Rear Sensor', C.YELLOW)}")
    print(f"  Save folder   : {colorize(folder_path, C.BLUE)}")
    print(f"  Server URL    : {colorize(url, C.MAGENTA)}")
    print(colorize("=" * 60, C.CYAN))
    print("  Open the URL above in a mobile browser (Chrome/Firefox).")
    print("  Click 'Start Diagnostic Test' on the page to begin.")
    print("  Waiting for diagnostic sequence to complete... (Ctrl+C to abort)")
    print(colorize("=" * 60, C.CYAN) + "\n")

    server.start()

    try:
        subprocess.run(
            ["termux-open-url", url],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=3,
        )
    except Exception:
        pass

    last_printed = -1
    try:
        while True:
            with state_lock:
                current = state["count"]
            if current != last_printed:
                print(colorize(f"  Processed frames: {current}/{target}", C.GREEN), flush=True)
                last_printed = current
            if current >= target:
                break
            time.sleep(0.5)
    except KeyboardInterrupt:
        print(colorize("\n  Aborted by user.", C.RED))
    finally:
        server.shutdown()
        server.join(timeout=5)

    with state_lock:
        final_count = state["count"]

    trigger_media_scan(folder_path, recursive=True)

    print("\n" + colorize("=" * 60, C.CYAN))
    print(colorize("  Diagnostic session complete.", C.BOLD + C.GREEN))
    print(f"  Frames recorded : {colorize(f'{final_count}/{target}', C.YELLOW)}")
    print(f"  Saved in        : {colorize(folder_path, C.BLUE)}")
    print(colorize("=" * 60, C.CYAN) + "\n")


QUICK_COUNTS = [1, 2, 3, 4, 5]


def print_quick_menu():
    print(colorize("\n  Quick select frame count:", C.BOLD + C.CYAN))
    print(colorize("  " + "-" * 40, C.CYAN))

    cells = [colorize(f"{n}", C.GREEN) for n in QUICK_COUNTS]
    cells.append(colorize("Custom", C.MAGENTA))
    row = "  " + "  |  ".join(cells)
    print(row)

    print(colorize("  " + "-" * 40, C.CYAN))
    print(colorize(
        f"  Type one of the numbers above, or 'custom' for any\n"
        f"  count from {MIN_FRAMES} to {MAX_FRAMES}.",
        C.CYAN
    ))
    print()


def prompt_custom_count():
    while True:
        raw = input(
            colorize(f"  Enter custom frame count ({MIN_FRAMES}-{MAX_FRAMES}): ", C.YELLOW)
        ).strip()
        if raw.isdigit():
            n = int(raw)
            if MIN_FRAMES <= n <= MAX_FRAMES:
                return n
        print(colorize(f"  Please enter a whole number between {MIN_FRAMES} and {MAX_FRAMES}.", C.RED))


def prompt_frame_count():
    print_quick_menu()
    while True:
        raw = input(colorize("Select an option: ", C.YELLOW)).strip().lower()

        if raw in ("custom", "c"):
            return prompt_custom_count()

        if raw.isdigit():
            n = int(raw)
            if MIN_FRAMES <= n <= MAX_FRAMES:
                return n

        print(colorize(
            f"  Please enter {', '.join(str(n) for n in QUICK_COUNTS)}, "
            f"'custom', or any number {MIN_FRAMES}-{MAX_FRAMES}.",
            C.RED
        ))


def view_saved_sessions():
    captures_root = resolve_captures_root()

    sessions = sorted(
        d for d in os.listdir(captures_root)
        if os.path.isdir(os.path.join(captures_root, d))
    ) if os.path.isdir(captures_root) else []

    if not sessions:
        print(colorize("\nNo sessions found yet. Run option 1 first.\n", C.YELLOW))
        return

    print("\n" + colorize("=" * 60, C.CYAN))
    print(colorize("  Saved Diagnostic Sessions", C.BOLD + C.GREEN))
    print(colorize("=" * 60, C.CYAN))
    for session in sessions:
        session_path = os.path.join(captures_root, session)
        frames = sorted(
            f for f in os.listdir(session_path)
            if f.lower().endswith((".jpg", ".jpeg", ".png"))
        )
        print(colorize(f"  {session}", C.BOLD))
        print(f"    Path   : {colorize(session_path, C.BLUE)}")
        print(f"    Frames : {colorize(len(frames), C.YELLOW)}")
        if frames:
            preview = ", ".join(frames[:5]) + (" ..." if len(frames) > 5 else "")
            print(f"    Files  : {preview}")
        print(colorize("-" * 60, C.CYAN))
    print()


def main_menu():
    resolve_captures_root()

    while True:
        print(colorize("=" * 60, C.CYAN))
        print(colorize("  MediaStream-Diagnostic -- Main Menu", C.BOLD + C.GREEN))
        print(colorize("=" * 60, C.CYAN))
        print(f"  {colorize('1.', C.YELLOW)} Start Media Stream Diagnostic Session")
        print(f"  {colorize('2.', C.YELLOW)} View Saved Sessions / Frames")
        print(f"  {colorize('3.', C.YELLOW)} Exit")
        choice = input(colorize("Select an option (1-3): ", C.MAGENTA)).strip()

        if choice == "1":
            start_diagnostic_test()
        elif choice == "2":
            view_saved_sessions()
        elif choice == "3":
            print(colorize("Goodbye.", C.GREEN))
            sys.exit(0)
        else:
            print(colorize("Invalid option. Please choose 1, 2, or 3.\n", C.RED))


if __name__ == "__main__":
    try:
        main_menu()
    except KeyboardInterrupt:
        print(colorize("\nExiting.", C.YELLOW))
        sys.exit(0)
