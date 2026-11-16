# Profile groove verification

The V-bit settings use a two-column desktop editor: cutting parameters and
calibration inputs on the left, the current calculated width and measurement
confirmation on the right. Narrow screens stack the same sections.

The historic trial diameter is an input, not the measured result. For one trial
at the cutting depth, effective width is `used diameter + nominal strip -
measured strip`. The live preview uses the same single-offset or least-squares
model as `monitor.profiles.fit_profile`; changing the cutting depth updates the
prediction. Invalid inputs show an explanation and disable confirmation/save.
Unsaved changes are identified in the result panel; export stays disabled until
they are saved or cancelled, so the displayed draft cannot be mistaken for the
exported profile.

The operator measures a straight section of the existing single-pass groove
around the trial, away from corners. No extra groove or numeric measurement
field is added. The explicit checkbox attests agreement with the displayed
width; it does not change the tool model or verify electrical isolation.

Saving with the checkbox checked submits the exact calibration evidence and
width. The backend independently fits the profile, rejects mismatched evidence
or width, and stores `groove_verification` with the server-computed width and
UTC confirmation time. Reload validates this evidence as well as the existing
profile checksum. The confirmation is included in profile exports.

Editing calibration inputs or any cutting condition immediately clears the
checkbox. Saving without confirmation persists an unverified profile; existing
profiles are not automatically verified or migrated. This indicator introduces
no additional milling interlock. Renaming alone does not invalidate measurement
evidence. Normal profile saving still creates a revision and requires fresh CAM
and Z preparation through the existing contracts.

UI persistence checks use an isolated ProfileStore on localhost. They never
forward requests to the Raspberry Pi or serial controller, and do not attest
any real physical measurements.
