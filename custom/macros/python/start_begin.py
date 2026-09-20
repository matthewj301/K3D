vars = printer["gcode_macro _PRINTER_VARS"]
bed_temp = float(params.get("BED_TEMP", 0))
hotend_temp = float(params.get("HOTEND_TEMP", 0))
chamber_target_temp = float(params.get("TARGET_CHAMBER_TEMP", 0))
mat = params.get("MATERIAL", vars["default_material"]).upper()
# Fire bed heat before homing so it soaks during MAYBE_HOME + SYNC_MOTORS. Bed only:
# the first Z home is an intentionally-cold Beacon contact probe, so no early M104 here.
emit(f"M140 S{bed_temp}")
emit("_CLEAR_PRINT_SKEW")
emit("UPDATE_DELAYED_GCODE ID=FILTER_DELAYED_STOP DURATION=0")
emit("MAYBE_HOME")
# Skip motor sync if phases are still valid from a prior print (motors kept energized).
ms = printer["motors_sync"] if "motors_sync" in printer else {}
ms_applied = bool(ms["applied"]) if "applied" in ms else False
if not (ms_applied and "xyz" in printer["toolhead"]["homed_axes"]):
  emit("SYNC_MOTORS")
else:
  emit('RESPOND MSG="Motor sync still valid - skipping"')
emit(f'SAVE_VARIABLE VARIABLE=current_material VALUE=\'"{mat}"\'')
emit("CLEAR_PAUSE")
emit("RESET_MULTIPLIERS")
emit("G90")
emit("BED_MESH_CLEAR")
emit("SET_GCODE_OFFSET Z=0")
if "_BEACON_SET_NOZZLE_TEMP_OFFSET" in printer["gcode"]["commands"]:
  emit("_BEACON_SET_NOZZLE_TEMP_OFFSET RESET=True")
has_beacon = "beacon" in printer["configfile"]["settings"]
