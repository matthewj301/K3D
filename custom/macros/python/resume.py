if printer['gcode_macro _PRINT_START_STATE']['active']:
    raise_error('Startup is heating; use TA_CHAMBER_STOP or CANCEL_PRINT to stop')
if not printer['pause_resume']['is_paused']:
    raise_error('RESUME: printer is not paused')
vars = printer['gcode_macro _PRINTER_VARS']
resume = printer['gcode_macro RESUME']
if resume['printing_target_temp'] > 0:
    emit('M109 S%s' % resume['printing_target_temp'])
if 'mmu' in printer and printer['mmu']['enabled']:
    if '_BEACON_SET_NOZZLE_TEMP_OFFSET' in printer['gcode']['commands']:
        emit('_BEACON_SET_NOZZLE_TEMP_OFFSET')
    emit('RESUME_BASE')
else:
    # Native Python emit executes synchronously; this is a fresh status read after M109.
    length = float(resume['retracted_length'])
    if length > 0 and not printer['extruder']['can_extrude']:
        raise_error('RESUME: nozzle is still too cold to unretract')
    accel = printer['toolhead']['max_accel']
    emit('SET_VELOCITY_LIMIT ACCEL=%s' % float(vars['travel_accel']))
    try:
        emit('RESTORE_GCODE_STATE NAME=PAUSEPARK MOVE=1 MOVE_SPEED=%s' % (float(vars['travel_speed'])/2))
        if '_BEACON_SET_NOZZLE_TEMP_OFFSET' in printer['gcode']['commands']:
            emit('_BEACON_SET_NOZZLE_TEMP_OFFSET')
        if length > 0:
            emit('SAVE_GCODE_STATE NAME=_RESUME_EXTRUSION')
            emit('M83')
            emit('G1 E%s F%s' % (length,float(vars['retract_speed'])*60))
            emit('RESTORE_GCODE_STATE NAME=_RESUME_EXTRUSION')
            set_gcode_variable('RESUME','retracted_length',0)
        emit('SET_IDLE_TIMEOUT TIMEOUT=%s' % printer['configfile']['settings']['idle_timeout']['timeout'])
        emit('RESUME_BASE VELOCITY=%s' % (float(vars['travel_speed'])/2))
    finally:
        emit('SET_VELOCITY_LIMIT ACCEL=%s' % accel)
