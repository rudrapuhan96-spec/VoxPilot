# VoxPilot — Phase 2 Foundation (Windows)

This is a **working foundation prototype**, not the finished AI operator. It demonstrates the important execution model:
- lightweight Tkinter UI (built into Python on Windows)
- long-running work executes on a background thread so the UI does not freeze
- task progress is sent to the UI through a queue
- only registered tools are exposed; the app does not execute arbitrary AI-generated shell text
- PowerShell calls have timeouts and output limits
- read-only system and network diagnostics
- open Settings / launch Notepad on request
- cancellation signal for supported tasks

## Requirements
- Windows 10/11
- Python 3.11+ (Python 3.12/3.13 recommended)
- No third-party packages required for this foundation

## Run
1. Extract this ZIP to a folder such as `C:\VoxPilot`.
2. Open PowerShell in that folder.
3. Run:
   ```powershell
   py -3 voxpilot\app.py
   ```
   If `py` is unavailable, try `python voxpilot\app.py`.

## What it can do today
- Show basic system information.
- Run read-only network diagnostics.
- Open Windows Settings or Notepad.
- Keep long tasks off the UI thread and display progress.

## What it cannot do yet
- It does not yet include speech recognition, a full LLM planner, broad desktop automation, automatic repair playbooks, or an installer.
- It does not provide a blanket unrestricted administrator shell.
- It does not guarantee that every fault can be fixed.

## Administrator operations
For the first foundation, diagnostics are read-only and do not need admin. Later repair tools should request elevation per operation using Windows UAC, validate the exact operation, and verify results. Do not store admin passwords or bypass UAC.

## Performance principles
- One system-changing job at a time.
- Keep UI work on the main thread and blocking work on a worker thread.
- Set timeouts and cap captured output.
- Do not continuously poll hardware/services.
- Add optional voice/model components only when needed; do not load a large model at startup.

## Next implementation milestones
1. Add structured task planner and intent parsing.
2. Add tested diagnostic playbooks and verification checks.
3. Add controlled UAC elevation for individually registered repair tools.
4. Add push-to-talk Hindi/Hinglish voice layer.
5. Add desktop automation and app workflows.
6. Add packaging, resource profiling, and recovery tests.
