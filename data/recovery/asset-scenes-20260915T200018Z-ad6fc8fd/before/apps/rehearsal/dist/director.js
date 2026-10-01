import { illustrations, thumbnail } from "./director-visuals.js";
import {movementFields, readMovement, movementDescription} from "./director-movement.js?v=director-03";
import {ChannelEditor} from './channel-editor.js?v=cinematic-01';
import {CameraControls} from './camera-controls.js?v=cinematic-01';
import {timecode as playbackTimecode} from './orbit-player.js';
import {directionCard} from './shot-direction.js?v=shot-language-01';
import {
  envelope,
  sessionScope,
  requestJSON,
  ResponseError,
} from "./director-client.js";
const $ = (id) => document.getElementById(id);
const esc = (value) =>
  String(value).replace(
    /[&<>"']/g,
    (char) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        char
      ],
  );
const money = (value) =>
  new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(
    value / 1e6,
  );
const timecode = (ms) => playbackTimecode(ms / 1000);
const frameNames = {
  extreme_wide: "Extreme wide · environment",
  wide: "Wide shot",
  full: "Full body · head to feet",
  medium_full: "Medium full · knees up",
  cowboy: "Cowboy · mid-thigh up",
  medium: "Medium shot",
  medium_close_up: "Medium close-up · chest up",
  close_up: "Close-up",
  extreme_close_up: "Extreme close-up · detail",
};
function framingLabel(shot) {
  return shot.camera_target?.kind==='object'
    ?'Object · '+shot.framing.replaceAll('_',' ')
    :frameNames[shot.framing];
}
const moveNames = {
  template: "Simulator movement",
  static: "Fixed camera",
  arm_pan_tilt: "Aim with the arm",
  straight_dolly: "Straight dolly",
  orbit: "Orbit",
  strafe: "Sideways travel",
  stairs: "Stair movement",
  optical_zoom: "Optical zoom",
  other_requested: "Other requested move",
};
const stageNames = {
  brief: "Brief",
  planning: "Planning",
  script: "Script",
  preview: "Preview",
  rehearsal: "Rehearsal",
  ready: "Ready",
  starting_recording: "Starting recording",
  recording: "Recording",
  finalizing: "Finalizing",
  review: "Review",
  accepted: "Accepted",
  editing: "Editing",
  complete: "Complete",
  cancelled: "Closed",
  fault: "Needs review",
};
const eventNames = {
  session_created: "Production created",
  save_brief: "Creative brief saved",
  revise_brief: "Brief revised",
  load_sample: "Editorial sample selected",
  save_document: "Script revision saved",
  start_script: "Manual script started",
  approve_script: "Creative script approved",
  request_plan: "Planning requested",
  request_lines: "Line alternatives requested",
  planning_finished: "Proposal saved",
  planning_failed: "Planning failed",
  cancel_planning: "Planning cancelled",
  cancel: "Production closed",
  request_rejected: "Request rejected",
  reconciliation_required: "Unfinished work invalidated after restart",
};
const pendingKey = "takeone-director-pending-v1",
  selectionKey = "takeone-director-selection-v1";
let detail = null,
  sessions = [],
  planning = null,
  pending = null,
  busy = false,
  dirty = false;
let activeTab = "brief",
  loadSequence = 0,
  pollTimer = null,
  aiRequest = null,
  editApply = null;
const session = () => detail?.session,
  creative = () => detail?.creative;
const shots = (doc) => doc.scenes.flatMap((scene) => scene.shots);
function notice(message = "", error = false) {
  $("notice").textContent = message;
  $("notice").hidden = !message;
  $("notice").classList.toggle("error", error);
}
function setBusy(value) {
  busy = value;
  const blocked = busy || pending !== null;
  for (const element of document.querySelectorAll(
    "[data-mutation], #newSession, #refreshSessions, .session-item, .starter, #ideaForm button, #approveButton, #cancelPlanning, #editForm button[type=submit]",
  ))
    element.disabled = blocked;
  $("briefFields").disabled = blocked || session()?.mode === "demonstration";
  $("approveButton").disabled =
    blocked ||
    !creative() ||
    creative().approved ||
    session()?.phase === "planning";
  $("exportButton").disabled = !creative();
  $("pendingNotice").hidden = pending === null;
  $("retryRequest").disabled = busy;
}
function menu(open) {
  $("sidebar").classList.toggle("open", open);
  $("sidebarScrim").hidden = !open;
  $("menuButton").setAttribute("aria-expanded", String(open));
  $("sidebar").inert = !open && window.matchMedia("(max-width:720px)").matches;
}
function selectTab(tab, focus = false) {
  activeTab = tab;
  for (const name of ["brief", "script", "shots"]) {
    $(name + "Tab").setAttribute("aria-selected", String(name === tab));
    $(name + "Tab").tabIndex = name === tab ? 0 : -1;
    $(name + "View").hidden = name !== tab;
  }
  if (focus) $(tab + "Tab").focus();
}
function canNavigate() {
  if (busy || pending) return false;
  if (dirty) {
    notice("Save your brief before opening another production.", true);
    selectTab("brief");
    return false;
  }
  return true;
}
function showHome() {
  if (!canNavigate()) return;
  clearTimeout(pollTimer);
  ++loadSequence;
  detail = null;
  localStorage.removeItem(selectionKey);
  $("workspace").hidden = true;
  $("home").hidden = false;
  $("breadcrumb").textContent = "Your next film";
  window.scrollTo({ top: 0 });
  notice();
  renderList();
  menu(false);
  $("idea").focus();
}
function renderList() {
  $("sessionList").innerHTML = sessions.length
    ? ""
    : '<p class="empty-list">A space for your next story.<br>Your productions will live here.</p>';
  for (const item of sessions) {
    const button = document.createElement("button");
    button.className =
      "session-item" +
      (item.session_id === session()?.session_id ? " active" : "");
    button.setAttribute(
      "aria-current",
      item.session_id === session()?.session_id ? "page" : "false",
    );
    button.innerHTML = `<strong>${esc(item.brief.title)}</strong><small>${item.brief.duration_ms / 1000}s · ${esc(item.brief.aspect_ratio)} · ${esc(stageNames[item.phase] || item.phase)}</small>`;
    button.onclick = () => {
      if (canNavigate()) loadSession(item.session_id, true).catch(report);
    };
    $("sessionList").append(button);
  }
}
async function refreshList() {
  sessions = (await requestJSON("/api/director/sessions")).sessions;
  renderList();
  setBusy(busy);
}
function getContext() {
  const facts = $("facts")
    .value.split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  if (facts.length > 12 || facts.some((line) => line.length > 400))
    throw new Error(
      "Use at most 12 facts, with no more than 400 characters each.",
    );
  return {
    skill_id: $("skill").value,
    audience: $("audience").value.trim(),
    tone: $("tone").value.trim(),
    facts: facts.map((text, index) => ({ fact_id: `fact-${index + 1}`, text })),
  };
}
function currentBrief() {
  return {
    title: $("title").value.trim(),
    objective: $("objective").value.trim(),
    duration_ms: Number($("duration").value) * 1000,
    aspect_ratio: $("aspect").value,
  };
}
function defaultContext() {
  const skill = planning.skills[0];
  return {
    skill_id: skill.id,
    audience: skill.audience,
    tone: skill.tone,
    facts: [],
  };
}
function fillBrief() {
  const brief = session().brief,
    context = detail.creative_context || defaultContext();
  $("title").value = brief.title;
  $("objective").value = brief.objective;
  $("duration").value = brief.duration_ms / 1000;
  $("aspect").value = brief.aspect_ratio;
  $("skill").value = context.skill_id;
  $("audience").value = context.audience;
  $("tone").value = context.tone;
  $("facts").value = context.facts.map((fact) => fact.text).join("\n");
  dirty = false;
  $("saveBrief").textContent = "Save brief";
}
function renderSession(next, preserveForm = false) {
  detail = next;
  localStorage.setItem(selectionKey, session().session_id);
  // The shared shell's TO control binds a live conversation to this production.
  document.body.dataset.t1DirectorSession = session().session_id;
  $("home").hidden = true;
  $("workspace").hidden = false;
  const doc = creative()?.document;
  $("breadcrumb").textContent = session().brief.title;
  $("projectTitle").textContent = doc?.title || session().brief.title;
  $("projectLogline").textContent = doc?.logline || session().brief.objective;
  $("revision").textContent = `Revision ${session().revision}`;
  const source = creative()?.provenance.source;
  $("sourceTag").textContent =
    source === "curated_sample"
      ? "EDITORIAL SAMPLE"
      : source === "model_proposal"
        ? "AI PROPOSAL · FOR YOUR REVIEW"
        : "YOUR PRODUCTION";
  $("sampleNote").hidden = source !== "curated_sample";
  $("metaDuration").textContent =
    `${session().brief.duration_ms / 1000} seconds`;
  $("metaAspect").textContent =
    session().brief.aspect_ratio +
    (session().brief.aspect_ratio === "9:16"
      ? " · Portrait"
      : session().brief.aspect_ratio === "16:9"
        ? " · Landscape"
        : " · Square");
  $("metaStage").textContent = creative()?.approved
    ? "Script approved"
    : stageNames[session().phase];
  $("approveButton").textContent = creative()?.approved
    ? "Script approved ✓"
    : "Approve script ✓";
  const blocked = creative()
    ? all(creative().document).filter(
        (shot) => !shot.movement || shot.movement.template_id === "unresolved",
      ).length
    : 0;
  const repair = $("repairButton");
  repair.hidden = !blocked;
  repair.textContent = `Fix ${blocked} blocked shot${blocked === 1 ? "" : "s"} ↗`;
  const rehearse = $("rehearseLink");
  rehearse.hidden = !creative()?.digest;
  if (creative()?.digest) rehearse.href = `/?script=${session().session_id}/${creative().digest}`;
  $("jobBanner").hidden = session().phase !== "planning";
  $("planningHint").textContent = planning.provider.available
    ? `Live request budget: ${money(planning.provider.request_budget_microusd)}. You confirm before anything is sent.`
    : "AI isn’t connected yet. Save your brief, write a script yourself, or explore a sample.";
  if (!preserveForm || !dirty) fillBrief();
  renderDocuments();
  renderNotes();
  renderList();
  setBusy(busy);
  clearTimeout(pollTimer);
  if (session().phase === "planning") schedulePoll(session().session_id);
}
async function loadSession(id, chooseTab = false) {
  const sequence = ++loadSequence,
    next = await requestJSON(
      "/api/director/sessions/" + encodeURIComponent(id),
    );
  if (sequence !== loadSequence) return;
  renderSession(next);
  if (chooseTab) {
    selectTab(next.creative ? "script" : "brief");
    window.scrollTo({ top: 0 });
  }
  menu(false);
}
function schedulePoll(id) {
  pollTimer = setTimeout(async () => {
    if (session()?.session_id !== id || busy || pending) {
      if (session()?.session_id === id) schedulePoll(id);
      return;
    }
    const revision = session().revision;
    try {
      const next = await requestJSON("/api/director/sessions/" + id);
      if (
        session()?.session_id !== id ||
        busy ||
        session().revision !== revision
      ) {
        if (session()?.session_id === id) schedulePoll(id);
        return;
      }
      if (next.session.revision !== revision) {
        renderSession(next, true);
        const failed = next.jobs.find((job) => job.status === "failed");
        if (failed && next.jobs[0]?.job_id === failed.job_id)
          notice(failed.result.message, true);
        else if (next.creative && next.session.phase === "script") {
          notice("Your proposal is ready to review.");
          if (!dirty) selectTab("script");
        }
        await refreshList();
      } else schedulePoll(id);
    } catch (error) {
      notice(
        "Could not refresh planning. Your work is still saved. " +
          error.message,
        true,
      );
      schedulePoll(id);
    }
  }, 1200);
}
function report(error) {
  if ($("editDialog").open) {
    $("editError").textContent =
      error.message || "This revision could not be saved.";
    $("editError").hidden = false;
    $("editError").scrollIntoView({ block: "nearest" });
  }
  notice(error.message || "Something went wrong. Please try again.", true);
}
async function perform(work) {
  if (busy || pending) return;
  setBusy(true);
  try {
    return await work();
  } catch (error) {
    report(error);
    return null;
  } finally {
    setBusy(false);
  }
}
async function send(path, extra) {
  const runtime = await requestJSON("/api/director/runtime");
  pending = {
    path,
    body: { ...envelope(runtime, crypto.randomUUID()), ...extra },
  };
  localStorage.setItem(pendingKey, JSON.stringify(pending));
  setBusy(true);
  return deliver();
}
function clearPending() {
  pending = null;
  localStorage.removeItem(pendingKey);
}
async function deliver() {
  let result;
  try {
    result = await requestJSON(pending.path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pending.body),
    });
  } catch (error) {
    if (
      error instanceof ResponseError &&
      error.status >= 400 &&
      error.status < 500
    )
      clearPending();
    throw error;
  }
  clearPending();
  if (!result.ok) {
    if (result.session) await loadSession(result.session.session_id);
    throw new Error(result.message);
  }
  dirty = false;
  try {
    await loadSession(result.session.session_id);
    await refreshList();
  } catch {
    detail = null;
    $("workspace").hidden = true;
    $("home").hidden = false;
    throw new Error(
      "Saved successfully, but the view could not refresh. Reopen the production from the sidebar.",
    );
  }
  return result;
}
const command = (action, payload) => {
  if (dirty && action !== "save_brief") {
    selectTab("brief");
    throw new Error("Save the changed brief before editing the script.");
  }
  return send("/api/director/creative", {
    scope: sessionScope(session()),
    action,
    payload,
  });
};
async function saveBrief() {
  if (!$("briefForm").reportValidity()) return false;
  await command("save_brief", { brief: currentBrief(), context: getContext() });
  notice("Brief saved. Changes to the brief require a new script revision.");
  return true;
}
async function saveDocument(document) {
  await command("save_document", { document });
  notice("Revision saved. Previous script approval has been cleared.");
}
function renderStarters() {
  $("starters").innerHTML = "";
  $("skill").innerHTML = planning.skills
    .map(
      (skill) => `<option value="${esc(skill.id)}">${esc(skill.name)}</option>`,
    )
    .join("");
  planning.skills.forEach((skill, index) => {
    const button = document.createElement("button");
    button.className = "starter";
    button.setAttribute("aria-label", `Open ${skill.name} sample`);
    button.innerHTML = `<div class="starter-art">${illustrations[skill.id] || illustrations.reaction}<span class="art-caption">STUDY 0${index + 1}</span></div><div class="starter-caption"><span class="starter-arrow" aria-hidden="true">↗</span><h3>${esc(skill.name)}</h3><p>${esc(skill.description)}</p></div>`;
    button.onclick = () =>
      perform(async () => {
        await send("/api/director/sessions", {
          brief: planning.samples[skill.id],
        });
        await command("load_sample", { skill_id: skill.id });
        selectTab("script");
        window.scrollTo({ top: 0 });
        notice("An editorial sample, ready for your own edits.");
      });
    $("starters").append(button);
  });
}
function emptyDocument(container) {
  if (session()?.mode === "demonstration") {
    container.innerHTML =
      '<div class="empty-document"><h3>A workflow demonstration.</h3><p>This saved record tests session transitions. Open an editorial sample from a new production to edit a real creative document.</p></div>';
    return;
  }
  container.innerHTML =
    '<div class="empty-document"><h3>Your script starts here.</h3><p>Ask the Director to shape your brief, or start writing your own opening shot.</p><button class="secondary" data-mutation>Start writing</button></div>';
  container.querySelector("button").onclick = () => perform(startScript);
}
async function startScript() {
  if (dirty) {
    notice(
      "Save the brief first so your script uses the latest direction.",
      true,
    );
    selectTab("brief");
    return;
  }
  const context = detail.creative_context || defaultContext();
  const document = {
    title: session().brief.title,
    logline: session().brief.objective.slice(0, 800),
    audience: context.audience,
    tone: context.tone,
    actors: [{ actor_id: "actor-a", name: "Presenter" }],
    marks: [
      {
        mark_id: "A",
        description: "Starting position; room placement to be confirmed.",
      },
    ],
    questions: ["Where should the actor stand in the room?"],
    scenes: [
      {
        scene_id: "scene-1",
        title: "Opening scene",
        location: "Location to be confirmed",
        shots: [
          {
            shot_id: "shot-1",
            start_ms: 0,
            end_ms: session().brief.duration_ms,
            actor_id: "actor-a",
            mark_id: "A",
            action: "Describe what the actor does in this shot.",
            framing: "medium",
            primitive: "static",
            camera_intent:
              "Hold a fixed frame; placement still needs simulation.",
            light_intent: "Describe the intended lighting.",
            edit_intent: "Describe how this shot connects to the next.",
            lines: [
              {
                text: "[Write your opening line.]",
                tone: context.tone,
                fact_ids: [],
              },
            ],
            selected_line: 0,
          },
        ],
      },
    ],
  };
  await command("start_script", { document, context });
  selectTab("script");
  notice("Your script is ready to write.");
}
function renderDocuments() {
  if (!creative()) {
    emptyDocument($("scriptContent"));
    emptyDocument($("shotsContent"));
    return;
  }
  const doc = creative().document;
  $("scriptContent").innerHTML = "";
  $("shotsContent").innerHTML = "";
  const actors = Object.fromEntries(
    doc.actors.map((actor) => [actor.actor_id, actor.name]),
  );
  let number = 0;
  for (const scene of doc.scenes) {
    const heading = document.createElement("div");
    heading.className = "scene-heading";
    heading.innerHTML = `<h3>${esc(scene.title)}</h3><span>${esc(scene.location)}</span>`;
    const staging=document.createElement('p');staging.textContent=scene.location_notes||'Add location directions and simulated set dressing.';heading.append(staging);
    const sceneEdit=document.createElement('button');sceneEdit.textContent='Edit scene & objects';sceneEdit.className='quiet-button';sceneEdit.dataset.mutation='';sceneEdit.onclick=()=>editScene(scene.scene_id);heading.append(sceneEdit);
    $("scriptContent").append(heading);
    for (const shot of scene.shots) {
      const index = ++number,
        line = shot.lines[shot.selected_line] || {text:'',tone:'Silent visual beat'};
      const row = document.createElement("article");
      row.className = "script-beat";
      row.innerHTML = `<div class="beat-index">${String(index).padStart(2, "0")}<small>${timecode(shot.start_ms)}–${timecode(shot.end_ms)}</small></div><div><div class="beat-meta"><span>${esc(actors[shot.actor_id]||"Product study")} · MARK ${esc(shot.mark_id)}</span><span>${esc(framingLabel(shot))}</span></div><div class="script-paper"><blockquote>“${esc(line.text)}”</blockquote><div class="paper-footer"><span>${esc(line.tone)} · Proposed dialogue</span><button data-edit data-mutation aria-label="Edit dialogue for shot ${index}">Edit line ↗</button></div></div><p class="actor-cue"><span aria-hidden="true">↳</span><span>${esc(shot.action)}</span></p><div class="line-controls"><button data-options aria-expanded="false">${shot.lines.length} line ${shot.lines.length === 1 ? "option" : "options"} ↓</button><button data-short data-mutation>Make it shorter ↗</button><button data-tone data-mutation>Change the tone ↗</button></div><div class="line-options" hidden></div></div>`;
      row.querySelector("[data-edit]").onclick = () =>
        editShot(shot.shot_id, "line");
      if(!shot.lines.length) {
        row.querySelector('blockquote').textContent=shot.audio_intent||'No dialogue';
        row.querySelector('.paper-footer span').textContent='Sound & atmosphere · no spoken line';
        row.querySelector('.line-controls').hidden=true;
        row.querySelector('[data-edit]').textContent='Add dialogue ↗';
      }
      row.querySelector("[data-short]").onclick = () =>
        askAI("request_lines", {
          shot_id: shot.shot_id,
          instruction:
            "Offer 2-3 shorter alternatives. Preserve the speaker’s voice and supplied facts.",
        });
      row.querySelector("[data-tone]").onclick = () => editTone(shot.shot_id);
      row.querySelector("[data-options]").onclick = (event) => {
        const panel = row.querySelector(".line-options");
        panel.hidden = !panel.hidden;
        event.currentTarget.setAttribute(
          "aria-expanded",
          String(!panel.hidden),
        );
      };
      shot.lines.forEach((option, optionIndex) => {
        const button = document.createElement("button");
        button.className = "line-option";
        button.dataset.mutation = "";
        button.setAttribute(
          "aria-pressed",
          String(optionIndex === shot.selected_line),
        );
        button.innerHTML = `<small>${esc(option.tone)}${optionIndex === shot.selected_line ? " · SELECTED" : ""}</small>${esc(option.text)}`;
        button.onclick = () =>
          perform(async () => {
            const changed = structuredClone(creative().document);
            shots(changed).find(
              (s) => s.shot_id === shot.shot_id,
            ).selected_line = optionIndex;
            await saveDocument(changed);
          });
        row.querySelector(".line-options").append(button);
      });
      $("scriptContent").append(row);
      renderShot(shot, index, actors);
    }
  }
  const add = document.createElement("button");
  add.className = "quiet-button";
  add.dataset.mutation = "";
  add.textContent = "＋ Add a shot";
  add.onclick = editNewShot;
  $("shotsContent").append(add);
}
const all = (document) => document.scenes.flatMap((scene) => scene.shots);
function movementSummary(shot) {
  return esc(movementDescription(planning.movement_catalog, shot));
}
function renderShot(shot, index, actors) {
  for(const size of planning?.movement_catalog?.shot_design?.sizes || [])frameNames[size.id]=size.name;
  const check = creative().constraints.find(
      (item) => item.shot_id === shot.shot_id,
    ),
    row = document.createElement("details");
  row.className = "shot-row";
  row.innerHTML = `<summary><div class="shot-thumbnail">${thumbnail(shot.framing)}</div><div class="shot-info"><strong>${String(index).padStart(2, "0")} / ${esc(framingLabel(shot))}</strong><small>${timecode(shot.start_ms)}–${timecode(shot.end_ms)} · ${esc(actors[shot.actor_id]||"Product study")} · Mark ${esc(shot.mark_id)}</small><p>${esc(moveNames[shot.primitive])}</p></div><span class="shot-chevron" aria-hidden="true">＋</span></summary><div class="shot-details"><dl><dt>Performance</dt><dd>${esc(shot.action)}</dd></dl><dl><dt>Camera intention</dt><dd>${esc(shot.camera_intent)}</dd></dl><dl><dt>Light</dt><dd>${esc(shot.light_intent)}</dd></dl><dl><dt>The edit</dt><dd>${esc(shot.edit_intent)}</dd></dl><dl><dt>Simulator movement</dt><dd>${movementSummary(shot)}</dd></dl><div class="constraint ${check.status === "unsupported" ? "unsupported" : ""}"><strong>${check.status === "unsupported" ? "Revise this move" : "Needs simulation"}</strong>${esc(check.reason)}</div><button class="quiet-button" data-mutation>Edit shot direction ↗</button></div>`;
  row.querySelector("button").onclick = () => editShot(shot.shot_id, "shot");
  const moveButton = document.createElement("button");
  moveButton.className = "secondary"; moveButton.dataset.mutation = "";
  moveButton.textContent = "Edit simulator movement";
  moveButton.setAttribute("aria-label", `Edit simulator movement for shot ${index}`);
  moveButton.onclick = () => editMovement(shot.shot_id);
  row.querySelector(".shot-details").append(moveButton);
  const context=document.createElement('p');context.className='field-help';
  context.textContent=`Target: ${shot.camera_target?.target_id||shot.actor_id} · Cart: ${(shot.tracking?.cart||'planned').replaceAll('_',' ')} · Phone: ${(shot.tracking?.phone||'planned').replaceAll('_',' ')}. ${shot.audio_intent||''}`;
  row.querySelector('.shot-details').append(context);
  if(shot.design)row.querySelector('.shot-details').append(directionCard({...shot.design,size_label:framingLabel(shot)},actors));
  const designButton=document.createElement('button');designButton.className='secondary';designButton.dataset.mutation='';
  designButton.textContent='Design shot & performance beats';designButton.onclick=()=>editDesign(shot.shot_id);
  row.querySelector('.shot-details').append(designButton);
  $("shotsContent").append(row);
}
function renderNotes() {
  const container = $("notesContent");
  container.innerHTML = "";
  if (!creative()) {
    container.innerHTML =
      "<h3>A little direction goes a long way.</h3><p>Start with who the film is for and how it should feel. Leave unknown facts open.</p>";
    return;
  }
  const doc = creative().document;
  container.innerHTML = `<h3>${doc.questions.length ? "Still to decide" : "Creative questions resolved"}</h3><ul>${doc.questions.map((question) => `<li>${esc(question)}</li>`).join("")}</ul><button class="quiet-button" data-notes data-mutation>Edit production notes</button><h3>People & positions</h3><p>${doc.actors.map((actor) => esc(actor.name)).join(" · ")}</p><ul>${doc.marks.map((mark) => `<li><strong>${esc(mark.mark_id)}</strong> — ${esc(mark.description)}</li>`).join("")}</ul><p class="field-help">Dialogue and facts need your review. Mark positions are not measured coordinates.</p>`;
  container.querySelector("[data-notes]").onclick = editNotes;
  const style=document.createElement('section');style.className='direction-card';
  const heading=document.createElement('h3');heading.textContent='Film language';style.append(heading);
  for(const [key,value] of Object.entries(doc.visual_style || {})){
    const p=document.createElement('p');p.textContent=key.replaceAll('_',' ')+': '+(Array.isArray(value)?value.join(' · '):value);style.append(p);
  }
  const edit=document.createElement('button');edit.textContent='Edit film language';edit.dataset.mutation='';edit.onclick=editStyle;style.append(edit);container.prepend(style);
}
function field(label, name, value, type = "textarea", options = null, constraints = {}) {
  if (options)
    return `<label>${esc(label)}<select name="${esc(name)}">${Object.entries(
      options,
    )
      .map(
        ([key, title]) =>
          `<option value="${esc(key)}" ${key === value ? "selected" : ""}>${esc(title)}</option>`,
      )
      .join("")}</select></label>`;
  const required = constraints.required === false ? '' : 'required';
  const numeric = `type="number" step="any" min="${constraints.min ?? 0}" max="${constraints.max ?? 300}"`;
  return `<label>${esc(label)}${type === "textarea" ? `<textarea name="${esc(name)}" rows="3" maxlength="${constraints.maxLength ?? 800}" ${required}>${esc(value)}</textarea>` : `<input name="${esc(name)}" value="${esc(value)}" ${type === "number" ? numeric : `maxlength="${constraints.maxLength ?? 200}"`} ${required}>`}</label>`;
}
function openEdit(title, html, apply) {
  if (busy || pending) return;
  if (dirty) {
    notice("Save the changed brief before editing the script.", true);
    selectTab("brief");
    return;
  }
  $("editTitle").textContent = title;
  $("editError").hidden = true;
  $("editFields").innerHTML = html;
  editApply = apply;
  $("editDialog").showModal();
}
function editShot(id, kind) {
  const revision = session().revision,
    doc = structuredClone(creative().document),
    shot = shots(doc).find((s) => s.shot_id === id);
  const originalPrimitive = shot.primitive;
  const scene = doc.scenes.find(s => s.shots.some(s => s.shot_id === id));
  const html =
    kind === "line"
      ? field("Spoken line · leave empty for silence", "text", shot.lines[shot.selected_line]?.text||'', 'textarea', null, {required:false}) +
        field("Acting direction", "action", shot.action)
      : `<div class="form-row">${field("Start · seconds", "start", shot.start_ms / 1000, "number")}${field("End · seconds", "end", shot.end_ms / 1000, "number")}</div>` +
        field(
          "Actor",
          "actor",
          shot.actor_id,
          "select",
          Object.fromEntries(
            [["", "No actor · object shot"], ...doc.actors.map((actor) => [actor.actor_id, actor.name])],
          ),
        ) +
        field(
          "Stage mark",
          "mark",
          shot.mark_id,
          "select",
          Object.fromEntries(
            doc.marks.filter(mark => !mark.scene_id || mark.scene_id === scene.scene_id).map((mark) => [mark.mark_id, mark.mark_id]),
          ),
        ) +
        field("Framing", "framing", shot.framing, "select", frameNames) +
        field("Camera move", "primitive", shot.primitive, "select", moveNames) +
        field("Camera intention", "camera", shot.camera_intent) +
        field("Acting direction", "action", shot.action) +
        field("Light", "light", shot.light_intent) +
        field("Edit intention", "edit", shot.edit_intent) + field('Sound & atmosphere','audio',shot.audio_intent||'Natural location sound.');
  openEdit(
    kind === "line" ? "Make it sound like you." : "Give the shot direction.",
    html,
    async (data) => {
      if (session().revision !== revision)
        throw new Error(
          "The script changed while this editor was open. Close and reopen it.",
        );
      if (kind === "line") {
        const value=data.get('text').trim();
        if(!value){shot.lines=[];shot.selected_line=0;}
        else if(!shot.lines.length){shot.lines=[{text:value,tone:'Natural',fact_ids:[]}];shot.selected_line=0;}
        else shot.lines[shot.selected_line].text=value;
      } else
        Object.assign(shot, {
          start_ms: Math.round(Number(data.get("start")) * 1000),
          end_ms: Math.round(Number(data.get("end")) * 1000),
          framing: data.get("framing"),
          actor_id: data.get("actor"),
          mark_id: data.get("mark"),
          primitive: data.get("primitive"),
          camera_intent: data.get("camera").trim(),
          light_intent: data.get("light").trim(),
          edit_intent: data.get("edit").trim(),
          audio_intent:data.get('audio').trim(),
        });
      shot.action = data.get("action").trim();
      if (kind !== 'line' && shot.camera_target?.kind === 'actor') shot.camera_target.target_id = shot.actor_id;
      if (kind !== "line" && shot.movement) {
        if (shot.primitive !== originalPrimitive) delete shot.movement;
        else shot.movement.parameters = shot.movement.parameters.filter(p => p.name !== "duration_s");
      }
      await saveDocument(doc);
    },
  );
}
function editStyle() {
  const revision=session().revision,doc=structuredClone(creative().document);
  const value=doc.visual_style || {visual_rules:doc.tone,palette:'Choose the location palette.',lighting:'Keep light direction consistent.',
    wardrobe:'Keep wardrobe and held props consistent.',sound:'Use the shot sound cues.',continuity_locks:[]};
  const labels={visual_rules:'Visible rules for this film',palette:'Colour palette',lighting:'Light direction & quality',
    wardrobe:'Wardrobe & props',sound:'Sound',continuity_locks:'Continuity locks · one per line'};
  openEdit('Give the film a visual language',Object.entries(labels).map(([key,label])=>field(label,key,
    Array.isArray(value[key])?value[key].join('\n'):value[key],'textarea',null,{maxLength:key==='continuity_locks'?4800:1000,required:key!=='continuity_locks'})).join(''),
  async data=>{
    if(session().revision!==revision)throw new Error('The script changed. Reopen film language.');
    doc.visual_style=Object.fromEntries(Object.keys(labels).map(key=>[key,key==='continuity_locks'
      ?data.get(key).split('\n').map(x=>x.trim()).filter(Boolean):data.get(key).trim()]));
    await saveDocument(doc);
  });
}
function editDesign(id) {
  const revision=session().revision,doc=structuredClone(creative().document),shot=shots(doc).find(s=>s.shot_id===id);
  const scene=doc.scenes.find(s=>s.shots.includes(shot)),duration=(shot.end_ms-shot.start_ms)/1000;
  const design=structuredClone(shot.design || {
    purpose:shot.edit_intent,attention:shot.camera_intent,composition:shot.actor_id?'single':'insert',angle:'eye_level',lens_policy:'authored',
    featured_actor_ids:shot.actor_id?[shot.actor_id]:[],focus:{mode:'manual',target:'Confirm the subject on the recording phone.'},
    opening:shot.action,ending:'Hold the final action until the cut.',continuity:'Keep the eyeline and prop hand consistent.',
    practical_setup:scene.location_notes || 'Use the marked camera route.',
    beats:[{start_s:0,end_s:duration,actor_id:shot.actor_id,action:shot.action,motivation:'',emotion:'',eyeline:'',delivery:''}],
  });
  const available=new Set([shot.actor_id,...(scene.cast||[]).map(a=>a.actor_id)]);
  const people=doc.actors.filter(a=>available.has(a.actor_id));
  const names=Object.fromEntries([['','Crew / object action'],...people.map(a=>[a.actor_id,a.name])]);
  const catalog=planning.movement_catalog.shot_design;
  const labels={purpose:'Purpose · what this shot adds',attention:'What the viewer should notice',opening:'Opening state',
    ending:'Ending state',continuity:'Continuity across the cut',practical_setup:'Practical setup & crew directions'};
  const html=Object.entries(labels).map(([key,label])=>field(label,key,design[key],'textarea',null,{maxLength:key==='practical_setup'?1000:key==='continuity'?800:600})).join('')+
    field('Composition','composition',design.composition,'select',catalog.compositions)+
    field('Camera angle · match movement height and aim','angle',design.angle,'select',catalog.angles)+
    field('Lens choice','lens-policy',design.lens_policy,'select',catalog.lens_policies)+
    field('Subject visibility','visibility',design.visibility||'throughout','select',{throughout:'Keep visible throughout',by_end:'Reveal by the final frame',intentional_partial:'Intentional partial view'})+
    '<fieldset><legend>People featured in this frame</legend>'+people.map(a=>'<label><input type="checkbox" name="featured" value="'+esc(a.actor_id)+'" '+(design.featured_actor_ids.includes(a.actor_id)?'checked':'')+'>'+esc(a.name)+'</label>').join('')+
    '<p class="field-help">Place supporting people in Scene & objects before selecting a two-person or over-shoulder view.</p></fieldset>'+
    field('Focus intent · manual recording app','focus-mode',design.focus.mode,'select',{manual:'Confirm manually',deep:'Keep the scene readable',selective:'Isolate a subject',rack:'Change focus between subjects'})+
    field('Focus target / change cue','focus-target',design.focus.target,'textarea',null,{maxLength:400})+
    '<h3>Performance beats</h3><p class="field-help">Seconds from the first filmed frame of this edit shot; setup excluded. These cues guide the performer. Body and head animation use the independent movement channels.</p><div id="performanceEditor"></div>';
  openEdit('Design the shot and its performance',html,async data=>{
    if(session().revision!==revision)throw new Error('The script changed. Reopen shot design.');
    readBeats();
    for(const key of Object.keys(labels))design[key]=data.get(key).trim();
    Object.assign(design,{composition:data.get('composition'),angle:data.get('angle'),lens_policy:data.get('lens-policy'),visibility:data.get('visibility'),
      featured_actor_ids:data.getAll('featured'),focus:{mode:data.get('focus-mode'),target:data.get('focus-target').trim()}});
    shot.design=design;await saveDocument(doc);
  });
  function readBeats() {
    const form=new FormData($('editForm'));
    design.beats.forEach((beat,i)=>{
      for(const key of ['start_s','end_s'])beat[key]=Number(form.get('beat-'+i+'-'+key));
      for(const key of ['actor_id','action','motivation','emotion','eyeline','delivery'])beat[key]=String(form.get('beat-'+i+'-'+key)||'').trim();
    });
  }
  function renderBeats() {
    const container=$('performanceEditor');container.innerHTML=design.beats.map((beat,i)=>'<fieldset><legend>Beat '+(i+1)+'</legend>'+
      field('Start · seconds','beat-'+i+'-start_s',beat.start_s,'number',null,{max:duration})+
      field('End · seconds','beat-'+i+'-end_s',beat.end_s,'number',null,{max:duration})+
      field('Performer','beat-'+i+'-actor_id',beat.actor_id,'select',names)+
      Object.entries({action:'Observable action',motivation:'Why this action happens',emotion:'Emotional change',eyeline:'Look toward',delivery:'Breath / line delivery'}).map(([key,label])=>
        field(label,'beat-'+i+'-'+key,beat[key],'textarea',null,{required:key==='action',maxLength:key==='action'?600:400})).join('')+
      '<button type="button" data-remove-beat="'+i+'">Remove beat</button></fieldset>').join('')+
      '<button type="button" id="addPerformanceBeat">Split longest beat</button>';
    for(const button of container.querySelectorAll('[data-remove-beat]')){
      button.disabled=design.beats.length===1;button.onclick=()=>{readBeats();design.beats.splice(Number(button.dataset.removeBeat),1);renderBeats();};
    }
    $('addPerformanceBeat').disabled=design.beats.length>=16;
    $('addPerformanceBeat').onclick=()=>{
      readBeats();let index=0;
      design.beats.forEach((beat,i)=>{if(beat.end_s-beat.start_s>design.beats[index].end_s-design.beats[index].start_s)index=i;});
      const beat=design.beats[index],mid=(beat.start_s+beat.end_s)/2;
      design.beats.splice(index,1,{...beat,end_s:mid},{...beat,start_s:mid});renderBeats();
    };
  }
  renderBeats();
}
function editMovement(id) {
  const revision = session().revision, doc = structuredClone(creative().document);
  const shot = shots(doc).find(s => s.shot_id === id), catalog = planning.movement_catalog;
  const scene=doc.scenes.find(s=>s.shots.some(s=>s.shot_id===id));
  const targets=Object.fromEntries([...doc.actors.map(a=>[`actor:${a.actor_id}`,'Actor · '+a.name]),...(scene.objects||[]).map(o=>[`object:${o.object_id}`,o.label||o.object_id])]);
  const initialId = catalog.templates.some(e => e.id === shot.movement?.template_id) ? shot.movement.template_id : "static";
  const html = field("Camera movement", "movement-template", initialId, "select",
    Object.fromEntries(catalog.templates.map(e => [e.id, e.name]))) +
    '<p id="movementIntent" class="field-help"></p>' +
    field("Subject", "movement-subject", shot.movement?.subject_motion || "hold", "select", {hold:"Actor stands still",walk:"Actor walks",none:"Product only · no actor"}) +
    field('Camera target','camera-target',`${shot.camera_target?.kind||'actor'}:${shot.camera_target?.target_id||shot.actor_id}`,'select',targets)+
    field('Cart control','cart-follow',shot.tracking?.cart||'planned','select',{planned:'Authored route',follow_actor:'Follow selected actor'})+
    field('Phone arm control','head-follow',shot.tracking?.phone||'planned','select',{planned:'Authored aim',follow_head:'Follow selected head'})+
    field('Between setups','transition',shot.transition||'cut','select',{cut:'Cut · reset between takes',reposition:'Estimate drive within this location'})+
    '<div id="movementFields" class="movement-editor-grid"></div><details><summary>Independent timing & organic drift</summary><div id="directorChannels"></div><div id="directorLens"></div></details>'+
    '<details><summary>Share one continuous take</summary><p class="field-help">Use the same take name, movement and mark on consecutive shots. Source times must adjoin. Setup happens once; rehearsal includes the full take, even footage trimmed from the edit.</p>'+
    `<label>Take name (leave empty for a separate setup)<input name="capture-id" maxlength="40" value="${esc(shot.capture?.take_id||'')}"></label>`+
    field('Source filming start · s','capture-in',shot.capture?.in_s||0,'number',null,{min:0,max:600})+'</details>'+
    field('Full take filming duration · s (stationary shared takes)','capture-duration',shot.movement?.parameters.find(p=>p.name==='duration_s')?.value||10,'number',null,{min:.5,max:120})+
    '<p class="field-help">Follow modes use the scripted actor in rehearsal. Live controller integration is required for real following. Edit timing is set in shot direction.</p>';
  let channelSettings;
  openEdit("Direct the whole movement.", html, async data => {
    if (session().revision !== revision) throw new Error("The script changed. Reopen the movement editor.");
    shot.movement = readMovement(catalog, shot, data.get("movement-template"), data.get("movement-subject"), data);
    shot.movement.cinematography={channels:Object.fromEntries(Object.keys(catalog.channels).map(k=>[k,channelSettings.channels[k]||[]])),texture:channelSettings.texture,breath:channelSettings.breath,camera:channelSettings.camera};
    if(shot.movement.subject_motion==='none')shot.actor_id='';
    else if(!shot.actor_id)shot.actor_id=doc.actors[0]?.actor_id||'';
    shot.primitive = "template";
    const [kind,target_id]=data.get('camera-target').split(':');shot.camera_target={kind,target_id};
    shot.tracking={cart:data.get('cart-follow'),phone:data.get('head-follow'),on_loss:'stop_and_hold',reason:'Selected for this shot in Director.'};
    shot.transition=data.get('transition');
    shot.capture={take_id:String(data.get('capture-id')).trim(),in_s:Number(data.get('capture-in'))};
    if(shot.capture.take_id&&catalog.templates.find(e=>e.id===shot.movement.template_id).route==='hold')shot.movement.parameters.push({name:'duration_s',value:Number(data.get('capture-duration'))});
    await saveDocument(doc);
  });
  if (!$("editDialog").open) return;
  const select = $("editFields").querySelector('[name="movement-template"]');
  const updateSubjectFields=()=>{
    const motion=$('editFields').querySelector('[name="movement-subject"]').value;
    for(const input of $('movementFields').querySelectorAll('input')){
      input.parentElement.hidden=(input.name.startsWith('actor_')&&motion!=='walk')||(input.name==='subject_height_m'&&motion==='none');
      if(input.name==='radius_m'){
        const label=motion==='none'?'Product to cart':'Actor to cart';
        input.parentElement.firstChild.textContent=label+' · m';input.setAttribute('aria-label',label);
      }
      if(input.name==='distance_m'&&['arc_push','three_beat'].includes(select.value)){
        input.parentElement.firstChild.textContent='Curve size · m';input.setAttribute('aria-label','Curve size');
      }
    }
  };
  const draw = () => {
    const entry = catalog.templates.find(e => e.id === select.value);
    $("movementIntent").textContent = entry.intent;
    $("movementFields").innerHTML = movementFields(catalog, shot, select.value).map(f =>
      `<label>${esc(f.label)}${f.unit ? ' · '+esc(f.unit) : ''}<input type="number" name="${esc(f.key)}" aria-label="${esc(f.label)}" min="${f.minimum*f.scale}" max="${f.maximum*f.scale}" step="any" value="${Number(f.value.toFixed(5))}" required></label>`).join("");
    channelSettings=structuredClone(entry.defaults);
    if(select.value===shot.movement?.template_id&&shot.movement.cinematography){Object.assign(channelSettings,structuredClone(shot.movement.cinematography));channelSettings.channels=Object.fromEntries(Object.entries(channelSettings.channels).filter(([,v])=>v.length));}
    new ChannelEditor($('directorChannels'),channelSettings,catalog.channels,()=>{}, {moving:entry.route!=='hold'});
    const focal=$('movementFields').querySelector('[name="focal_mm"]');
    const lens=new CameraControls({container:$('directorLens'),focal,onChange:()=>{channelSettings.camera=lens.read();}});lens.load(channelSettings.camera);
    updateSubjectFields();
  };
  select.onchange = () => {
    $("editFields").querySelector('[name="movement-subject"]').value = catalog.templates.find(e => e.id === select.value).defaults.subject_motion;
    syncSubject();
    draw();
  };
  const syncSubject=()=>{
    const product=$('editFields').querySelector('[name="movement-subject"]').value==='none';
    const target=$('editFields').querySelector('[name="camera-target"]');
    const prefix=product?'object:':'actor:';
    if(!target.value.startsWith(prefix))target.value=Object.keys(targets).find(k=>k.startsWith(prefix))||'';
    for(const name of ['cart-follow','head-follow']){
      const input=$('editFields').querySelector(`[name="${name}"]`);
      if(product)input.value='planned';
    }
    updateSubjectFields();
  };
  $('editFields').querySelector('[name="movement-subject"]').onchange=syncSubject;
  draw();
}
function editScene(id) {
  const revision=session().revision,doc=structuredClone(creative().document),scene=doc.scenes.find(s=>s.scene_id===id);
  const catalog=planning.movement_catalog.scene_catalog;
  const objectOptions=Object.fromEntries(catalog.objects.map(o=>[o.id,o.name]));
  const html=field('Scene title','title',scene.title,'input')+field('Location','location',scene.location)+
    field('Find a place like this · actor and crew directions','directions',scene.location_notes||'Find a clear level area and leave room for the camera path.','textarea',null,{maxLength:1200})+
    field('Atmosphere','atmosphere',scene.atmosphere||'studio','select',Object.fromEntries(catalog.atmospheres.map(s=>[s,s.replaceAll('_',' ')])))+
    '<p class="field-help">Assumed scene geometry in metres. Positions are object centres. Props do not represent measured venue dimensions.</p>'+
    (scene.objects||[]).map((o,i)=>`<fieldset><legend>${esc(o.label||o.object_id)}</legend>`+
      field('Object','asset-'+i,o.asset_id,'select',objectOptions)+field('Label','label-'+i,o.label,'input',null,{required:false,maxLength:120})+
      '<div class="movement-editor-grid">'+['X','Y','Z'].map((a,j)=>field(a+' centre · m',`pos-${i}-${j}`,o.position_m[j],'number',null,{min:-100,max:100})).join('')+
      ['Width','Depth','Height'].map((a,j)=>field(a+' · m',`size-${i}-${j}`,o.size_m[j],'number',null,{min:.02,max:30})).join('')+
      field('Rotation · degrees','yaw-'+i,o.yaw_rad*180/Math.PI,'number',null,{min:-360,max:360})+'</div></fieldset>').join('')+
    field('Add from object library','new-object','','select',{'':'Keep existing objects',...objectOptions})+
    field('New object label','new-label','','input',null,{required:false,maxLength:120})+castFields(scene,doc);
  openEdit('Stage this scene',html,async data=>{
    if(session().revision!==revision)throw new Error('The script changed. Reopen this scene.');
    scene.cast=doc.actors.filter(a=>data.get('cast-'+a.actor_id)).map(a=>({actor_id:a.actor_id,offset_m:[0,1,2].map(j=>Number(data.get('cast-'+a.actor_id+'-'+j))),facing_rad:Number(data.get('cast-facing-'+a.actor_id))*Math.PI/180,motion:data.get('cast-motion-'+a.actor_id)}));
    scene.title=data.get('title').trim();scene.location=data.get('location').trim();scene.location_notes=data.get('directions').trim();scene.atmosphere=data.get('atmosphere');
    scene.objects=(scene.objects||[]).map((o,i)=>({...o,asset_id:data.get('asset-'+i),label:data.get('label-'+i).trim(),position_m:[0,1,2].map(j=>Number(data.get(`pos-${i}-${j}`))),size_m:[0,1,2].map(j=>Number(data.get(`size-${i}-${j}`))),yaw_rad:Number(data.get('yaw-'+i))*Math.PI/180}));
    if(data.get('new-object')) {
      const entry=catalog.objects.find(o=>o.id===data.get('new-object'));
      scene.objects.push({object_id:`${entry.id}-${crypto.randomUUID().slice(0,8)}`,asset_id:entry.id,label:data.get('new-label').trim(),position_m:[4,4,entry.default_size_m[2]/2],size_m:[...entry.default_size_m],yaw_rad:0});
    }
    await saveDocument(doc);
  });
}
function castFields(scene,doc) {
  return '<h3>Supporting people</h3><p class="field-help">Offsets are in metres from this shot’s lead mark, or from the lead actor for Walk with lead. Each shot supplies its own lead actor. Choose up to five supporting people.</p>'+
    doc.actors.map(actor=>{
      const member=(scene.cast||[]).find(c=>c.actor_id===actor.actor_id);
      const value=member||{offset_m:[1,0,0],facing_rad:0,motion:'hold'};
      return '<fieldset><legend><label><input type="checkbox" name="cast-'+esc(actor.actor_id)+'" '+(member?'checked':'')+'>'+esc(actor.name)+'</label></legend>'+
        ['X','Y','Z'].map((label,j)=>field(label+' offset · m','cast-'+actor.actor_id+'-'+j,value.offset_m[j],'number',null,{min:-100,max:100})).join('')+
        field('Facing · degrees','cast-facing-'+actor.actor_id,value.facing_rad*180/Math.PI,'number',null,{min:-360,max:360})+
        field('Movement','cast-motion-'+actor.actor_id,value.motion,'select',{hold:'Hold position',with_lead:'Walk with lead'})+'</fieldset>';
    }).join('');
}
function editNotes() {
  const revision = session().revision,
    doc = structuredClone(creative().document);
  const html =
    field("Production title", "title", doc.title, "input") +
    field("One sentence story", "logline", doc.logline) +
    `<label>Actors · one name per line<textarea name="actors" rows="3" maxlength="480">${esc(doc.actors.map((actor) => actor.name).join("\n"))}</textarea><span class="field-help">Leave empty for a product film. Existing names keep their identities. Add another name to introduce an actor.</span></label>` +
    `<label>Open questions · one per line<textarea name="questions" rows="4" maxlength="3200">${esc(doc.questions.join("\n"))}</textarea></label>` +
    doc.marks
      .map((mark, index) =>
        field(`Mark ${mark.mark_id}`, "mark-" + index, mark.description) +
        `<div class="movement-editor-grid">${[["X position · m","x",mark.position_m?.[0] ?? 0],["Y position · m","y",mark.position_m?.[1] ?? 0],["Facing · degrees","facing",(mark.facing_rad ?? 0)*180/Math.PI]].map(([label,key,value]) => `<label>${esc(label)}<input type="number" step="any" name="mark-${index}-${key}" value="${Number(value.toFixed(5))}" required></label>`).join("")}</div>`,
      )
      .join("") +
    `<label>New marks · one description per line<textarea name="newMarks" rows="2" maxlength="1600"></textarea></label>` +
    doc.scenes
      .map(
        (scene, index) =>
          field(
            `Scene ${index + 1} title`,
            "scene-title-" + index,
            scene.title,
            "input",
          ) +
          field(
            `Scene ${index + 1} location`,
            "scene-location-" + index,
            scene.location,
            "input",
          ),
      )
      .join("");
  openEdit("The details behind the take.", html, async (data) => {
    if (session().revision !== revision)
      throw new Error("The production changed. Reopen this editor.");
    doc.title = data.get("title").trim();
    doc.logline = data.get("logline").trim();
    const names = data
      .get("actors")
      .split("\n")
      .map((name) => name.trim())
      .filter(Boolean);
    doc.actors = names.map((name, index) => ({
      actor_id:
        doc.actors[index]?.actor_id ||
        "actor-" + crypto.randomUUID().slice(0, 8),
      name,
    }));
    doc.questions = data
      .get("questions")
      .split("\n")
      .map((s) => s.trim())
      .filter(Boolean);
    doc.marks.forEach((mark, index) => {
      mark.description = data.get("mark-" + index).trim();
      mark.position_m = [Number(data.get(`mark-${index}-x`)), Number(data.get(`mark-${index}-y`))];
      mark.facing_rad = Number(data.get(`mark-${index}-facing`)) * Math.PI / 180;
    });
    for (const description of data
      .get("newMarks")
      .split("\n")
      .map((value) => value.trim())
      .filter(Boolean)) {
      let index = doc.marks.length + 1;
      while (doc.marks.some((mark) => mark.mark_id === "M" + index)) index++;
      doc.marks.push({ mark_id: "M" + index, description });
    }
    doc.scenes.forEach((scene, index) => {
      scene.title = data.get("scene-title-" + index).trim();
      scene.location = data.get("scene-location-" + index).trim();
    });
    await saveDocument(doc);
  });
}
function editNewShot() {
  const doc = structuredClone(creative().document),
    previous = shots(doc).at(-1),
    revision = session().revision;
  if (shots(doc).length >= 24) {
    notice("Keep a production to 24 shots or fewer.", true);
    return;
  }
  if (previous.end_ms >= session().brief.duration_ms) {
    notice(
      "Make room for another shot by shortening the last shot’s proposed end time.",
      true,
    );
    return;
  }
  openEdit(
    "What happens next?",
    field("Spoken line · optional", "line", "", 'textarea', null, {required:false}) +
      field("Acting direction", "action", "Describe the next beat.") +
      field("Scene", "scene", "current", "select", {
        current: "Continue this scene",
        new: "Start a new scene",
      }),
    async (data) => {
      if (session().revision !== revision)
        throw new Error("The production changed. Reopen this editor.");
      let markId = previous.mark_id;
      if (data.get("scene") === "new") {
        const sceneId = crypto.randomUUID();
        let markIndex = doc.marks.length + 1;
        while (doc.marks.some(mark => mark.mark_id === `M${markIndex}`)) markIndex++;
        markId = `M${markIndex}`;
        doc.marks.push({mark_id:markId,scene_id:sceneId,description:'Lead actor starting mark.',position_m:[0,0],facing_rad:0});
        doc.scenes.push({
          scene_id: sceneId,
          space_id: sceneId,
          title: "New scene",
          location: "Location to be confirmed",
          location_notes: 'Find a clear level area with room for the actors and camera path.',
          atmosphere: 'studio', objects: [], cast: [],
          shots: [],
        });
      }
      const line = data.get('line').trim();
      doc.scenes.at(-1).shots.push({
        ...structuredClone(previous),
        shot_id: crypto.randomUUID(),
        mark_id: markId,
        transition: 'cut',
        camera_target: {kind:'actor',target_id:previous.actor_id},
        start_ms: previous.end_ms,
        end_ms: session().brief.duration_ms,
        action: data.get("action").trim(),
        lines: line ? [{ text: line, tone: doc.tone, fact_ids: [] }] : [],
        selected_line: 0,
      });
      await saveDocument(doc);
    },
  );
}
function editTone(shotId) {
  if (!planning.provider.available) {
    $("connectionDialog").showModal();
    return;
  }
  openEdit(
    "How should this line feel?",
    field("Tone and direction", "tone", creative().document.tone, "input"),
    async (data) => {
      // This editor only collects the instruction; the following dialog asks for the actual paid request.
      $("editDialog").close();
      setTimeout(
        () =>
          askAI("request_lines", {
            shot_id: shotId,
            instruction:
              "Offer 2-3 alternatives in this tone: " + data.get("tone"),
          }),
        0,
      );
    },
  );
}
function askAI(action, payload) {
  if (!planning.provider.available) {
    $("connectionDialog").showModal();
    return;
  }
  if (busy || pending) return;
  if (dirty) {
    notice("Save your brief before asking the Director to plan.", true);
    selectTab("brief");
    return;
  }
  aiRequest = { action, payload, revision: session().revision };
  $("consentTitle").textContent =
    action === "request_lines"
      ? "Find another way to say it?"
      : action === "repair_shots"
        ? "Let the Director fix the blocked shots?"
        : "Create a first draft?";
  $("consentDescription").textContent =
    `This sends the brief, supplied facts and relevant script to OpenAI (${planning.provider.model}). Up to ${money(planning.provider.request_budget_microusd)} is reserved for this request, within a ${money(planning.provider.session_budget_microusd)} production budget. Proposals need your review.`;
  $("consentDialog").showModal();
}
function renderConnection() {
  const provider = planning.provider;
  $("connectionLabel").textContent = provider.available
    ? "AI configured"
    : "Connect AI";
  $("connectionButton").classList.toggle("connected", provider.available);
  $("connectionDescription").textContent = provider.available
    ? "The planner is configured. Your next request will verify live model access. Your script stays editable at every stage."
    : "Luna Max is selected. Set OPENAI_API_KEY in the server environment to generate a script. The editable examples and simulator work without a key.";
  $("modelName").textContent = `${provider.model} · ${provider.reasoning_effort === 'max' ? 'Max reasoning' : provider.reasoning_effort}`;
  $("requestBudget").textContent = money(provider.request_budget_microusd);
  $("sessionBudget").textContent = money(provider.session_budget_microusd);
}
$("ideaForm").onsubmit = (event) => {
  event.preventDefault();
  perform(async () => {
    const objective = $("idea").value.trim();
    if (!objective) return;
    await send("/api/director/sessions", {
      brief: {
        title: objective.length > 65 ? objective.slice(0, 62) + "…" : objective,
        objective,
        duration_ms: Number($("ideaDuration").value),
        aspect_ratio: $("ideaAspect").value,
      },
    });
    selectTab("brief");
    window.scrollTo({ top: 0 });
    notice(
      "Your idea is saved. Add a little direction, then create your script.",
    );
  });
};
$("briefForm").oninput = () => {
  dirty = true;
  $("saveBrief").textContent = "Save changes";
};
$("briefForm").onsubmit = (event) => {
  event.preventDefault();
  perform(saveBrief);
};
$("skill").onchange = () => {
  const skill = planning.skills.find((item) => item.id === $("skill").value);
  $("audience").value = skill.audience;
  $("tone").value = skill.tone;
  dirty = true;
};
$("planButton").onclick = () => {
  if (!$("briefForm").reportValidity()) return;
  try {
    askAI("request_plan", { context: getContext() });
  } catch (error) {
    report(error);
  }
};
$("approveButton").onclick = () =>
  perform(async () => {
    await command("approve_script", { document_digest: creative().digest });
    notice(
      "Script approved. Open Rehearse script to calculate its shots and see the full timeline.",
    );
  });
$("cancelPlanning").onclick = () =>
  perform(async () => {
    await command("cancel_planning", {});
    notice("Planning cancelled. Any late response will be discarded.");
  });
$("newSession").onclick = showHome;
$("refreshSessions").onclick = () =>
  perform(async () => {
    await refreshList();
    if (session() && !dirty) await loadSession(session().session_id);
  });
$("menuButton").onclick = () => menu(!$("sidebar").classList.contains("open"));
$("sidebarScrim").onclick = () => menu(false);
$("connectionButton").onclick = () => $("connectionDialog").showModal();
$("repairButton").onclick = () => askAI("repair_shots", {});
$("declineAI").onclick = () => {
  aiRequest = null;
  $("consentDialog").close();
};
$("confirmAI").onclick = () => {
  const request = aiRequest;
  $("consentDialog").close();
  aiRequest = null;
  perform(async () => {
    if (!request || request.revision !== session().revision)
      throw new Error("The production changed. Request planning again.");
    await command(request.action, { ...request.payload, budget_consent: true });
    notice("Planning has started. Your result will appear here.");
  });
};
$("editForm").onsubmit = (event) => {
  event.preventDefault();
  perform(async () => {
    await editApply(new FormData($("editForm")));
    $("editDialog").close();
  });
};
$("closeEdit").onclick = $("cancelEdit").onclick = () =>
  $("editDialog").close();
$("retryRequest").onclick = async () => {
  if (!pending || busy) return;
  setBusy(true);
  try {
    await deliver();
    notice("The original save is confirmed.");
  } catch (error) {
    report(error);
  } finally {
    setBusy(false);
  }
};
$("historyButton").onclick = () => {
  $("historyContent").innerHTML = detail.events
    .slice()
    .reverse()
    .map(
      (event) =>
        `<div class="history-entry"><time>${esc(new Date(event.created_utc).toLocaleString())} · Revision ${event.revision}</time><p>${esc(eventNames[event.kind] || event.kind.replaceAll("_", " "))}</p>${event.detail.message ? `<small>${esc(event.detail.message)}</small>` : ""}</div>`,
    )
    .join("");
  $("historyDialog").showModal();
};
$("exportButton").onclick = () => {
  const blob = new Blob(
    [
      JSON.stringify(
        {
          schema_version: 1,
          kind: "creative_proposal_not_robot_plan",
          brief: session().brief,
          ...creative(),
        },
        null,
        2,
      ),
    ],
    { type: "application/json" },
  );
  const url = URL.createObjectURL(blob),
    link = document.createElement("a");
  link.href = url;
  link.download = "takeone-creative-revision-" + session().revision + ".json";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
for (const tab of document.querySelectorAll("[data-tab]")) {
  tab.onclick = () => selectTab(tab.dataset.tab);
  tab.onkeydown = (event) => {
    const names = ["brief", "script", "shots"],
      index = names.indexOf(activeTab);
    if (["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) {
      event.preventDefault();
      selectTab(
        event.key === "Home"
          ? "brief"
          : event.key === "End"
            ? "shots"
            : names[(index + (event.key === "ArrowRight" ? 1 : 2)) % 3],
        true,
      );
    }
  };
}
window.addEventListener("beforeunload", (event) => {
  if (dirty || pending) {
    event.preventDefault();
    event.returnValue = "";
  }
});
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") menu(false);
  if (
    event.key.toLowerCase() === "n" &&
    !event.ctrlKey &&
    !event.metaKey &&
    !event.altKey &&
    !document.querySelector("dialog[open]") &&
    !["INPUT", "TEXTAREA", "SELECT"].includes(document.activeElement.tagName)
  ) {
    event.preventDefault();
    showHome();
  }
});
async function initialize() {
  menu(false);
  try {
    pending = JSON.parse(localStorage.getItem(pendingKey) || "null");
  } catch {
    notice(
      "The stored save receipt is unreadable. Reload with browser storage available.",
      true,
    );
    return;
  }
  setBusy(true);
  try {
    const result = await Promise.all([
      requestJSON("/api/director/planning"),
      requestJSON("/api/director/sessions"),
    ]);
    planning = result[0];
    sessions = result[1].sessions;
    renderStarters();
    renderConnection();
    renderList();
    const selection = localStorage.getItem(selectionKey);
    if (selection && sessions.some((item) => item.session_id === selection))
      await loadSession(selection, true);
    if (pending)
      notice(
        "A previous save is unconfirmed. Check that request before making another change.",
        true,
      );
  } catch (error) {
    report(error);
  } finally {
    setBusy(false);
  }
}
window
  .matchMedia("(max-width:720px)")
  .addEventListener("change", () => menu(false));
initialize();
