import { useCallback, useEffect, useRef, useState } from "react";

import { PRODUCTION, UTILITIES } from "../state/phases";

/* The production surfaces — Director, Shot Studio, Record — are served by
 * the TakeOne rehearsal server, a different local process from this editor.
 *
 * This component does not claim that server is running. It resolves the address
 * honestly, in order: an address the operator set, the origin this tab was
 * opened from (so arriving through the rehearsal flow configures it for free),
 * then the documented default. The links always point at that real address, and
 * the panel says plainly what it is.
 */

const DEFAULT_ORIGIN = "http://127.0.0.1:8766";
const STORAGE_KEY = "takeone.rehearsalUrl";

/* The phase list is not restated here: it is imported, so the editor cannot
 * disagree with the rehearsal surfaces about what the production is. */

function loopbackOrigin(value: string | undefined | null): string | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    const local = ["127.0.0.1", "localhost", "[::1]"].includes(url.hostname);
    return local && url.origin !== window.location.origin ? url.origin : null;
  } catch {
    return null;
  }
}

function resolveOrigin(): string {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY);
    if (stored) return new URL(stored).origin;
  } catch {
    /* unusable stored value; fall through */
  }
  return loopbackOrigin(document.referrer) ?? DEFAULT_ORIGIN;
}

export function TakeOneNav() {
  const [open, setOpen] = useState(false);
  const [origin, setOrigin] = useState(DEFAULT_ORIGIN);
  const [draft, setDraft] = useState(DEFAULT_ORIGIN);
  const panel = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const resolved = resolveOrigin();
    setOrigin(resolved);
    setDraft(resolved);
    // Remember an address discovered from the referrer so later visits keep it.
    const discovered = loopbackOrigin(document.referrer);
    if (discovered) {
      try {
        window.localStorage.setItem(STORAGE_KEY, discovered);
      } catch {
        /* storage unavailable; the address still works for this session */
      }
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    const onClick = (event: MouseEvent) => {
      if (panel.current && !panel.current.contains(event.target as Node) &&
          !trigger.current?.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    };
    document.addEventListener("mousedown", onClick);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onClick);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const commit = useCallback((value: string) => {
    try {
      const next = new URL(value).origin;
      window.localStorage.setItem(STORAGE_KEY, next);
      setOrigin(next);
      setDraft(next);
    } catch {
      setDraft(origin);
    }
  }, [origin]);

  return (
    <div className="t1x">
      <button
        ref={trigger}
        type="button"
        className="t1x__trigger"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
      >
        Utilities
        <span className="t1x__caret" aria-hidden>▾</span>
      </button>

      {open && (
        <div className="t1x__panel" ref={panel} role="dialog" aria-label="TakeOne production surfaces">
          <p className="label">Production</p>
          <ul className="t1x__list">
            {PRODUCTION.map((item) =>
              item.path === null ? (
                <li key={item.id}>
                  <span className="t1x__here">
                    {item.label}
                    <em>you are here</em>
                  </span>
                </li>
              ) : (
                <li key={item.id}>
                  <a href={`${origin}${item.path}`}>{item.label}</a>
                </li>
              ),
            )}
          </ul>

          <p className="label">Utilities</p>
          <ul className="t1x__list">
            {UTILITIES.map((item) => (
              <li key={item.path}>
                <a href={`${origin}${item.path}`}>
                  {item.label}
                  <small>{item.note}</small>
                </a>
              </li>
            ))}
          </ul>

          <label className="t1x__field">
            <span className="label">Rehearsal server address</span>
            <input
              type="url"
              value={draft}
              spellCheck={false}
              onChange={(event) => setDraft(event.target.value)}
              onBlur={(event) => commit(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") commit((event.target as HTMLInputElement).value);
              }}
            />
          </label>
          <p className="t1x__note">
            Those surfaces are served by the TakeOne rehearsal server, a separate local
            process. This editor cannot tell whether it is running; the links open the
            address above.
          </p>
        </div>
      )}
    </div>
  );
}
