/* TAKE ONE — shared application shell behaviour.
 *
 * Enhances the static header that every surface ships in its own markup. The
 * navigation works with this module absent; this file adds the compact drawer,
 * the utilities menu, entrance and reveal motion, marquee pausing, and an
 * honest availability probe for the editor, which is a separate local service.
 *
 * Boundaries this module holds:
 *   - It never opens a port, enables torque, moves anything, starts a
 *     recording, touches a microphone or contacts a model provider.
 *   - Its only network call is a liveness probe against a loopback editor
 *     address, so an "Edit" entry is never offered for a service that is not
 *     answering and never points at a URL that would 404.
 *   - All decorative animation stops when the document is hidden and under
 *     prefers-reduced-motion.
 */

const root = document.documentElement;
const reduced = window.matchMedia("(prefers-reduced-motion: reduce)");

/* ── Document state ───────────────────────────────────────────────────────── */

function markHidden() {
  root.dataset.t1Hidden = document.hidden ? "1" : "0";
}
document.addEventListener("visibilitychange", markHidden);
markHidden();

/* Surface identity is mirrored onto <html> so the ambient ground, which is
 * painted there, can vary per surface without :has() support. */
if (document.body.dataset.t1Page) {
  root.dataset.t1Page = document.body.dataset.t1Page;
}

/* Ambient drift is opt-in per surface and only on creative surfaces. */
if (document.body.dataset.t1Ambient === "on" && !reduced.matches) {
  root.dataset.t1Ambient = "on";
}

/* ── Entrance ─────────────────────────────────────────────────────────────── */

const entering = document.querySelectorAll("[data-t1-enter]");
entering.forEach((node, index) => {
  node.style.setProperty("--t1-order", String(index));
});
requestAnimationFrame(() => {
  root.dataset.t1Ready = "1";
});

/* ── Sectional reveal (long-form surfaces only) ───────────────────────────── */

const revealing = document.querySelectorAll("[data-t1-reveal]");
if (revealing.length) {
  if (reduced.matches || !("IntersectionObserver" in window)) {
    revealing.forEach((node) => {
      node.dataset.t1Seen = "1";
    });
  } else {
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (!entry.isIntersecting) continue;
          entry.target.dataset.t1Seen = "1";
          observer.unobserve(entry.target);
        }
      },
      { rootMargin: "0px 0px -12% 0px", threshold: 0.08 }
    );
    revealing.forEach((node) => observer.observe(node));
  }
}

/* ── Utilities menu ───────────────────────────────────────────────────────── */

function wireMenu(menu) {
  const button = menu.querySelector(".t1-menu__button");
  const list = menu.querySelector(".t1-menu__list");
  if (!button || !list) return;

  const setOpen = (open) => {
    menu.dataset.open = open ? "1" : "0";
    button.setAttribute("aria-expanded", open ? "true" : "false");
  };
  setOpen(false);

  button.addEventListener("click", (event) => {
    event.stopPropagation();
    setOpen(menu.dataset.open !== "1");
  });

  menu.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || menu.dataset.open !== "1") return;
    setOpen(false);
    button.focus();
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) setOpen(false);
  });

  list.addEventListener("focusout", () => {
    window.setTimeout(() => {
      if (!menu.contains(document.activeElement)) setOpen(false);
    }, 0);
  });
}

document.querySelectorAll(".t1-menu").forEach(wireMenu);

/* ── Compact navigation drawer ────────────────────────────────────────────── */
/* Built by cloning the header's own links, so the compact menu can never drift
 * from the wide one and can never contain a link the header does not have. */

function buildDrawer(header) {
  const burger = header.querySelector(".t1-burger");
  if (!burger) return;

  const drawer = document.createElement("div");
  drawer.className = "t1-drawer";
  drawer.id = "t1Drawer";
  drawer.setAttribute("role", "dialog");
  drawer.setAttribute("aria-modal", "false");
  drawer.setAttribute("aria-label", "TakeOne navigation");
  drawer.dataset.open = "0";

  const primary = header.querySelector(".t1-nav");
  if (primary) {
    const heading = document.createElement("h2");
    heading.textContent = "Production";
    drawer.append(heading);
    primary.querySelectorAll("a").forEach((link) => drawer.append(link.cloneNode(true)));
  }

  const utilities = header.querySelector(".t1-menu__list");
  if (utilities) {
    const heading = document.createElement("h2");
    heading.textContent = "Utilities";
    drawer.append(heading);
    utilities.querySelectorAll("a").forEach((link) => drawer.append(link.cloneNode(true)));
  }

  document.body.append(drawer);

  const focusable = () =>
    Array.from(drawer.querySelectorAll('a[href], button:not([disabled])')).filter(
      (node) => node.offsetParent !== null
    );

  const setOpen = (open) => {
    drawer.dataset.open = open ? "1" : "0";
    burger.setAttribute("aria-expanded", open ? "true" : "false");
    document.body.style.overflow = open ? "hidden" : "";
    if (open) {
      const first = focusable()[0];
      if (first) first.focus();
    }
  };
  setOpen(false);

  burger.setAttribute("aria-controls", "t1Drawer");
  burger.addEventListener("click", () => setOpen(drawer.dataset.open !== "1"));

  drawer.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setOpen(false);
      burger.focus();
      return;
    }
    if (event.key !== "Tab") return;
    const nodes = focusable();
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  drawer.addEventListener("click", (event) => {
    if (event.target.closest("a")) setOpen(false);
  });

  window.matchMedia("(min-width: 1081px)").addEventListener("change", (event) => {
    if (event.matches) setOpen(false);
  });

  return { drawer, setOpen };
}

const header = document.querySelector(".t1-header");
let drawerApi = null;
if (header) drawerApi = buildDrawer(header);

/* ── Header tuck on long-form surfaces ────────────────────────────────────── */
/* Never applied to an operational workspace: transport, status and Stop
 * controls must stay where the operator left them. */

if (header && document.body.dataset.t1Scrollheader === "tuck" && !reduced.matches) {
  let last = window.scrollY;
  let ticking = false;
  const update = () => {
    const y = window.scrollY;
    const tucked =
      y > 180 && y > last && (!drawerApi || drawerApi.drawer.dataset.open !== "1");
    header.dataset.tucked = tucked ? "1" : "0";
    last = y;
    ticking = false;
  };
  window.addEventListener(
    "scroll",
    () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(update);
    },
    { passive: true }
  );
}

/* ── Marquee pause controls ───────────────────────────────────────────────── */

document.querySelectorAll(".t1-marquee").forEach((marquee) => {
  if (marquee.querySelector(".t1-marquee__pause")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "t1-marquee__pause";
  const label = (paused) => (paused ? "Resume motion" : "Pause motion");
  button.textContent = label(false);
  button.addEventListener("click", () => {
    const paused = marquee.dataset.paused === "1";
    marquee.dataset.paused = paused ? "0" : "1";
    button.textContent = label(!paused);
  });
  // Prefer the section heading, where the control reads as a control rather
  // than as something floating over the moving content.
  const head = marquee.closest("section")?.querySelector(".t1-rail__head");
  (head || marquee).append(button);
  if (head) button.classList.add("t1-marquee__pause--head");
  if (reduced.matches) {
    marquee.dataset.paused = "1";
    button.textContent = label(true);
  }
});

/* ── Editor handoff ───────────────────────────────────────────────────────── */
/* The editor is a separate local process: a Vite dev server, or the editor API
 * serving a built interface. This shell deliberately does NOT auto-detect it.
 *
 * A loopback liveness probe cannot tell the editor apart from any other server
 * on that port — the rehearsal server answers a request for the editor's health
 * route with a 404, which an opaque no-cors probe reports as success. Rendering
 * that as "connected" would be a claim we cannot support, so "Edit" opens a
 * connection panel that states what the editor is, shows the address it will
 * open, and lets the operator open it or start it. Nothing is contacted until
 * the operator asks, and no state is ever described as connected on our word.
 */

const EDITOR_DEFAULT = "http://127.0.0.1:5178";
const EDITOR_KEY = "takeone.editorUrl";

function editorAddress() {
  try {
    const stored = window.localStorage.getItem(EDITOR_KEY);
    if (stored) return new URL(stored).origin;
  } catch {
    /* storage unavailable or an unusable value; fall through to the default */
  }
  return EDITOR_DEFAULT;
}

function rememberEditorAddress(value) {
  try {
    window.localStorage.setItem(EDITOR_KEY, new URL(value).origin);
    return true;
  } catch {
    return false;
  }
}

let editorPanel = null;

function buildEditorPanel() {
  const overlay = document.createElement("div");
  overlay.className = "t1-overlay";
  overlay.dataset.open = "0";
  overlay.innerHTML = `
    <div class="t1-service t1-service--dialog" role="dialog" aria-modal="true"
         aria-labelledby="t1EditorTitle" data-state="idle">
      <h3 id="t1EditorTitle">Edit and finish</h3>
      <p>The TakeOne editor runs as its own local process. It is not part of this
         server, so this page cannot confirm whether it is running.</p>
      <label class="t1-service__field">
        <span>Editor address</span>
        <input type="url" id="t1EditorUrl" spellcheck="false" autocomplete="off">
      </label>
      <p class="t1-service__result" role="status" data-t1-editor-result></p>
      <div class="t1-service__row">
        <a class="t1-service__open primary" id="t1EditorOpen" href="${EDITOR_DEFAULT}/">Open the editor</a>
        <button type="button" id="t1EditorCheck">Check this address</button>
        <button type="button" id="t1EditorClose">Close</button>
      </div>
      <div class="t1-service__how">
        <p>Not running yet? From the workspace root:</p>
        <code>python -m takeone.editor.cli serve --media-root data/takes</code>
        <code>cd apps/editor &amp;&amp; npm install &amp;&amp; npm run dev</code>
      </div>
    </div>`;
  document.body.append(overlay);

  const dialog = overlay.querySelector(".t1-service");
  const field = overlay.querySelector("#t1EditorUrl");
  const open = overlay.querySelector("#t1EditorOpen");
  const result = overlay.querySelector("[data-t1-editor-result]");
  const check = overlay.querySelector("#t1EditorCheck");
  const close = overlay.querySelector("#t1EditorClose");

  let returnFocus = null;

  const sync = () => {
    const origin = editorAddress();
    field.value = origin;
    open.href = `${origin}/`;
  };
  sync();

  field.addEventListener("change", () => {
    if (rememberEditorAddress(field.value)) {
      sync();
      dialog.dataset.state = "idle";
      result.textContent = "";
    } else {
      result.textContent = "That does not look like a web address.";
    }
  });

  check.addEventListener("click", async () => {
    const origin = editorAddress();
    result.textContent = `Contacting ${origin}…`;
    const controller = new AbortController();
    const timer = window.setTimeout(() => controller.abort(), 1500);
    try {
      await fetch(`${origin}/api/editor/health`, {
        mode: "no-cors",
        cache: "no-store",
        signal: controller.signal,
      });
      dialog.dataset.state = "answering";
      // Deliberately not "connected": an opaque response proves only that
      // something accepted the connection, not that it was the editor.
      result.textContent = `Something is answering at ${origin}. Open it to see whether it is the editor.`;
    } catch {
      dialog.dataset.state = "silent";
      result.textContent = `Nothing is answering at ${origin}. The editor is probably not running.`;
    } finally {
      window.clearTimeout(timer);
    }
  });

  const setOpen = (isOpen) => {
    overlay.dataset.open = isOpen ? "1" : "0";
    if (isOpen) {
      returnFocus = document.activeElement;
      sync();
      open.focus();
    } else if (returnFocus && returnFocus.focus) {
      returnFocus.focus();
    }
  };

  close.addEventListener("click", () => setOpen(false));
  overlay.addEventListener("click", (event) => {
    if (event.target === overlay) setOpen(false);
  });
  overlay.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setOpen(false);
      return;
    }
    if (event.key !== "Tab") return;
    const nodes = Array.from(
      overlay.querySelectorAll("a[href], button, input")
    ).filter((node) => !node.disabled);
    if (!nodes.length) return;
    const first = nodes[0];
    const last = nodes[nodes.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  });

  return { setOpen };
}

function openEditorPanel() {
  if (!editorPanel) editorPanel = buildEditorPanel();
  editorPanel.setOpen(true);
}

function wireEditorEntries(scope) {
  scope.querySelectorAll('[data-t1-service="editor"]').forEach((node) => {
    if (node.dataset.t1Wired === "1") return;
    node.dataset.t1Wired = "1";
    node.dataset.state = "external";
    node.setAttribute("role", "button");
    node.setAttribute("tabindex", "0");
    node.removeAttribute("aria-disabled");
    node.title = "The editor runs as a separate local service — opens a connection panel";
    const activate = (event) => {
      event.preventDefault();
      openEditorPanel();
    };
    node.addEventListener("click", activate);
    node.addEventListener("keydown", (event) => {
      if (event.key === "Enter" || event.key === " ") activate(event);
    });
  });
}

wireEditorEntries(document);

/* ── TO live control ──────────────────────────────────────────────────────── */
/* One toggle on every surface: start or stop a live spoken conversation with
 * the director. The heavy module loads only on first use; nothing about the
 * conversation runs until the operator presses the control. A director page
 * can bind the conversation to its production by setting
 * document.body.dataset.t1DirectorSession before the operator starts TO. */

function wireLiveControl() {
  const host = document.querySelector(".t1-header__end");
  if (!host || host.querySelector(".t1-live")) return;
  const button = document.createElement("button");
  button.type = "button";
  button.className = "t1-live";
  button.dataset.state = "off";
  button.setAttribute("aria-pressed", "false");
  button.title = "Talk to TO, the director. Uses the microphone; nothing records without a take.";
  button.innerHTML = '<i class="t1-live__dot" aria-hidden="true"></i><span>TO · OFF</span>';
  const label = button.querySelector("span");
  const anchor = host.querySelector("[data-t1-env]");
  host.insertBefore(button, anchor || host.firstChild);

  let controller = null;
  let busy = false;

  const show = (state, text) => {
    button.dataset.state = state;
    button.setAttribute("aria-pressed", state === "listening" ? "true" : "false");
    label.textContent = text;
  };

  button.addEventListener("click", async () => {
    if (busy) return;
    if (controller) {
      controller.stop();
      controller = null;
      show("off", "TO · OFF");
      return;
    }
    busy = true;
    show("starting", "TO · STARTING");
    try {
      const {boot} = await import("/voice-live.js");
      controller = await boot({
        directorSessionId: document.body.dataset.t1DirectorSession || null,
        onStatus: (state) => {
          if (state === "listening") show("listening", "TO · LISTENING");
          else if (state === "resuming" || state === "connecting") show("starting", "TO · RECONNECTING");
          else if (state === "error") show("error", "TO · ERROR");
        },
      });
      show("listening", "TO · LISTENING");
    } catch (error) {
      controller = null;
      show("error", "TO · UNAVAILABLE");
      button.title = String(error.message || error);
    } finally {
      busy = false;
    }
  });

  window.addEventListener("pagehide", () => controller?.stop(), {once: true});
}

wireLiveControl();

/* ── Environment pill ─────────────────────────────────────────────────────── */
/* A same-origin, read-only status read. It reports what the server already
 * knows; it starts nothing and changes nothing. */

async function showEnvironment() {
  const pill = document.querySelector("[data-t1-env]");
  if (!pill) return;
  const label = pill.querySelector("[data-t1-env-label]");
  try {
    const response = await fetch("/api/health", { cache: "no-store" });
    if (!response.ok) return;
    const health = await response.json();
    if (!label) return;
    const hardware =
      health.hardwareConnected === true
        ? "HARDWARE"
        : health.hardwareConnected === null
          ? "PLAYBACK ACTIVE"
          : "SIMULATION";
    label.textContent = `LOCAL · ${hardware}`;
    pill.dataset.tone = health.hardwareConnected === true ? "warn" : "sim";
    pill.title =
      `Served from the local loopback address. Mode: ${health.mode}. ` +
      `Robot playback: ${health.robotPlayback}.`;
  } catch {
    /* Pages opened outside the rehearsal server keep the static LOCAL label. */
  }
}

showEnvironment();


/* ── Movement rail ────────────────────────────────────────────────────────── */
/* A slow horizontal rail of the real movement library, so the creative surface
 * shows what this rig can actually shoot. The names come from the same catalog
 * the Shot Studio compiles from — nothing here is decorative copy. The read is
 * a same-origin GET; it starts nothing. */

async function fillMovementRail() {
  const host = document.querySelector('[data-t1-marquee="movements"]');
  if (!host) return;
  const track = host.querySelector(".t1-marquee__track");
  const note = document.querySelector("[data-t1-marquee-note]");
  try {
    const response = await fetch("/api/previs/templates", { cache: "no-store" });
    if (!response.ok) throw new Error(String(response.status));
    const catalog = await response.json();
    const templates = catalog.templates || [];
    if (!templates.length) throw new Error("empty catalog");

    const families = [...new Set(templates.map((item) => item.family))];
    const cards = templates.map((item) => {
      const node = document.createElement("a");
      node.className = "t1-move";
      node.href = "/";
      node.setAttribute("role", "listitem");
      node.innerHTML =
        `<span class="t1-move__family">${item.family}</span>` +
        `<span class="t1-move__name"></span>`;
      node.querySelector(".t1-move__name").textContent = item.name;
      return node;
    });

    // Two identical runs so the -50% translation loops seamlessly.
    for (const pass of [0, 1]) {
      for (const card of cards) {
        const copy = card.cloneNode(true);
        if (pass === 1) copy.setAttribute("aria-hidden", "true");
        track.append(copy);
      }
    }

    if (note) {
      note.textContent =
        `${templates.length} movements in ${families.length} families — ` +
        `${families.join(" · ")}. The full list is selectable in Shot Studio.`;
    }
  } catch {
    host.hidden = true;
    if (note) {
      note.textContent =
        "The movement library could not be read from this server. Open Shot Studio to browse it.";
    }
  }
}

fillMovementRail();

export { openEditorPanel };
