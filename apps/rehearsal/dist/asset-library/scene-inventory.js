// Shared scene-editor helpers. Asset identity is not scene-instance identity.
export const availabilityLabels = {
  unconfirmed: 'Unconfirmed physical availability',
  present: 'Present on location (operator confirmed)',
  proposed: 'Proposed dressing - arrange before filming',
  virtual_only: 'Visualization only - not on location',
};

export function createSceneObject(entry, label = '', uuid = crypto.randomUUID()) {
  if (!entry?.id || !/^[0-9a-f-]{36}$/i.test(uuid)) throw new Error('Invalid scene object identity.');
  return {
    object_id: 'obj-' + uuid,
    asset_id: entry.id,
    label: label.trim(),
    availability: 'proposed',
    position_m: [4, 4, entry.default_size_m[2] / 2],
    size_m: [...entry.default_size_m],
    yaw_rad: 0,
  };
}

export function matchingAssets(entries, query = '', selected = '', limit = 40) {
  const terms = query.toLowerCase().trim().split(/\s+/).filter(Boolean);
  const matches = entries.filter(entry => terms.every(term => (entry.name + ' ' + entry.id).toLowerCase().includes(term)));
  const result = matches.slice(0, limit), current = entries.find(entry => entry.id === selected);
  if (current && !result.some(entry => entry.id === selected)) result.unshift(current);
  return {entries: result, total: matches.length};
}

export function bindAssetSearch(container, entries) {
  for (const select of container.querySelectorAll('select[name^="asset-"], select[name="new-object"]')) {
    const search = document.createElement('input'), count = document.createElement('small');
    search.type = 'search'; search.placeholder = 'Search installed models or procedural objects';
    search.setAttribute('aria-label', 'Search ' + select.name); search.dataset.assetSearch = select.name;
    count.className = 'field-help'; count.setAttribute('role', 'status');
    select.before(search); select.after(count);
    const redraw = () => {
      const selected = select.value, found = matchingAssets(entries, search.value, selected);
      select.replaceChildren();
      const placeholder = new Option(select.name === 'new-object' ? 'Keep existing objects' : 'Choose an object', '');
      select.add(placeholder);
      for (const entry of found.entries) select.add(new Option(entry.name, entry.id));
      // Retain an unresolved reference visibly; never replace it with the first match.
      if (selected && !found.entries.some(entry => entry.id === selected)) select.add(new Option('Missing model: ' + selected, selected));
      select.value = selected;
      count.textContent = `${found.total} matches; showing up to 40 plus the current selection.`;
    };
    search.addEventListener('input', redraw); redraw();
  }
}

export function inventoryLines(scene) {
  return (scene?.objects || []).map(object =>
    `${object.label || object.object_id}: ${availabilityLabels[object.availability || 'unconfirmed']} | ` +
    `${object.asset_id} | centre ${object.position_m.join(', ')} m | dimensions ${object.size_m.join(' x ')} m`);
}
