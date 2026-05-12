# Kalico Python Macros Migration Guide

A step-by-step guide for converting Klipper/Kalico gcode_macros from Jinja2 templates to Kalico's built-in Python macro framework. Developed and proven on the K3D config, applicable to any Kalico-based printer that shares the same macro patterns.

---

## Prerequisites

- **Kalico firmware** with Python macro support (`!` prefix lines and `!!include`)
- `RELOAD_GCODE_MACROS` command available (replaces `[dynamicmacros]` plugin for hot-reload)
- Familiarity with the existing macro structure: `_PRINTER_VARS`, material presets, Beacon integration

---

## Key Concepts

### Syntax

Python macros use `!` prefixed lines instead of `{% %}` Jinja2 blocks:

```ini
# Jinja2 (before)
[gcode_macro MY_MACRO]
gcode:
  {% set vars = printer["gcode_macro _PRINTER_VARS"] %}
  {% set speed = (vars.travel_speed|float * 60)|int %}
  {% if printer.extruder.can_extrude %}
    G1 E-5 F{speed}
  {% endif %}

# Python (after)
[gcode_macro MY_MACRO]
gcode:
  !vars = printer["gcode_macro _PRINTER_VARS"]
  !speed = int(float(vars.travel_speed) * 60)
  !if printer.extruder.can_extrude:
  !  emit(f"G1 E-5 F{speed}")
```

### Rules

1. **Cannot mix Python and Jinja2 in the same macro** — pick one per macro
2. **Python indentation goes after the `!`** — the `!` is always at the same column, Python indent follows it
3. **`emit()` queues G-code** — it does NOT block. Use `wait_moves()` to block until the move queue drains
4. **`respond_info()` is immediate** — executes during macro evaluation, not queued. Use `emit('RESPOND MSG="..."')` for messages that should appear in sequence with G-code
5. **`RETURN` exits the macro** — uppercase, bare keyword (not Python's `return`)
6. **`math` is available** — Kalico injects the `math` module into the Python macro namespace, no import needed
7. **`delayed_gcode` and `idle_timeout` sections cannot use Python** — they stay Jinja2

### External Python Files

For complex macros (40+ lines), externalize the Python code:

```ini
[gcode_macro COMPLEX_MACRO]
gcode: !!include python/complex_macro.py
```

The path is relative to the `.cfg` file containing the macro. The `.py` file contains plain Python (no `!` prefix needed). Place external files in a `python/` subdirectory under your macros directory.

---

## Available API in Python Macros

| Function | Purpose |
|----------|---------|
| `emit("GCODE")` | Queue a G-code command for execution |
| `respond_info("msg")` | Send immediate console message (// prefix) |
| `set_gcode_variable("MACRO", "var", val)` | Set a macro variable at runtime |
| `wait_moves()` | Block until all queued moves complete |
| `sleep(seconds)` | Sleep for N seconds |
| `wait_until(condition)` | Block until condition is true |
| `wait_while(condition)` | Block while condition is true |
| `RETURN` | Exit macro early (bare keyword) |
| `printer` | Printer state object (same as Jinja2) |
| `params` | Dict of macro parameters (uppercase string keys) |
| `own_vars` | Access to this macro's `variable_*` declarations |
| `math` | Python math library (pre-injected) |

---

## What to Convert vs Leave Alone

### Convert (high value)

| Pattern | Why |
|---------|-----|
| Recursive self-calling macros (e.g., chamber heating loops) | Replace with `while` + `wait_moves()` — the single biggest win |
| Heavy conditional branching (PRINT_START, COOLDOWN) | Python if/elif/else is much cleaner than nested `{% if %}` |
| Dictionary lookups (MPC material properties) | Native Python dicts with `.get()` replace Jinja2 dict literals |
| Math-heavy macros (thermal expansion) | `min()`, `max()`, `abs()`, f-string formatting |
| Material-aware logic with list membership | `material in warp_list` after `.split(",")` — fixes substring-match bugs |

### Leave as Jinja2 (no value in converting)

| Pattern | Why |
|---------|-----|
| Fan wrappers (1-3 lines, conditional SET_FAN_SPEED) | Too simple to benefit |
| G-code command wrappers (CANCEL_PRINT, M600) | Trivial delegators |
| State reset macros (RESET_MULTIPLIERS) | Just emit a few G-code lines |
| Variable-only macros (_PRINTER_VARS, BEACON_VARS) | No gcode section to convert |
| `delayed_gcode` / `idle_timeout` blocks | Cannot use Python (different section type) |

---

## Migration Patterns

### Pattern 1: Simple conditional → Python if/else

```ini
# BEFORE (Jinja2)
gcode:
  {% set vars = printer["gcode_macro _PRINTER_VARS"] %}
  {% if "beacon" in printer.configfile.settings %}
    G28 Z METHOD=CONTACT CALIBRATE=1
  {% else %}
    G28 Z
  {% endif %}

# AFTER (Python)
gcode:
  !vars = printer["gcode_macro _PRINTER_VARS"]
  !if "beacon" in printer.configfile.settings:
  !  emit("G28 Z METHOD=CONTACT CALIBRATE=1")
  !else:
  !  emit("G28 Z")
```

### Pattern 2: Feature detection

```ini
# BEFORE (Jinja2)
{% if printer.configfile.config["gcode_macro SMART_PARK"] is defined %}
    SMART_PARK
{% endif %}

# AFTER (Python) — use gcode.commands for cleaner checks
!if "SMART_PARK" in printer.gcode.commands:
!  emit("SMART_PARK")
```

### Pattern 3: Dictionary lookups (MPC materials)

```ini
# BEFORE (Jinja2)
{% set density_map = {"PLA": 1.24, "ABS": 1.04, "ASA": 1.07} %}
{% set density = density_map[material] if material in density_map else 1.20 %}

# AFTER (Python)
!density_map = {"PLA": 1.24, "ABS": 1.04, "ASA": 1.07}
!density = density_map.get(material, 1.20)
```

### Pattern 4: Recursive loop → while + wait_moves()

This is the highest-value conversion. Chamber heating macros typically use a recursive self-calling pattern because Jinja2 can't do blocking loops:

```ini
# BEFORE (Jinja2) — 4 separate macros, recursive self-call
[gcode_macro TA_CHAMBER_CYCLE]
gcode:
  {% if cycle >= max_cycles %}
    ...abort...
  {% else %}
    {% if at_target %}
      ...done...
    {% else %}
      ...emit pattern moves...
      G4 P{wait_ms}
      TA_CHAMBER_CYCLE SENSOR="{sensor}" TARGET={target} CYCLE={cycle + 1}
    {% endif %}
  {% endif %}
```

```python
# AFTER (Python) — single macro with proper loop
# In chamber_heating.py (loaded via !!include):

wait_moves()  # Wait for setup moves before entering loop

for cycle in range(max_cycles):
    # Check stop flag — reads LIVE state after wait_moves()
    if int(printer["gcode_macro TA_CHAMBER_STATE"].stop) == 1:
        emit("TURN_PART_COOLING_FAN_OFF")
        respond_info("Chamber mixing aborted by user")
        RETURN

    # Check temperature — LIVE reading, not template-time snapshot
    if printer[sensor_key].temperature >= chamber_target:
        emit(f"M190 S{bed_target}")
        emit(f"M109 S{hotend_target}")
        emit("TURN_PART_COOLING_FAN_OFF")
        respond_info(f"Chamber reached {chamber_target}C")
        RETURN

    # ... emit pattern moves ...
    wait_moves()  # Block until moves complete
    sleep(interval_s)  # Pace between cycles
```

The critical improvement: `wait_moves()` makes the loop truly blocking, so `printer[sensor_key].temperature` returns a **live reading** each iteration instead of a single snapshot taken at template expansion time.

### Pattern 5: Stepped cooldown with for loop

```ini
# BEFORE (Jinja2) — all G-code emitted at template time
{% set cooldown_steps = [(bed_temp * 0.8)|int, (bed_temp * 0.5)|int, vars.cooldown_final_temp|int] %}
{% for temp in cooldown_steps %}
    M190 S{temp}
    G4 S{vars.cooldown_step_wait|int}
{% endfor %}

# AFTER (Python) — cleaner, same behavior (M190 is inherently blocking)
!cooldown_steps = [int(bed_temp * 0.8), int(bed_temp * 0.5), int(vars.cooldown_final_temp)]
!for temp in cooldown_steps:
!  emit(f'RESPOND MSG="Bed cooling to {temp}C..."')
!  emit(f"M190 S{temp}")
!  emit(f"G4 S{int(vars.cooldown_step_wait)}")
```

### Pattern 6: Boolean config variable checks

```ini
# BEFORE (Jinja2) — convoluted because Jinja2 bool handling is fragile
{% set enabled = true if printer["gcode_macro BEACON_VARS"].beacon_contact_expansion_compensation|default(false)|lower == 'true' else false %}

# AFTER (Python) — Klipper variable_* booleans are native Python bools
!enabled = bool(printer["gcode_macro BEACON_VARS"].beacon_contact_expansion_compensation)
```

### Pattern 7: Accessing saved variables

```ini
# BEFORE (Jinja2)
{% set svv = printer.save_variables.variables %}
{% set material = svv.current_material|string|upper %}
{% set coefficient = svv.nozzle_expansion_coefficient|default(0)|float %}

# AFTER (Python)
!svv = printer.save_variables.variables
!material = str(svv.current_material).upper()
!coefficient = float(svv.get("nozzle_expansion_coefficient", 0))
```

### Pattern 8: Material list membership (bugfix)

```ini
# BEFORE (Jinja2) — substring match bug: "PC" matches "PC-CF"
{% set warp_materials = vars.warp_prone_materials|string|upper %}
{% set needs_cooldown = True if material in warp_materials else False %}

# AFTER (Python) — split into list for exact match
!warp_materials = str(vars.warp_prone_materials).upper().split(",")
!needs_cooldown = material in warp_materials
```

---

## Removing `[dynamicmacros]` Dependency

If the printer config uses the `[dynamicmacros]` plugin for hot-reload:

1. Delete the `[dynamicmacros]` config section and its generated `.dynamicmacros.cfg` shim file
2. Remove `[include .dynamicmacros.cfg]` from `printer.cfg`
3. Replace `SET_DYNAMIC_VARIABLE` with `SET_GCODE_VARIABLE` (Jinja2) or `set_gcode_variable()` (Python)
4. Move macros from the `dynamic_macros/` directory into the main `macros/` directory
5. Use Kalico's native `RELOAD_GCODE_MACROS` for hot-reload

---

## File Organization

```
custom/macros/
  python/                    # External Python files for complex macros
    chamber_heating.py       # TA_CHAMBER_HEAT loop logic (!!include)
  chamber_heating.cfg        # Chamber heating macro declarations
  print.cfg                  # PRINT_START/END, PAUSE/RESUME (inline !)
  heating_cooling.cfg        # PREHEAT, COOLDOWN_SEQUENCE (inline !)
  thermal_expansion_compensation.cfg  # Beacon suite (inline !)
  fans.cfg                   # Fan wrappers (stays Jinja2)
  park.cfg                   # Parking macros (stays Jinja2)
  homing.cfg                 # Homing logic (stays Jinja2)
  utils.cfg                  # Reset/utility wrappers (stays Jinja2)
```

---

## Verification Checklist

After each macro conversion:

- [ ] Run `RELOAD_GCODE_MACROS` (no firmware restart needed for Python changes)
- [ ] Invoke the macro manually from the console with test parameters
- [ ] Check Klipper logs for Python exceptions (they show full tracebacks)
- [ ] For chamber heating: test `TA_CHAMBER_STOP` while the loop is running
- [ ] For cooldown: test both `QUICK=0` (fast) and `QUICK=1` (stepped) paths
- [ ] For PRINT_START: run a test print with your default material
- [ ] Verify `RELOAD_GCODE_MACROS` replaces `[dynamicmacros]` hot-reload

### Smoke Test Macro

Create this first to validate the Python macro framework works on your Kalico build:

```ini
[gcode_macro _TEST_PYTHON]
gcode:
  !vars = printer["gcode_macro _PRINTER_VARS"]
  !respond_info(f"travel_speed = {vars.travel_speed}")
  !respond_info(f"params = {params}")
  !emit("M117 Python macros work")
```

Run `_TEST_PYTHON` from the console. If it works, proceed with the migration.

---

## Common Pitfalls

1. **Don't mix `!` and `{% %}` in the same macro** — Kalico will error. Pick one language per macro.
2. **`emit()` is non-blocking** — if you need to read printer state after moves complete, call `wait_moves()` first.
3. **`respond_info()` fires immediately** — use `emit('RESPOND MSG="..."')` if you want the message to appear in sequence with queued G-code.
4. **String params are always strings** — `params.get("BED_TEMP", 0)` returns the string `"110"`, not int. Always cast: `float(params.get("BED_TEMP", 0))`.
5. **`RETURN` is not `return`** — it's a Kalico keyword that exits the macro. Uppercase, no parentheses.
6. **`!!include` paths are relative to the .cfg file** — not the Klipper config root.
7. **`variable_*` names must be lowercase** — Klipper enforces this for macro variables.
