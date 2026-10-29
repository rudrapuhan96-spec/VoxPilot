# VoxPilot foundation test plan

Run these tests on a non-critical Windows 10/11 machine first.

1. Launch with `py -3 voxpilot\app.py`; confirm UI appears.
2. Start System health snapshot; move/resize the window during collection. UI should remain responsive.
3. Start Network diagnostics; confirm progress messages appear and no CMD window flashes.
4. Start Open Windows Settings; confirm Settings opens visibly.
5. Start Open Notepad; confirm Notepad opens visibly.
6. Start a second task while one is running; app should decline parallel execution.
7. Click Cancel during diagnostics; app should request cancellation and explain that an OS subprocess may finish first.
8. Check Task Manager during idle and task execution; record RAM/CPU on the target PC.
9. Confirm no admin elevation is requested for read-only diagnostics.
10. Verify failures/timeouts are shown as failures, never as successful completion.

This test plan is not a substitute for security review, compatibility testing, or recovery testing.
