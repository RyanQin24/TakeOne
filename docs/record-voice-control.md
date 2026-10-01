# Record voice commands

Open Record from Shot Studio after compiling the shot. Click **Start voice
control**, allow the microphone, and wait for **Listening**. Say **start filming**
to start the selected shot, or **stop filming** / **cut** to stop. **Start shooting**
and **start recording** are also accepted. Selecting the next shot remains manual.

The listener uses the browser's SpeechRecognition service, without a Gemini key.
Chrome is the intended browser. Browser speech recognition may require a network
connection and send microphone audio to its speech service; unsupported browsers
and permission/network failures are reported beside the control. Microphone use
starts only after clicking the control and stops when the page becomes hidden or
closes. It must be explicitly enabled again after a recognition error.

Final complete commands call the same selected-shot workflow as **Start filming**.
Partial speech, negations and questions do not execute. Duplicate recognizer events
are consumed once; a repeated start never becomes a stop. Stop can cancel a start
while preparation is pending. The normal ownership, compiled-plan, phone, lens,
tracking and active-take checks remain in force. Voice is not an emergency stop;
the on-screen Stop remains available.

Before this change, Record automatically started Gemini Live, which required a
server API key and did not invoke the selected robot shot's Start button. The
Record-specific block now uses `dist/record-voice.js`; conversational TO remains
available on Director and the other top-level surfaces. Record's embedded preview
does not create its own TO owner.

Transient JavaScript import failures now reload the preview document at most twice,
preserving its shot/handoff parameters. A fresh document discards the browser's
failed module map. If recovery fails, **Retry planned frame** reloads just the
embedded preview. It does not navigate the recorder or start a take.

Behavior tests use synthetic recognition events and injected robot HTTP responses.
They exercise real command parsing and robot-client sequencing without a microphone
or physical movement. They are not physical filming acceptance or a measured speech
recognition result.

## Verification (20 September 2026)

- 220 Record, voice, startup and shared-interface JavaScript tests passed.
- 10 focused recording/selected-shot/preview HTTP tests passed.
- The original Record handoff URL rendered the planned camera frame and enabled
  the shot-time scrubber in the browser. Changed JavaScript passed syntax checks.
- The broader web suite had four failures in the existing location/world tests;
  its syntax-check launcher also reported stale generated editor tokens.
- The required full launcher completed 1,416 Python tests in 853 seconds with
  34 failures and six errors in unchanged editor, motion-baseline and provider
  code. The run was stopped at approximately 15 minutes during the separate
  simulation phase; no full-suite pass is claimed. Test processes were stopped.
