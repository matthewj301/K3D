# Kalico Config Constants Migration Guide

A step-by-step guide for migrating a Klipper/Kalico printer config from hardcoded duplicate values to a structured three-layer deduplication system. This was developed and proven on an Annex K3 build and applies to any Kalico-based printer.

---

## Prerequisites

- **Kalico firmware** (Klipper fork) with `[constants]` support
  - `[constants]` provides config-time `${constants.name}` string substitution, resolved at parse time
  - Only ONE `[constants]` block is allowed per config
- **`[danger_options]`** with `error_on_unused_config_options: False` (recommended during migration so unused constants don't error)
- Familiarity with Kalico's cross-section reference syntax: `${section.option}` (e.g. `${stepper_x.rotation_distance}`)

---

## Architecture: Three Layers

The key insight is that not all duplicated values should be centralized the same way. Hardware profile files (motors, hotends, extruders) are designed to be swapped in and out — centralizing their values in `[constants]` would break that pattern. The solution is three layers:

### Layer 1: `[constants]` — Board-level and tuning values

Values that belong to the **printer build itself**, not to any single swappable component. These live in `printer.cfg` and are referenced as `${constants.name}` from any config file.

**Good candidates:**
- Sensorless homing currents and sensitivity thresholds (tuned per-build)
- Firmware retraction speeds (consistent across hotend swaps)
- Probe movement speeds (bed mesh, z-tilt)
- Filament diameter (1.75 vs 2.85 — build-level choice)
- TMC bus voltages (wired to PSU, not to motor)
- Any value that appears in 2+ files and is NOT tied to a specific swappable part

**Bad candidates (do NOT put in constants):**
- Motor-specific params (run_current, rotation_distance, microsteps) — these belong in the motor profile
- Hotend-specific params (max_temp, sensor_type, pressure_advance) — these belong in the hotend profile
- Extruder-specific params (gear_ratio, full_steps_per_rotation) — these belong in the extruder profile
- Pin assignments — unique per section
- Input shaper values — tuned per-machine, appear once
- SAVE_CONFIG block values — auto-generated

### Layer 2: Cross-section references — Motor/driver deduplication

When multiple steppers use **identical motors** (e.g. 4 XY steppers, 3 Z steppers), designate one section as the source of truth and have the others reference it with `${section.option}`.

```ini
# stepper_x is the source of truth
[stepper_x]
rotation_distance: 40
microsteps: 64
full_steps_per_rotation: 200

# All followers reference stepper_x
[stepper_x1]
rotation_distance: ${stepper_x.rotation_distance}
microsteps: ${stepper_x.microsteps}
full_steps_per_rotation: ${stepper_x.full_steps_per_rotation}
```

This works for TMC driver sections too — note the space-in-section-name syntax:

```ini
[tmc5160 stepper_x]
run_current: 2.1
interpolate: True
sense_resistor: 0.075

[tmc5160 stepper_x1]
run_current: ${tmc5160 stepper_x.run_current}
interpolate: ${tmc5160 stepper_x.interpolate}
sense_resistor: ${tmc5160 stepper_x.sense_resistor}
```

**Key benefit:** When you swap motors, you edit ONE section and all followers update. The motor config file remains self-contained — you can swap `[include motor-a.cfg]` for `[include motor-b.cfg]` and everything works.

### Layer 3: Hardcoded in swappable profiles

Hotend files, extruder files, and motor TMC config files keep their values hardcoded. These files act as drop-in profiles:

```
custom/hotends/chube-air.cfg    ← swap to dragon-hf.cfg
custom/extruders/sherpa_mini.cfg ← swap to galileo-2.cfg
custom/steppers/motors/ldo/tmc5160/42STH48-2804AH.cfg ← swap to different motor
```

Each profile is self-contained with all values needed for that component. The ONLY exception is `filament_diameter` which comes from `${constants.filament_diameter}` since it's a build-level choice, not a hotend property.

### Layer 4 (bonus): `_PRINTER_VARS` for macro magic numbers

Gcode macro bodies can't use `${constants.*}` (that's config-time only). Instead, promote magic numbers to a `[gcode_macro _PRINTER_VARS]` section, accessible at runtime via Jinja:

```ini
[gcode_macro _PRINTER_VARS]
variable_park_front_offset: 5
variable_cooldown_step_wait: 60
gcode:
```

Accessed in macros as:
```jinja
{% set vars = printer["gcode_macro _PRINTER_VARS"] %}
G0 Y{printer.toolhead.axis_minimum.y + vars.park_front_offset}
G4 S{vars.cooldown_step_wait|int}
```

---

## Step-by-Step Migration Process

### Step 1: Audit the config

Before changing anything, understand what you're working with.

```bash
# Find all config files
find . -name "*.cfg" -not -path "./.git/*" | sort

# Find duplicated values — look for the same key:value appearing in multiple files
grep -rn 'rotation_distance:' custom/ printer.cfg
grep -rn 'run_current:' custom/ printer.cfg
grep -rn 'microsteps:' custom/ printer.cfg
grep -rn 'sense_resistor:' custom/ printer.cfg
grep -rn 'max_temp:' custom/ printer.cfg
grep -rn 'sensor_type:' custom/ printer.cfg
grep -rn 'filament_diameter:' custom/ printer.cfg
```

For each duplicated value, classify it:
1. **Same value, same component type, appears N times** → cross-section ref (Layer 2)
2. **Same value, different component types, build-level** → `[constants]` (Layer 1)
3. **Magic number in gcode block** → `_PRINTER_VARS` (Layer 4)
4. **Value in swappable profile file, appears once** → leave hardcoded (Layer 3)

### Step 2: Identify the `[constants]` candidates

Walk through each file group and ask: "If I swapped this hardware, would this value change?"

| Value | Changes on swap? | Layer |
|-------|-----------------|-------|
| `run_current: 2.1` | Yes (motor-specific) | 2 — cross-section ref within motor file |
| `sensorless_y_home_current: 1.2` | No (tuned to frame/belts) | 1 — `[constants]` |
| `voltage: 48` | No (wired to PSU) | 1 — `[constants]` |
| `max_temp: 450` | Yes (hotend-specific) | 3 — hardcoded in hotend profile |
| `filament_diameter: 1.75` | No (build choice) | 1 — `[constants]` |
| Hardcoded `5` in park gcode | N/A (tuning knob) | 4 — `_PRINTER_VARS` |

### Step 3: Add `[constants]` to printer.cfg

Place it near the top of `printer.cfg`, before any sections that reference it. Use descriptive group comments:

```ini
[constants]
# Sensorless homing (tuning values, not motor-specific)
sensorless_x_home_current: 1.4
sensorless_y_home_current: 1.2
sensorless_y_sgt: 0

# Firmware retraction
fw_retract_speed: 60
fw_unretract_speed: 60

# Probe movement speed (bed mesh + z-tilt)
mesh_tilt_speed: 500

# Filament
filament_diameter: 1.75

# TMC autotune bus voltages
xy_bus_voltage: 48
z_bus_voltage: 24
e_bus_voltage: 24
```

**Naming rules:**
- Use lowercase with underscores
- Prefix with category when ambiguous (e.g. `fw_retract_speed` not `retract_speed` to avoid collision with gcode macro variables that may have a `variable_retract_speed` for a different purpose)
- Keep names self-documenting

### Step 4: Convert stepper files to cross-section refs

For each group of identical steppers, pick one as the source of truth (usually the first: `stepper_x`, `stepper_z`). Convert followers:

**Before:**
```ini
[stepper_z]
rotation_distance: 40
gear_ratio: 5:1
microsteps: 64
full_steps_per_rotation: 200

[stepper_z1]
rotation_distance: 40
gear_ratio: 5:1
microsteps: 64
full_steps_per_rotation: 200
```

**After:**
```ini
[stepper_z]
rotation_distance: 40
gear_ratio: 5:1
microsteps: 64
full_steps_per_rotation: 200

[stepper_z1]
rotation_distance: ${stepper_z.rotation_distance}
gear_ratio: ${stepper_z.gear_ratio}
microsteps: ${stepper_z.microsteps}
full_steps_per_rotation: ${stepper_z.full_steps_per_rotation}
```

Do the same for TMC driver sections:

**Before:**
```ini
[tmc2209 stepper_z]
run_current: 1.1
interpolate: True
sense_resistor: 0.11
stealthchop_threshold: 0

[tmc2209 stepper_z1]
run_current: 1.1
interpolate: True
sense_resistor: 0.11
stealthchop_threshold: 0
```

**After:**
```ini
[tmc2209 stepper_z]
run_current: 1.1
interpolate: True
sense_resistor: 0.11
stealthchop_threshold: 0

[tmc2209 stepper_z1]
run_current: ${tmc2209 stepper_z.run_current}
interpolate: ${tmc2209 stepper_z.interpolate}
sense_resistor: ${tmc2209 stepper_z.sense_resistor}
stealthchop_threshold: ${tmc2209 stepper_z.stealthchop_threshold}
```

**Important:** Only cross-reference values that are truly identical across all steppers in the group. Values that intentionally differ per-stepper (like `driver_SGT` for sensorless homing, or `dir_pin` polarity) must stay hardcoded.

### Step 5: Update config files to use `${constants.*}`

Replace hardcoded values with constant references in the appropriate files:

```ini
# In sensorless homing files:
home_current: ${constants.sensorless_x_home_current}

# In firmware retraction section:
retract_speed: ${constants.fw_retract_speed}

# In bed mesh / z-tilt sections:
speed: ${constants.mesh_tilt_speed}

# In hotend profiles (only filament_diameter):
filament_diameter: ${constants.filament_diameter}

# In TMC autotune:
voltage: ${constants.xy_bus_voltage}
```

### Step 6: Add `_PRINTER_VARS` entries

Search macros for hardcoded numbers that should be tunable. Common candidates:

```bash
# Find magic numbers in gcode blocks
grep -n 'G4 S[0-9]' custom/macros/*.cfg
grep -n 'G4 P[0-9]' custom/macros/*.cfg
grep -n 'DURATION=[0-9]' custom/macros/*.cfg
grep -n 'axis_minimum.*+.*[0-9]' custom/macros/*.cfg
grep -n 'axis_maximum.*-.*[0-9]' custom/macros/*.cfg
grep -n 'MAX_DEVIATION' custom/macros/*.cfg
```

Add them to `_PRINTER_VARS` with descriptive names and unit comments:

```ini
[gcode_macro _PRINTER_VARS]
# ... existing vars ...

# Park position offsets
variable_park_front_offset: 5              # mm from Y axis_min for front park
variable_park_rear_margin: 10              # mm inset from axis limits for rear park

# Cooldown sequence
variable_cooldown_step_wait: 60            # seconds to wait at each cooldown step
variable_cooldown_final_temp: 40           # deg C final bed temp in stepped cooldown
gcode:
```

### Step 7: Update macros to use `_PRINTER_VARS`

**Before:**
```jinja
G0 Y{printer.toolhead.axis_minimum.y + 5} F{travel_speed}
G4 S60
```

**After:**
```jinja
{% set vars = printer["gcode_macro _PRINTER_VARS"] %}
G0 Y{printer.toolhead.axis_minimum.y + vars.park_front_offset} F{travel_speed}
G4 S{vars.cooldown_step_wait|int}
```

If the macro already has `{% set vars = printer["gcode_macro _PRINTER_VARS"] %}`, just use `vars.variable_name`. If not, add it at the top of the gcode block.

---

## Verification Checklist

Run these after all changes:

```bash
# 1. All referenced constants are defined
grep -rohn '\${constants\.\([a-z0-9_]*\)}' custom/ printer.cfg \
  | sed 's/.*\${constants\.\([a-z0-9_]*\)}.*/\1/' | sort -u > /tmp/refs.txt

sed -n '/^\[constants\]/,/^\[/p' printer.cfg \
  | grep -v '^#' | grep -v '^\[' | grep -v '^$' \
  | sed 's/:.*//' | sort -u > /tmp/defs.txt

# Show any referenced but not defined (should be empty):
comm -23 /tmp/refs.txt /tmp/defs.txt

# Show any defined but not referenced (potential dead constants):
comm -13 /tmp/refs.txt /tmp/defs.txt

# 2. All cross-section refs point to valid sections
grep -rn '\${[a-z]' custom/ | grep -v constants | grep -v '^#'
# Manually verify each referenced section exists

# 3. No orphaned hardcoded values in converted files
# (spot-check — values that should now be cross-refs or constants)
grep -rn 'run_current: 2.1' custom/   # should only appear once (source of truth)
grep -rn 'rotation_distance: 40' custom/  # should only appear in source-of-truth steppers

# 4. _PRINTER_VARS references resolve
grep -rn 'vars\.' custom/macros/ | sed 's/.*vars\.\([a-z_]*\).*/\1/' | sort -u > /tmp/var_refs.txt
grep 'variable_' printer.cfg | sed 's/.*variable_\([a-z_]*\):.*/\1/' | sort -u > /tmp/var_defs.txt
comm -23 /tmp/var_refs.txt /tmp/var_defs.txt  # should be empty
```

### Functional testing (after deploying to printer)

1. Restart Klipper/Kalico — check logs for config parse errors
2. Home all axes — sensorless homing uses constants
3. Run Z_TILT_ADJUST — uses mesh_tilt_speed constant
4. Run BED_MESH_CALIBRATE — uses mesh_tilt_speed constant
5. Heat hotend — verifies extruder section merging works
6. Run PARK_FRONT, PARK_REAR — uses _PRINTER_VARS offsets
7. Short test print — exercises firmware retraction, purge, full workflow

---

## Common Pitfalls

### 1. Name collisions between `[constants]` and `_PRINTER_VARS`

`[constants]` uses bare names (`retract_speed: 60`). `_PRINTER_VARS` uses `variable_` prefix (`variable_retract_speed: 25`). If both exist for similar concepts, use a distinguishing prefix in constants:

```ini
[constants]
fw_retract_speed: 60        # firmware retraction (config-level)

[gcode_macro _PRINTER_VARS]
variable_retract_speed: 25   # end-of-print G1 retract (runtime macro)
```

### 2. Centralizing swappable hardware values

**Don't do this:**
```ini
[constants]
xy_run_current: 2.1          # BAD — this is motor-specific
hotend_max_temp: 450          # BAD — this is hotend-specific
extruder_gear_ratio: 50:8     # BAD — this is extruder-specific
```

These values live in their respective profile files. If you swap motors from LDO-2804AH to LDO-2504AC, you swap the motor config file — you don't want to also have to update `printer.cfg`.

### 3. Raw GPIO pins bypassing board_pins aliases

If the MCU config defines `[board_pins]` aliases (e.g. `e_dir_pin=PC1`), always use the alias in config files, not the raw GPIO:

```ini
# BAD — bypasses alias, breaks if MCU changes
dir_pin: !PC1

# GOOD — uses board_pins alias
dir_pin: !e_dir_pin
```

### 4. Klipper section merging

Multiple files can contribute to the same `[section]`. For example, `[extruder]` might get `sensor_type` from the hotend file, `rotation_distance` from the extruder file, and `control` from SAVE_CONFIG. This is by design — just make sure no key appears in more than one file (last-loaded wins silently).

### 5. `${constants.*}` doesn't work in gcode blocks

Constant substitution is config-parse-time only. Inside `gcode:` blocks, use `_PRINTER_VARS` accessed via Jinja:

```ini
# This does NOT work:
gcode:
  G1 F${constants.retract_speed}

# This works:
gcode:
  {% set vars = printer["gcode_macro _PRINTER_VARS"] %}
  G1 F{vars.retract_speed}
```

### 6. Cross-section refs to sections with spaces

TMC driver sections have spaces in their names. The syntax works but looks unusual:

```ini
run_current: ${tmc5160 stepper_x.run_current}
```

### 7. Commented-out alternative configs

If a file has commented-out alternatives (e.g. leadscrew vs belted Z), leave them hardcoded. Cross-section refs in comments would be confusing:

```ini
# 5:1 Belted Z (active)
rotation_distance: 40
gear_ratio: 5:1

# TR12x2 Leadscrew (alternative — leave hardcoded)
#rotation_distance: 2
#gear_ratio: 2:1
```

---

## File Organization Reference

Typical structure after migration:

```
printer.cfg                          # [constants], [gcode_macro _PRINTER_VARS], [heater_bed], etc.
custom/
├── mcus/
│   └── octopus-pro.cfg              # [mcu], [board_pins] with pin aliases
├── k3/                              # (or your printer name)
│   ├── k3.cfg                       # kinematic config, [printer] section
│   ├── steppers/
│   │   ├── xy/steppers.cfg          # stepper_x (source), x1/y/y1 (cross-refs)
│   │   └── z/steppers.cfg           # stepper_z (source), z1/z2 (cross-refs)
│   ├── sensorless-homing/
│   │   ├── sensorless-homing-x.cfg  # uses ${constants.sensorless_x_home_current}
│   │   └── sensorless-homing-y.cfg  # uses ${constants.sensorless_y_*}
│   └── z-tilt.cfg                   # uses ${constants.mesh_tilt_speed}
├── steppers/motors/                  # SWAPPABLE — motor TMC profiles
│   ├── ldo/tmc5160/42STH48-2804AH.cfg  # x source, x1/y/y1 cross-ref
│   ├── ldo/tmc2209/42STH48-2504AC.cfg  # z source, z1/z2 cross-ref
│   └── moons/.../24v-0.85a-e.cfg        # single section, hardcoded
├── extruders/                        # SWAPPABLE — extruder profiles
│   └── sherpa_mini-8t.cfg            # hardcoded mechanical params
├── hotends/                          # SWAPPABLE — hotend profiles
│   ├── chube-air.cfg                 # hardcoded except filament_diameter
│   └── tk.cfg                        # hardcoded except filament_diameter
├── probes/
│   └── beacon.cfg                    # uses ${constants.mesh_tilt_speed}
├── fans/                             # fan configs
├── sensors/                          # temperature sensors
├── tuning/
│   └── tmc_autotune.cfg              # uses ${constants.*_bus_voltage}
└── macros/
    ├── print.cfg                     # uses _PRINTER_VARS
    ├── park.cfg                      # uses _PRINTER_VARS
    ├── heating_cooling.cfg           # uses _PRINTER_VARS
    └── utils.cfg                     # uses _PRINTER_VARS
```

---

## Quick Decision Flowchart

When you encounter a duplicated or hardcoded value, ask these questions in order:

1. **Is it in a gcode block?** → `_PRINTER_VARS` (Layer 4)
2. **Does it change when you swap a motor/hotend/extruder?** → Hardcoded in profile (Layer 3)
3. **Is it the same value across multiple sections of the same motor type?** → Cross-section ref to source section (Layer 2)
4. **Is it a build-level value used in 2+ files?** → `[constants]` (Layer 1)
5. **Does it appear only once?** → Leave it alone.

---

## Example: Full Conversion of a Z Stepper Group

**Starting state** (3 identical Z steppers, all hardcoded):

```ini
[stepper_z]
step_pin: z0_step_pin
dir_pin: z0_dir_pin
enable_pin: !z0_enable_pin
rotation_distance: 40
gear_ratio: 5:1
microsteps: 64
full_steps_per_rotation: 200
endstop_pin: probe:z_virtual_endstop
position_max: 170
position_min: -6

[stepper_z1]
step_pin: z1_step_pin
dir_pin: z1_dir_pin
enable_pin: !z1_enable_pin
rotation_distance: 40
gear_ratio: 5:1
microsteps: 64
full_steps_per_rotation: 200

[stepper_z2]
step_pin: z2_step_pin
dir_pin: !z2_dir_pin
enable_pin: !z2_enable_pin
rotation_distance: 40
gear_ratio: 5:1
microsteps: 64
full_steps_per_rotation: 200
```

**Final state:**

```ini
[stepper_z]
# Z0 — front left (MOTOR 5 on Octopus Pro)
step_pin: z0_step_pin
dir_pin: z0_dir_pin
enable_pin: !z0_enable_pin
rotation_distance: 40
gear_ratio: 5:1
microsteps: 64
full_steps_per_rotation: 200
endstop_pin: probe:z_virtual_endstop
position_max: 170
position_min: -6

[stepper_z1]
# Z1 — rear (MOTOR 6 on Octopus Pro)
step_pin: z1_step_pin
dir_pin: z1_dir_pin
enable_pin: !z1_enable_pin
rotation_distance: ${stepper_z.rotation_distance}
gear_ratio: ${stepper_z.gear_ratio}
microsteps: ${stepper_z.microsteps}
full_steps_per_rotation: ${stepper_z.full_steps_per_rotation}

[stepper_z2]
# Z2 — front right (MOTOR 7 on Octopus Pro)
step_pin: z2_step_pin
dir_pin: !z2_dir_pin
enable_pin: !z2_enable_pin
rotation_distance: ${stepper_z.rotation_distance}
gear_ratio: ${stepper_z.gear_ratio}
microsteps: ${stepper_z.microsteps}
full_steps_per_rotation: ${stepper_z.full_steps_per_rotation}
```

**What changed:** Mechanical params (rotation_distance, gear_ratio, microsteps, full_steps_per_rotation) on z1/z2 now reference stepper_z. Pin assignments and position limits stay hardcoded (unique per stepper). Dir pin polarity (`!z2_dir_pin`) stays hardcoded (intentionally different on z2).
