; FORMAT EXAMPLE ONLY: operator-controlled air motion, not a PCB cutting job.
; Verify work zero, travel and clamp clearance before any physical start.
G21 G90 G94 G54
M5
G0 Z5
G0 X8 Y5
G1 X12 Y5 F100
G1 X15 Y8
G1 X15 Y12
G1 X12 Y15
G1 X8 Y15
G1 X5 Y12
G1 X5 Y8
G1 X8 Y5
G0 Z5
M5
M30
