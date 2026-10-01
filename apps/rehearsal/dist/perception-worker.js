importScripts('/mediapipe/vision_bundle.js');
const {FilesetResolver, ObjectDetector} = Vision;

let detector = null;
let processing = false;

function people(result, width, height) {
  const output = [];
  for (const detection of result?.detections || []) {
    const category = detection.categories?.[0];
    const label = String(category?.categoryName || category?.displayName || '').toLowerCase();
    if (label !== 'person') continue;
    const box = detection.boundingBox;
    if (!box || width <= 0 || height <= 0) continue;
    const left = Math.max(0, box.originX / width);
    const top = Math.max(0, box.originY / height);
    const right = Math.min(1, (box.originX + box.width) / width);
    const bottom = Math.min(1, (box.originY + box.height) / height);
    if (!(left < right && top < bottom)) continue;
    output.push({bbox_uv: [left, top, right, bottom], confidence: Number(category?.score || 0)});
  }
  return output;
}
self.onmessage = async event => {
  const message = event.data || {};
  if (message.type === 'init') {
    try {
      const vision = await FilesetResolver.forVisionTasks(message.wasmRoot);
      detector = await ObjectDetector.createFromOptions(vision, {
        baseOptions: {modelAssetPath: message.modelPath},
        runningMode: 'VIDEO',
        scoreThreshold: message.scoreThreshold,
        maxResults: message.maxResults,
      });
      self.postMessage({type: 'ready'});
    } catch (error) {
      self.postMessage({type: 'error', message: String(error?.message || error)});
    }
    return;
  }
  if (message.type !== 'frame' || !detector || processing) {
    message.bitmap?.close?.();
    return;
  }
  processing = true;
  const bitmap = message.bitmap;
  try {
    const startedMs = performance.now();
    const result = detector.detectForVideo(bitmap, message.captureMs);
    const inferenceMs = performance.now() - startedMs;
    self.postMessage({
      type: 'detections',
      captureMs: message.captureMs,
      inferenceMs,
      detections: people(result, bitmap.width, bitmap.height),
    });
  } catch (error) {
    self.postMessage({type: 'error', message: String(error?.message || error)});
  } finally {
    bitmap.close?.();
    processing = false;
  }
};
