if printer['gcode_macro _PRINT_START_STATE']['active']:
    raise_error('Startup is heating; use TA_CHAMBER_STOP or CANCEL_PRINT to stop')
if printer['pause_resume']['is_paused']:
    respond_info('Already paused')
else:
    vars = printer['gcode_macro _PRINTER_VARS']
    set_gcode_variable('RESUME', 'printing_target_temp', printer['extruder']['target'])
    if 'mmu' in printer and printer['mmu']['enabled']:
        emit('_MMU_SAVE_POSITION')
        emit('PAUSE_BASE')
        emit('_MMU_PARK OPERATION="pause"')
    else:
        length = float(vars['end_retract_length']) if printer['extruder']['can_extrude'] else 0
        set_gcode_variable('RESUME', 'retracted_length', length)
        emit('PAUSE_BASE')
        emit('SAVE_GCODE_STATE NAME=_PAUSE_EXTRUSION')
        emit('M83')
        if length > 0:
            emit('G1 E-%s F%s' % (length, float(vars['retract_speed'])*60))
        emit('RESTORE_GCODE_STATE NAME=_PAUSE_EXTRUSION')
        emit('TURN_PART_COOLING_FAN_OFF')
        accel = printer['toolhead']['max_accel']
        emit('SET_VELOCITY_LIMIT ACCEL=%s' % float(vars['travel_accel']))
        try:
            emit('PICK_PARK_LOCATION')
        finally:
            emit('SET_VELOCITY_LIMIT ACCEL=%s' % accel)
        emit('SAVE_GCODE_STATE NAME=PAUSEPARK')
        # Preserve K3's established hotend-off and four-hour pause policy.
        emit('M104 S0')
        emit('SET_IDLE_TIMEOUT TIMEOUT=%s' % float(vars['pause_idle_timeout']))
