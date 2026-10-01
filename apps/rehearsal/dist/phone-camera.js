import * as THREE from 'three';

const OPTICAL_TO_CAMERA = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(1, 0, 0), Math.PI);

// Reuse all work vectors. This changes output framing, never the robot model.
export class PhoneFraming {
  constructor() {
    this.forward = new THREE.Vector3();this.right = new THREE.Vector3();this.down = new THREE.Vector3();
    this.up = new THREE.Vector3(0, 0, 1);this.basis = new THREE.Matrix4();
  }
  orient(camera, opticalQuaternion, horizon) {
    if (horizon === 'phone') camera.quaternion.copy(opticalQuaternion);
    else {
      this.forward.set(0, 0, 1).applyQuaternion(opticalQuaternion);
      this.right.crossVectors(this.forward, this.up);
      if (this.right.lengthSq() < 1e-14) this.right.set(1, 0, 0).applyQuaternion(opticalQuaternion);
      else this.right.normalize();
      this.down.crossVectors(this.forward, this.right);
      camera.quaternion.setFromRotationMatrix(this.basis.makeBasis(this.right, this.down, this.forward));
    }
    camera.quaternion.multiply(OPTICAL_TO_CAMERA);
  }
}

export function zoomAt(points, fraction) {
  if (fraction <= points[0].at) return points[0].focal_mm;
  for (let i = 0; i < points.length - 1; i++) {
    const a = points[i], b = points[i + 1];
    if (fraction < b.at) {
      let u = (fraction - a.at) / (b.at - a.at);
      if (a.ease === 'smooth') u = u * u * u * (10 + u * (-15 + 6 * u));
      else if (a.ease === 'hold') u = 0;
      return a.focal_mm + (b.focal_mm - a.focal_mm) * u;
    }
  }
  return points.at(-1).focal_mm;
}

export function lensDescription(focal) {
  if (focal === 13) return '0.5× · Ultra Wide';
  if (focal === 24) return '1× · Main';
  if (focal === 48) return '2× · Main sensor crop';
  if (focal === 100) return '4× · Telephoto';
  if (focal === 200) return '8× · Telephoto sensor crop';
  if (focal > 200) return `Digital video crop · approximately ${(focal / 24).toFixed(1)}×`;
  return 'Continuous equivalent framing between lens presets';
}
