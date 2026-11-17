# Open issues (assignable)

Unlike audits and historical notes, entries here ARE assignments. Fix, then delete the
entry in the same change. Shared-macro issues live in the fleet master's
`~/git/doomcube/docs/open-issues.md`; fix those there first, then port.

## MPC

- **Manual `_SET_MPC_MATERIAL` input handling differs from the fleet** (2026-11-16, review
  of the FILAMENT_DENSITY change). K3D's Python macro raises on a non-numeric
  `FILAMENT_DENSITY`, while Doomcube/Rat Race silently use 0.0; `nan` passes here too.
  Tracked as a fleet issue in the master's open-issues.md; port the master's fix here.
