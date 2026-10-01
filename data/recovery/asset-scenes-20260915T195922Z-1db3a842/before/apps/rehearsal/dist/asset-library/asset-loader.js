import * as THREE from 'three';
import {GLTFLoader} from 'three/addons/loaders/GLTFLoader.js';
import {clone as cloneSkeleton} from 'three/addons/utils/SkeletonUtils.js';
import {ResourceCache, LoadEpoch} from './lifecycle.mjs';

function disposeSource(gltf) {
  const geometries = new Set(), materials = new Set(), textures = new Set();
  const skeletons = new Set(), images = new Set();
  // The source owns all scenes. Instances share geometry/materials, NOT skeletons.
  for (const scene of gltf.scenes || [gltf.scene]) scene.traverse(object => {
    if (object.geometry) geometries.add(object.geometry);
    if (object.skeleton) skeletons.add(object.skeleton);
    for (const material of [].concat(object.material || [])) materials.add(material);
  });
  for (const material of materials) {
    for (const value of Object.values(material)) if (value?.isTexture) textures.add(value);
    material.dispose();
  }
  for (const texture of textures) {
    if (texture.source?.data) images.add(texture.source.data);
    texture.dispose();
  }
  for (const image of images) image.close?.();
  for (const geometry of geometries) geometry.dispose();
  for (const skeleton of skeletons) skeleton.dispose?.();
}

function finiteVector(value, label) {
  if (!Array.isArray(value) || value.length !== 3 || !value.every(Number.isFinite)) {
    throw new Error(`${label} must contain three finite numbers.`);
  }
  return value;
}

export class AssetLibrary {
  constructor(document, {loader = new GLTFLoader(), maxEntries = 16,
    maxBytes = 64 * 1024 * 1024, supportedRequiredExtensions = []} = {}) {
    if (document.schema_version !== 1) throw new Error('Unsupported asset catalog.');
    this.assets = new Map(document.assets.map(asset => [asset.asset_id, asset]));
    if (this.assets.size !== document.assets.length) throw new Error('Duplicate asset IDs.');
    this.loader = loader;
    this.supportedRequiredExtensions = new Set([
      'KHR_materials_unlit', 'KHR_texture_transform', 'KHR_mesh_quantization',
      ...supportedRequiredExtensions,
    ]);
    this.cache = new ResourceCache({maxEntries, maxBytes, dispose: disposeSource});
  }

  static async open(url = '/asset-library/catalog.json', options = {}) {
    const response = await fetch(url, {cache: 'no-cache'});
    if (!response.ok) throw new Error('No installed catalog. Run the local asset import command first.');
    return new AssetLibrary(await response.json(), options);
  }

  async createInstance(assetId, {position_m = [0, 0, 0], yaw_rad = 0,
    scale = 1, height_m = null, anchor = 'center', sha256 = null} = {}) {
    const asset = this.assets.get(assetId);
    if (!asset) throw new Error(`Asset is not installed: ${assetId}`);
    if (sha256 !== null && sha256 !== asset.sha256) throw new Error('Asset revision mismatch.');
    finiteVector(position_m, 'position_m');
    if (!Number.isFinite(yaw_rad) || !Number.isFinite(scale) || scale <= 0) throw new Error('Invalid asset transform.');
    if (height_m !== null && (!Number.isFinite(height_m) || height_m <= 0)) throw new Error('Invalid height.');
    if (!['center', 'feet'].includes(anchor)) throw new Error('Unknown origin anchor.');
    const url = new URL(asset.uri, location.href);
    if (url.origin !== location.origin || !url.pathname.startsWith('/asset-library/packs/')) {
      throw new Error('Only installed same-origin asset paths may be loaded.');
    }
    const unsupported = asset.extensions_required.filter(name => !this.supportedRequiredExtensions.has(name));
    if (unsupported.length) throw new Error(`Configure and test required loaders before using: ${unsupported.join(', ')}`);
    const lease = await this.cache.acquire(asset.uri, asset.dependency_bytes, () => this.loader.loadAsync(url.href));
    let model, mixer;
    try {
      model = cloneSkeleton(lease.value.scene);
      const converted = new THREE.Group();
      converted.rotation.x = Math.PI / 2; // glTF (x,y,z) -> TAKE ONE (x,-z,y).
      converted.add(model);
      const root = new THREE.Group();
      root.add(converted);
      root.updateMatrixWorld(true);
      const bounds = new THREE.Box3().setFromObject(converted, true);
      if (bounds.isEmpty()) throw new Error('The model contains no renderable bounds.');
      const dimensions = bounds.getSize(new THREE.Vector3());
      const center = bounds.getCenter(new THREE.Vector3());
      if (![dimensions.x, dimensions.y, dimensions.z].every(Number.isFinite)) throw new Error('Invalid model bounds.');
      if (height_m !== null && dimensions.z <= 0) throw new Error('Cannot height-fit a zero-height model.');
      const factor = height_m === null ? scale : height_m / dimensions.z;
      converted.scale.setScalar(factor);
      converted.position.set(-center.x * factor, -center.y * factor,
        -(anchor === 'feet' ? bounds.min.z : center.z) * factor);
      root.position.fromArray(position_m);
      root.rotation.z = yaw_rad;
      root.userData.assetId = assetId;
      root.userData.dimensionEvidence = 'Visual bind-pose bounds; not measured venue geometry';
      dimensions.multiplyScalar(factor);
      mixer = new THREE.AnimationMixer(model);
      let released = false;
      const handle = {
        root, asset, dimensions_m: dimensions.toArray(), clips: lease.value.animations,
        playClip(index) {
          if (released) throw new Error('Instance has been released.');
          if (!Number.isInteger(index) || !this.clips[index]) throw new Error('Unknown animation clip index.');
          mixer.stopAllAction();
          mixer.clipAction(this.clips[index]).reset().play();
        },
        setTime(filmingSeconds) {
          if (!Number.isFinite(filmingSeconds) || filmingSeconds < 0) throw new Error('Invalid filming time.');
          if (!released) mixer.setTime(filmingSeconds);
        },
        release() {
          if (released) return;
          released = true;
          root.removeFromParent();
          mixer.stopAllAction();
          mixer.uncacheRoot(model);
          const skeletons = new Set();
          model.traverse(object => { if (object.skeleton) skeletons.add(object.skeleton); });
          for (const skeleton of skeletons) skeleton.dispose?.();
          lease.release();
        },
      };
      return handle;
    } catch (error) {
      if (mixer && model) { mixer.stopAllAction(); mixer.uncacheRoot(model); }
      if (model) {
        const skeletons = new Set();
        model.traverse(object => { if (object.skeleton) skeletons.add(object.skeleton); });
        for (const skeleton of skeletons) skeleton.dispose?.();
      }
      lease.release();
      throw error;
    }
  }
}

/** Keep this root separate from the legacy procedural root and its disposal traversal. */
export class AssetLayer {
  constructor(scene, library) {
    this.root = new THREE.Group();
    scene.add(this.root);
    this.library = library;
    this.instances = [];
    this.epoch = new LoadEpoch();
  }

  clear() {
    this.epoch.advance();
    for (const instance of this.instances) instance.release();
    this.instances = [];
    this.root.clear();
  }

  async load(definitions) {
    this.clear();
    const epoch = this.epoch.value;
    // Sequential admission bounds simultaneous decoding and preserves authored order.
    const pending = [];
    try {
      for (const definition of definitions) {
        const instance = await this.library.createInstance(definition.asset_id, definition);
        pending.push(instance);
        if (!this.epoch.current(epoch)) {
          for (const created of pending) created.release();
          return false;
        }
      }
      for (const instance of pending) this.root.add(instance.root);
      this.instances = pending;
      return true;
    } catch (error) {
      for (const instance of pending) instance.release();
      throw error;
    }
  }

  pose(filmingSeconds) {
    for (const instance of this.instances) instance.setTime(filmingSeconds);
  }

  dispose() {
    this.clear();
    this.root.removeFromParent();
    this.library.cache.clearIdle();
  }
}
