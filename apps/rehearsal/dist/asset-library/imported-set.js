import {AssetLibrary, AssetLayer} from './asset-loader.js';
import {LoadEpoch} from './lifecycle.mjs';

/** An independent visual layer; never traversed by procedural-geometry disposal. */
export function createImportedSet(scene, onChange = () => {}) {
  const epoch = new LoadEpoch();
  let layer = null, opening = null, pending = Promise.resolve(true);
  let state = 'empty', status = null;
  function createStatus() {
  const status = document.createElement('div');
  status.setAttribute('role', 'status');
  status.dataset.sceneAssetStatus = 'empty';
  status.style.cssText = 'position:fixed;bottom:12px;left:12px;z-index:20;max-width:460px;padding:8px 12px;'
    + 'background:var(--t1-panel);color:var(--t1-fg);border-radius:var(--t1-r-panel);'
    + 'font-size:var(--t1-text-body);pointer-events:none';
  status.hidden = true;
  document.body.append(status);
  return status;
  }
  function message(next, text) {
    state = next;
    if (!status && state === 'empty') return;
    status ||= createStatus();
    status.dataset.sceneAssetStatus = state;
    status.textContent = text;
    status.hidden = state === 'empty';
  }
  function clear() {
    epoch.advance();
    layer?.clear();
    message('empty', '');
  }
  async function acquire(definitions) {
    if (!opening) opening = AssetLibrary.open().catch(error => { opening = null; throw error; });
    let library = await opening;
    if (definitions.some(item => !library.assets.has(item.asset_id))) {
      const refreshed = await AssetLibrary.open();
      library.assets = refreshed.assets;
    }
    return library;
  }
  function load(objects) {
    clear();
    const definitions = objects.filter(item => item.asset_id.startsWith('lib:'));
    if (!definitions.length) return pending = Promise.resolve(true);
    const ticket = epoch.value;
    message('loading', `Loading ${definitions.length} imported visual models...`);
    pending = (async () => {
      try {
        const library = await acquire(definitions);
        if (!epoch.current(ticket)) return false;
        layer ||= new AssetLayer(scene, library);
        const applied = await layer.load(definitions);
        if (!epoch.current(ticket) || !applied) return false;
        definitions.forEach((definition,index)=>{const root=layer.instances[index]?.root;if(root){root.userData.sceneObjectId=definition.object_id;root.userData.productionRole=definition.production_role||'';}});
        message('ready', `${definitions.length} imported models  -  visualization, not measured props`);
        onChange();
        return true;
      } catch (error) {
        if (epoch.current(ticket)) message('error', `Scene models unavailable: ${error.message}`);
        return false; // The visible error remains; never substitute a successful primitive.
      }
    })();
    return pending;
  }
  return {load, clear, get ready() { return pending; }, get state() { return state; },
    dispose() { clear(); layer?.dispose(); status?.remove(); }};
}
