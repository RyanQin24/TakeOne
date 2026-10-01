"""Retired synthetic host benchmark. Never opens a port or substitutes hardware."""

raise SystemExit(
    "The synthetic cart benchmark is retired. Use python -m takeone.cart.cli check "
    "--plan <prepared-plan.json> for offline arithmetic, or the scoped software tests. "
    "Measure real host timing only through the explicitly supervised real-device workflow."
)
