// Script values use SI units. Display values use the simulator catalog's conversions.
export function movementEntry(catalog, id) {
  const entry = catalog.templates.find(item => item.id === id);
  if (!entry) throw new Error('Choose a movement from the simulator library.');
  return entry;
}

export function movementFields(catalog, shot, id) {
  const entry = movementEntry(catalog, id);
  const same = shot.movement?.template_id === id;
  const overrides = same ? Object.fromEntries(shot.movement.parameters.map(p => [p.name, p.value])) : {};
  return [...entry.parameters.filter(key => key !== 'duration_s'), 'focal_mm'].map(key => {
    const meta = key === 'focal_mm' ? catalog.lens_field : catalog.fields[key];
    const scale = meta.scale || 1;
    return {key, ...meta, scale, value: (overrides[key] ?? entry.defaults[key]) * scale};
  });
}

export function readMovement(catalog, shot, id, motion, data) {
  if (!['hold', 'walk', 'none'].includes(motion)) throw new Error('Choose actor movement or product only.');
  return {
    template_id: id, subject_motion: motion,
    parameters: movementFields(catalog, shot, id).map(field => {
      const raw = data.get(field.key);
      if (raw === null || String(raw).trim() === '') throw new Error(`Enter ${field.label.toLowerCase()}.`);
      const value = Number(raw) / field.scale;
      if (!Number.isFinite(value) || value < field.minimum - 1e-8 || value > field.maximum + 1e-8)
        throw new Error(`Check ${field.label.toLowerCase()}.`);
      return {name: field.key, value};
    }),
  };
}

export function movementDescription(catalog, shot) {
  if (!shot.movement || shot.movement.template_id === 'unresolved') return 'Choose a simulator movement';
  const entry = movementEntry(catalog, shot.movement.template_id);
  const fields = new Map(movementFields(catalog, shot, entry.id).map(field => [field.key, field]));
  return [entry.name, shot.movement.subject_motion === 'walk' ? 'Actor walks' : shot.movement.subject_motion === 'none' ? 'Product only' : 'Actor holds',
    ...shot.movement.parameters.filter(p => fields.has(p.name)).map(p => {
      const field = fields.get(p.name);
      return `${field.label}: ${Number((p.value * field.scale).toFixed(2))}${field.unit ? ' ' + field.unit : ''}`;
    })].join(' · ');
}
