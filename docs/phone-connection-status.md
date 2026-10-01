# Phone setup status

Record distinguishes saved setup from the last device check. `/api/phone/status`
only reads cached evidence and never contacts the handset. The `connection`
object reports `unchecked`, `checked`, `stale`, or `failed`, with the time of the
last check and its error. Successful checks become stale after 60 seconds;
Record refreshes this evidence every five seconds while visible.

A failed probe, device setup call, or capture overrides an earlier success.
Calibration and past recording evidence are retained. A successful explicit
Connect check clears the connection failure; saving a look does not. Unknown
recording outcomes still take priority and require inspecting the phone.
Capture performs its own device checks before recording.

Phone setup disables its controls while an action is pending, refreshes status
after failures as well as successes, keeps format confirmations visible, and
reads the camera name and zoom capability from the actual Blackmagic response.

Regression coverage: `tests/test_phone_readiness.py` and
`apps/rehearsal/tests/record-workflow.test.mjs`, and the asynchronous page-handler
tests in `apps/rehearsal/tests/record-phone-status.test.mjs`. Run the standard checks with
`scripts/TakeOne.ps1 -Command test`. These checks use fake cameras and do not
record footage or move hardware.

Recovery copies from before this change are in
`data/recovery/phone-status-20260920`, at the original relative paths. The phone
service and HTTP adapter retain their roles; Record presentation helpers remain
in `record-workflow.js`, with setup events in `record.js`.
