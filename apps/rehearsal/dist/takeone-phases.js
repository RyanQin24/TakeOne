/* One definition of the production, used by every surface.
 *
 * Before this file the phase order was stated seven times in hardcoded page
 * headers and twice more in React, and the nine statements disagreed five ways:
 * Shot Studio was 02 on five pages and 03 on two, Edit was missing from World
 * entirely. A phase cannot be missing from one page if there is only one list.
 *
 * The numerals are gone. The order is real, so position communicates it; a
 * zero-padded numeral on every item is template chrome.
 */

export const PHASES = [
  { id: 'director', label: 'Director', href: '/director.html', page: 'director' },
  { id: 'world', label: 'World', href: '/world.html', page: 'world' },
  { id: 'studio', label: 'Shot Studio', href: '/', page: 'studio' },
  { id: 'record', label: 'Record', href: '/record.html', page: 'record' },
  /* /edit.html is served here and answers what footage exists and whether it
   * has reached this computer. The timeline editor itself is still a separate
   * local process on :5178; that page says plainly when it is not running. */
  { id: 'edit', label: 'Edit', href: '/edit.html', page: 'edit', service: 'editor' },
];

export const UTILITIES = [
  { label: 'Location scout', href: '/location.html', note: 'Real filming locations and rehearsal worlds' },
  { label: 'Voice rehearsal', href: '/voice.html', note: 'Scripted read-through, offline fixture' },
  { label: 'Motor Lab', href: '/motor-test.html', note: 'Direct calibrated motor diagnostics' },
  { label: 'Motion proof', href: '/drive-proof.html', note: 'Cart movement evidence and limits' },
  { label: 'Asset library', href: '/asset-library/browser.html', note: 'Installed models and performers' },
];

export const phaseFor = page => PHASES.find(phase => phase.page === page) || null;

const element = (tag, className, text) => {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
};

/* `filled` names the phases that already hold work, so the dot can say so. */
export function renderShell(host, { page, title, context = '', filled = [] } = {}) {
  if (!host) return null;
  host.className = 't1-header';
  host.replaceChildren();

  const brand = element('a', 't1-header__brand');
  brand.href = '/director.html';
  brand.setAttribute('aria-label', 'TakeOne home — start a new production');
  brand.append(element('span', 't1-header__mark', 'T/1'));
  brand.append(element('span', 't1-header__title', title || phaseFor(page)?.label || 'TakeOne'));
  host.append(brand);
  host.append(element('span', 't1-header__context', context));

  const nav = element('nav', 't1-nav');
  nav.setAttribute('aria-label', 'Production');
  for (const phase of PHASES) {
    const current = phase.page === page;
    const item = element(phase.href ? 'a' : 'button', 't1-nav__item', phase.label);
    if (phase.href) item.href = phase.href;
    else {
      item.type = 'button';
      item.setAttribute('role', 'link');
      item.setAttribute('aria-disabled', 'true');
      item.dataset.t1Service = phase.service;
    }
    if (current) item.setAttribute('aria-current', 'page');
    if (filled.includes(phase.id)) item.dataset.filled = 'true';
    if (phase.id === 'record' && page === 'studio') {
      item.href = '/record.html?handoff=1';
    }
    nav.append(item);
  }
  host.append(nav);

  const end = element('div', 't1-header__end');
  const utilities = element('details', 't1-utilities');
  utilities.append(element('summary', 't1-btn', 'Tools'));
  const tools = element('nav', 't1-utilities__list');
  tools.setAttribute('aria-label', 'Utilities');
  for (const utility of UTILITIES) {
    const link = element('a', 't1-utilities__link', utility.label);
    link.href = utility.href; link.title = utility.note; tools.append(link);
  }
  utilities.append(tools); end.append(utilities);
  const badge = element('span', 't1-badge', 'Local');
  badge.title = 'This interface is served from the local loopback address.';
  end.append(badge);
  host.append(end);
  return host;
}
