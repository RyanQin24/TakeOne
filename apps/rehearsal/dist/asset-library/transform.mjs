/** Fit converted Z-up visual bounds to an authored, bounding-centred scene box. */
export function fitBounds(minimum, maximum, {size_m = null, scale = 1, height_m = null, anchor = 'center'} = {}) {
  for (const vector of [minimum, maximum]) {
    if (!Array.isArray(vector) || vector.length !== 3 || !vector.every(Number.isFinite)) {
      throw new Error('Model bounds must contain three finite numbers.');
    }
  }
  if (!['center', 'feet'].includes(anchor)) throw new Error('Unknown origin anchor.');
  if (!Number.isFinite(scale) || scale <= 0) throw new Error('Invalid model scale.');
  if (height_m !== null && (!Number.isFinite(height_m) || height_m <= 0)) throw new Error('Invalid height.');
  const dimensions = maximum.map((value, i) => value - minimum[i]);
  if (dimensions.some(value => !Number.isFinite(value) || value < 0)) throw new Error('Reversed model bounds.');
  let factors;
  if (size_m !== null) {
    if (height_m !== null || scale !== 1) throw new Error('Choose explicit size or uniform scaling, not both.');
    if (!Array.isArray(size_m) || size_m.length !== 3 || !size_m.every(value => Number.isFinite(value) && value > 0)) {
      throw new Error('size_m must contain three positive finite dimensions.');
    }
    if (dimensions.some(value => value <= 1e-9)) throw new Error('Cannot size-fit a flat or empty model.');
    factors = size_m.map((value, i) => value / dimensions[i]);
  } else {
    if (height_m !== null && dimensions[2] <= 1e-9) throw new Error('Cannot height-fit a zero-height model.');
    factors = Array(3).fill(height_m === null ? scale : height_m / dimensions[2]);
  }
  if (factors.some(value => !Number.isFinite(value) || value <= 0)) throw new Error('Invalid fitted scale.');
  const offset = minimum.map((value, i) => -(value / 2 + maximum[i] / 2) || 0);
  if (anchor === 'feet') offset[2] = -minimum[2];
  return {factors, offset, dimensions: dimensions.map((value, i) => value * factors[i])};
}
