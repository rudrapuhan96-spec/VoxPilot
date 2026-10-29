from __future__ import annotations

import os
import platform
import queue
import subprocess
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from dataclasses import dataclass
from typing import Callable, Any


@dataclass
class TaskEvent:
    task_id: int
    kind: str
    message: str
    payload: Any = None


class CancellationToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    def cancelled(self) -> bool:
        return self._event.is_set()

    def checkpoint(self) -> None:
        if self.cancelled():
            raise InterruptedError("Task cancelled by user.")


def run_powershell(script: str, timeout: int = 20, cancel: CancellationToken | None = None) -> str:
    """
    Execute only scripts authored by registered tools below.
    Do not pass raw user or model-generated shell text to this function.
    """
    if cancel:
        cancel.checkpoint()

    cmd = [
        "powershell.exe",
        "-NoLogo",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy", "RemoteSigned",
        "-Command", script,
    ]
    completed = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        errors="replace",
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    output = (completed.stdout or "").strip()
    error = (completed.stderr or "").strip()
    combined = output
    if error:
        combined = (combined + "\n\nSTDERR:\n" + error).strip()
    if completed.returncode != 0:
        raise RuntimeError(
            f"PowerShell returned exit code {completed.returncode}.\n{combined[:12000]}"
        )
    return combined[:12000] or "(No output)"


def tool_system_health(progress: Callable[[str], None], cancel: CancellationToken) -> str:
    progress("Collecting basic Windows and resource information…")
    cancel.checkpoint()
    script = r"""
$os = Get-CimInstance Win32_OperatingSystem
$cpu = Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average
$memTotalGB = [math]::Round($os.TotalVisibleMemorySize / 1MB, 2)
$memFreeGB = [math]::Round($os.FreePhysicalMemory / 1MB, 2)
$uptime = (Get-Date) - $os.LastBootUpTime
"Computer: $env:COMPUTERNAME"
"Windows: $($os.Caption) (build $($os.BuildNumber))"
"Last boot: $($os.LastBootUpTime)"
"Uptime: $([int]$uptime.TotalDays)d $($uptime.Hours)h $($uptime.Minutes)m"
"CPU load (sample): $([math]::Round($cpu.Average, 0))%"
"RAM total: $memTotalGB GB"
"RAM free: $memFreeGB GB"
"""
    progress("Reading operating-system and memory counters…")
    result = run_powershell(script, timeout=20, cancel=cancel)
    progress("Basic system snapshot collected.")
    return result


def tool_network_diagnostics(progress: Callable[[str], None], cancel: CancellationToken) -> str:
    progress("Checking network adapters…")
    cancel.checkpoint()
    script1 = r"""
"=== ADAPTERS ==="
Get-NetAdapter -ErrorAction SilentlyContinue |
  Select-Object Name, InterfaceDescription, Status, LinkSpeed |
  Format-Table -AutoSize | Out-String -Width 180
"=== IP CONFIGURATION ==="
Get-NetIPConfiguration -ErrorAction SilentlyContinue |
  Select-Object InterfaceAlias, IPv4Address, IPv4DefaultGateway, DNSServer |
  Format-List | Out-String -Width 180
"""
    a = run_powershell(script1, timeout=25, cancel=cancel)
    progress("Checking WLAN service and basic reachability…")
    cancel.checkpoint()
    script2 = r"""
"=== WLAN SERVICE ==="
Get-Service WlanSvc -ErrorAction SilentlyContinue |
  Select-Object Name, Status, StartType | Format-List | Out-String
"=== GATEWAY / DNS QUICK TEST ==="
$cfg = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
  Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
  Select-Object -First 1
if ($cfg) {
  $gw = $cfg.IPv4DefaultGateway.NextHop
  "Gateway: $gw"
  "Gateway ping: " + (Test-Connection -ComputerName $gw -Count 1 -Quiet -ErrorAction SilentlyContinue)
} else {
  "No active IPv4 default gateway found."
}
"DNS resolution example.com: " + [bool](Resolve-DnsName example.com -ErrorAction SilentlyContinue)
"""
    b = run_powershell(script2, timeout=25, cancel=cancel)
    progress("Read-only network checks completed.")
    return a + "\n\n" + b


def tool_open_settings(progress: Callable[[str], None], cancel: CancellationToken) -> str:
    cancel.checkpoint()
    progress("Opening Windows Settings…")
    os.startfile("ms-settings:")
    return "Windows Settings launch requested."


def tool_open_notepad(progress: Callable[[str], None], cancel: CancellationToken) -> str:
    cancel.checkpoint()
    progress("Opening Notepad…")
    subprocess.Popen(
        ["notepad.exe"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )
    return "Notepad launch requested."


TOOLS: dict[str, Callable[[Callable[[str], None], CancellationToken], str]] = {
    "System health snapshot": tool_system_health,
    "Network diagnostics (read-only)": tool_network_diagnostics,
    "Open Windows Settings": tool_open_settings,
    "Open Notepad": tool_open_notepad,
}


class VoxPilotApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("VoxPilot — Local Windows Operator (Foundation)")
        self.root.geometry("820x600")
        self.root.minsize(680, 480)

        self.events: queue.Queue[TaskEvent] = queue.Queue()
        self.next_task_id = 1
        self.active: dict[int, CancellationToken] = {}
        self.worker_lock = threading.Lock()
        self.task_running = False

        self._build_ui()
        self.root.after(100, self._poll_events)
        self._log("Ready. Choose a task. Diagnostics in this build are read-only.")

    def _build_ui(self) -> None:
        outer = ttk.Frame(self.root, padding=12)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="VoxPilot",
            font=("Segoe UI", 20, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text="Local-first Windows AI operator foundation — background tasks, progress, verification-ready tools",
        ).pack(anchor="w", pady=(0, 12))

        controls = ttk.Frame(outer)
        controls.pack(fill="x", pady=(0, 8))

        self.tool_var = tk.StringVar(value=list(TOOLS.keys())[0])
        self.tool_select = ttk.Combobox(
            controls, textvariable=self.tool_var, values=list(TOOLS.keys()),
            state="readonly", width=38
        )
        self.tool_select.pack(side="left", padx=(0, 8))

        self.start_button = ttk.Button(controls, text="Start task", command=self.start_selected)
        self.start_button.pack(side="left", padx=(0, 8))
        self.cancel_button = ttk.Button(controls, text="Cancel active task", command=self.cancel_active)
        self.cancel_button.pack(side="left")

        self.status_var = tk.StringVar(value="Idle")
        ttk.Label(outer, textvariable=self.status_var).pack(anchor="w", pady=(4, 4))
        self.progress = ttk.Progressbar(outer, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 10))

        ttk.Label(outer, text="Task log").pack(anchor="w")
        self.log = tk.Text(outer, wrap="word", height=20, state="disabled", font=("Consolas", 9))
        self.log.pack(fill="both", expand=True, pady=(4, 8))

        footer = ttk.Label(
            outer,
            text="Prototype: no voice or AI planner yet. Do not use on a managed/company PC without authorization.",
            foreground="#555555",
        )
        footer.pack(anchor="w")

    def _log(self, text: str) -> None:
        stamp = time.strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {text}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _emit(self, event: TaskEvent) -> None:
        self.events.put(event)

    def start_selected(self) -> None:
        name = self.tool_var.get()
        tool = TOOLS.get(name)
        if not tool:
            messagebox.showerror("Unknown tool", "That tool is not registered.")
            return

        # One task at a time in this foundation keeps resource use predictable.
        with self.worker_lock:
            if self.task_running:
                messagebox.showinfo("Task running", "A task is already running. Wait or cancel it first.")
                return
            self.task_running = True

        task_id = self.next_task_id
        self.next_task_id += 1
        token = CancellationToken()
        self.active[task_id] = token

        self.status_var.set(f"Starting: {name}")
        self.progress.start(10)
        self.start_button.configure(state="disabled")
        self._log(f"Task #{task_id} started: {name}")

        def report(message: str) -> None:
            self._emit(TaskEvent(task_id, "progress", message))

        def worker() -> None:
            try:
                result = tool(report, token)
                self._emit(TaskEvent(task_id, "success", f"{name} completed.", result))
            except InterruptedError as exc:
                self._emit(TaskEvent(task_id, "cancelled", str(exc)))
            except subprocess.TimeoutExpired:
                self._emit(TaskEvent(task_id, "error", "Timed out. No success is assumed; inspect the task log."))
            except Exception as exc:
                self._emit(TaskEvent(task_id, "error", f"{type(exc).__name__}: {exc}"))
            finally:
                self._emit(TaskEvent(task_id, "finished", "Worker finished."))

        threading.Thread(target=worker, name=f"VoxPilotTask-{task_id}", daemon=True).start()

    def cancel_active(self) -> None:
        if not self.active:
            self._log("No active task to cancel.")
            return
        for token in self.active.values():
            token.cancel()
        self._log("Cancellation requested. A currently running OS command may finish before cancellation takes effect.")

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                if event.kind == "progress":
                    self.status_var.set(event.message)
                    self._log(event.message)
                elif event.kind == "success":
                    self.status_var.set(event.message)
                    self._log(event.message)
                    if event.payload:
                        self._log("----- RESULT -----")
                        self._log(str(event.payload))
                        self._log("------------------")
                elif event.kind == "error":
                    self.status_var.set("Task failed — see log")
                    self._log("ERROR: " + event.message)
                elif event.kind == "cancelled":
                    self.status_var.set("Task cancelled")
                    self._log(event.message)
                elif event.kind == "finished":
                    self.progress.stop()
                    self.start_button.configure(state="normal")
                    self.active.clear()
                    with self.worker_lock:
                        self.task_running = False
                    if self.status_var.get().startswith("Starting:"):
                        self.status_var.set("Idle")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)


def main() -> None:
    if os.name != "nt":
        raise SystemExit("VoxPilot foundation currently supports Windows only.")
    root = tk.Tk()
    try:
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")
    except Exception:
        pass
    VoxPilotApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
