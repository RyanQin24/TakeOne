# Supplied tracking scripts

These three Python files are byte-preserved copies, not refactored implementations.

| File | Source | SHA-256 |
|---|---|---|
| robocart_tracking.py | First user attachment, d9420a9b-a10d-4289-8a37-50183aa54a8f | 9a743fd24036d5ea531d9db2f225443a518ffcfc8df409efd7e3387abc24dcba |
| roboarm_tracking.py | Second user attachment, 305d17c0-6447-44bc-aef8-4af0b01f7142 | f467fe7f4479c06a5775731a7667d62a8c2f200c06874c8bdac8d0fbb8dae571 |
| motor_UART.py | Existing C:/Users/nonst/Documents/Python/TakeOne/motor_UART.py | 33db8afd69fa7024c545874c4c3f1aa5e1cadcf2334f9aeed9823e58e4832e92 |

Do not format these files. Ruff excludes this directory. The managed launcher
checks their hashes before execution. See [live tracking](../../docs/live-tracking.md)
for the UI, optional arm adapters and shutdown behavior.

Importing or directly running either tracking script executes its hardware setup.
The non-actuating check is `scripts/Check-Tracking.ps1`; normal operation is
through the simulation UI's explicit **Start live tracking** button.
