params = printer['gcode_macro _PRINT_START_STATE']['params']
vars = printer['gcode_macro _PRINTER_VARS']
hotend_temp = float(params['HOTEND_TEMP'])
mat = params.get('MATERIAL', vars['default_material']).upper()
has_beacon = 'beacon' in printer['configfile']['settings']
if has_beacon:
  emit('G28 Z METHOD=CONTACT CALIBRATE=1')
else:
  emit('G28 Z')
if "quad_gantry_level" in printer["configfile"]["settings"]:
  emit("QUAD_GANTRY_LEVEL")
elif "z_tilt" in printer["configfile"]["settings"] or "z_tilt_ng" in printer["configfile"]["settings"]:
  emit("Z_TILT_ADJUST")
else:
  emit('RESPOND MSG="No gantry leveling module detected - skipping."')
if has_beacon:
  # Wipe the nozzle and take the authoritative Z=0 home BEFORE meshing.
  # WIPE_NOZZLE contact-probes at the front of the bed (Y=3), which is
  # outside the mesh region (mesh_min Y=30). If a mesh were active, the
  # extrapolated edge compensation would shift the nozzle's start height
  # and the contact move would bottom out before touching the bed
  # ("No trigger on probe after full movement"). The gantry is already
  # level (Z_TILT_ADJUST ran); this contact home sets the Z=0 that
  # first-layer height depends on, so the nozzle must be clean.
  emit("WIPE_NOZZLE")
  emit("G28 Z METHOD=CONTACT CALIBRATE=0")
if "bed_mesh" in printer["configfile"]["settings"]:
  # Mesh last, anchored to the clean contact Z=0 via zero_reference_position.
  emit('RESPOND MSG="Starting bed mesh calibration..."')
  emit("BED_MESH_CALIBRATE ADAPTIVE=1")
  emit(f"BED_MESH_CHECK MAX_DEVIATION={vars['max_mesh_deviation']}")
if has_beacon:
  emit(f"M104 S{hotend_temp}")
emit(f'SET_DISPLAY_TEXT MSG="Heating hotend to {hotend_temp}c"')
if "SMART_PARK" in printer["gcode"]["commands"]:
  emit("SMART_PARK")
else:
  emit("PICK_PARK_LOCATION")
extruder_cfg = printer["configfile"]["settings"].get("extruder", {})
if extruder_cfg.get("control", "") == "mpc":
  emit(f'_SET_MPC_MATERIAL MATERIAL="{mat}"')
emit(f"M109 S{hotend_temp}")
commands = printer['gcode']['commands']
if 'T0' in commands and ('mmu' not in printer or printer['mmu']['enabled']):
  emit('T%d' % int(float(params.get('TOOL', 0))))
emit('_PRINT_START_CHECK_READY')
if "_BEACON_SET_NOZZLE_TEMP_OFFSET" in printer["gcode"]["commands"]:
  emit('RESPOND MSG="Setting Beacon thermal expansion compensation"')
  emit("_BEACON_SET_NOZZLE_TEMP_OFFSET")
if "LINE_PURGE" in printer["gcode"]["commands"]:
  emit('RESPOND MSG="Starting line purge..."')
  emit("LINE_PURGE")
else:
  emit('RESPOND MSG="Starting fallback line purge..."')
  emit(f"_FALLBACK_PURGE LENGTH={vars['purge_line_length']} SPEED={vars['purge_speed']}")
emit("MAYBE_LOAD_SKEW_CORRECTION")
emit('RESPOND MSG="Starting Print..."')
emit("SAVE_VARIABLE VARIABLE=is_printing_gcode VALUE=True")
emit("G90")
