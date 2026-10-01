/* Real-location world: Google photorealistic context and TakeOne's planning world.
 *
 * Two layers, drawn together, never mixed:
 *
 *   photoreal  Google Photorealistic 3D Tiles. Display only. Nothing in this
 *              file reads a tile's geometry, samples it, raycasts against it or
 *              derives anything from it. It is a backdrop.
 *   planning   TakeOne's metric world, drawn from the server's planning_world
 *              payload. This is what the robot reasons over, and it is the only
 *              layer that carries a clearance claim.
 *
 * The tiles library loads lazily. A missing key, a blocked network or a failed
 * import leaves the planning world rendering exactly as before — the Hack the
 * North demo must not need Google to be up.
 */

import * as THREE from 'three';

/* These four match the page legend's tokens exactly, so what the filmmaker
 * reads in the legend is what they see in the world:
 *   --t1-ready      observed / open geometry
 *   --t1-sim        proposed / authored proxy
 *   --t1-attention  unknown — needs qualification
 * Google's photorealistic layer gets no overlay colour at all. It is the
 * backdrop, and nothing about it is evidence. */
export const EVIDENCE_COLORS = {
  open_map_geometry: '#7d9b83',
  operator_measurement: '#7d9b83',
  photo_scout_reconstruction: '#7d9b83',
  operator_confirmed_extent: '#7d9b83',
  authored_proxy: '#8a8a8a',
  unknown: '#b09256',
};

const ACTOR_COLOR = '#e8b04b';
const ROBOT_COLOR = '#5fc2d1';
const UNKNOWN_COLOR = '#b09256';
const SITE_FAR_M = 900;

/* Tiles are only worth this much detail: the robot travels metres, and a city
 * of maximum-detail tiles is what makes a laptop demo stutter. */
const TILE_ERROR_TARGET = 24;
const TILE_CACHE_MIN = 4000;
const TILE_CACHE_MAX = 8000;

const ring2d = points => points.map(([x, y]) => new THREE.Vector2(x, y));

function polygonMesh(ring, {color, opacity, z = 0, height = 0}) {
  const shape = new THREE.Shape(ring2d(ring));
  const geometry = height > 0
    ? new THREE.ExtrudeGeometry(shape, {depth: height, bevelEnabled: false})
    : new THREE.ShapeGeometry(shape);
  const material = new THREE.MeshStandardMaterial({
    color, transparent: true, opacity, roughness: .95, metalness: 0,
    side: THREE.DoubleSide, depthWrite: height > 0,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.position.z = z;
  return mesh;
}

function polygonOutline(ring, color, z, opacity = .9) {
  const points = ring.map(([x, y]) => new THREE.Vector3(x, y, z));
  points.push(points[0].clone());
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineBasicMaterial({color, transparent: true, opacity});
  return new THREE.LineLoop(geometry, material);
}

function disposeTree(object) {
  object.traverse(child => {
    if (child.geometry) child.geometry.dispose();
    const material = child.material;
    if (Array.isArray(material)) material.forEach(entry => entry.dispose());
    else if (material) material.dispose();
  });
  object.clear();
}

export function createLocationWorld({scene, camera, renderer, redraw = () => {}, onStatus = () => {}}) {
  const root = new THREE.Group();
  root.name = 'location-world';
  root.visible = false;
  scene.add(root);

  const planningGroup = new THREE.Group();
  const unknownGroup = new THREE.Group();
  const marksGroup = new THREE.Group();
  const pathGroup = new THREE.Group();
  root.add(planningGroup, unknownGroup, marksGroup, pathGroup);

  /* Annotation layer. Marks, routes and the unknown-ground wash are notes to
   * the filmmaker, not set dressing, so they must not appear in the film
   * camera's frame. Shot Studio already reserves layer 1 for world-view-only
   * objects; a host that has one camera enables layer 1 on it. */
  const ANNOTATION_LAYER = 1;
  const annotate = object => {object.traverse(child => child.layers.set(ANNOTATION_LAYER));};

  let tiles = null;
  let tilesGroup = null;
  let tilesState = 'off';
  let tilesMessage = '';
  let attributions = [];
  let record = null;
  let staging = null;
  const savedFar = camera.far;
  const metrics = {activeTiles: 0, cachedTiles: 0, downloading: 0, parsing: 0, lastUpdateMs: 0};

  const status = () => ({
    tiles: tilesState,
    tilesMessage,
    attributions: attributions.slice(),
    metrics: {...metrics},
    worldId: record?.world_id || null,
  });
  const announce = () => onStatus(status());

  /* ------------------------------------------------------------- planning */
  function setPlanningWorld(next) {
    record = next;
    disposeTree(planningGroup);
    disposeTree(unknownGroup);
    if (!next) {root.visible = false; redraw(); announce(); return;}
    const world = next.planning_world;
    root.visible = true;

    for (const region of world.ground_regions.concat(world.walkable_regions)) {
      const color = EVIDENCE_COLORS[region.evidence.source] || EVIDENCE_COLORS.open_map_geometry;
      const fill = polygonMesh(region.polygon_m, {color, opacity: region.walkable ? .3 : .16, z: .01});
      fill.userData.evidence = region.evidence;
      planningGroup.add(fill);
      planningGroup.add(polygonOutline(region.polygon_m, color, .012, .5));
    }
    for (const obstacle of world.static_obstacles) {
      const color = EVIDENCE_COLORS[obstacle.evidence.source] || EVIDENCE_COLORS.open_map_geometry;
      const height = Math.max(.4, Math.min(obstacle.max_z_m - obstacle.min_z_m, 60));
      const solid = polygonMesh(obstacle.footprint_polygon_m, {color, opacity: .22, z: obstacle.min_z_m, height});
      solid.userData.evidence = obstacle.evidence;
      planningGroup.add(solid);
      planningGroup.add(polygonOutline(obstacle.footprint_polygon_m, color, obstacle.min_z_m + .02, .85));
    }
    /* Unknown ground is drawn, deliberately, as its own colour. An unmarked
     * gap would read as empty floor, which is the one thing it is not. */
    /* A flat low-opacity fill, no outline: the grid is 6 m and outlining every
     * cell turns honest uncertainty into visual noise that hides the set. */
    for (const region of world.unknown_regions) {
      const patch = polygonMesh(region.polygon_m, {color: UNKNOWN_COLOR, opacity: .07, z: .004});
      patch.userData.unknown = true;
      annotate(patch);
      unknownGroup.add(patch);
    }
    redraw();
    announce();
  }

  /* -------------------------------------------------------------- staging */
  function setStaging(candidate) {
    disposeTree(marksGroup);
    disposeTree(pathGroup);
    staging = null;
    if (!candidate) {redraw(); return;}
    const actorStart = candidate.actor_start_m;
    const actorEnd = candidate.actor_end_m;
    const robot = candidate.robot_start_m;

    marksGroup.add(mark(actorStart, ACTOR_COLOR, .4, {post: 1.7}));
    if (actorEnd[0] !== actorStart[0] || actorEnd[1] !== actorStart[1]) {
      marksGroup.add(mark(actorEnd, ACTOR_COLOR, .34));
      pathGroup.add(line([actorStart, actorEnd], ACTOR_COLOR, .035, .16));
    }
    marksGroup.add(mark(robot, ROBOT_COLOR, .48, {post: 1.2}));
    const heading = candidate.actor_heading_rad;
    const travel = candidate.travel_m || 0;
    const robotEnd = [robot[0] + Math.cos(heading) * travel, robot[1] + Math.sin(heading) * travel];
    if (travel > 0.05) {
      pathGroup.add(line([robot, robotEnd], ROBOT_COLOR, .05, .24));
      marksGroup.add(mark(robotEnd, ROBOT_COLOR, .34));
    }
    staging = {
      points: [actorStart, actorEnd, robot, robotEnd],
    };
    annotate(marksGroup);
    annotate(pathGroup);
    redraw();
  }

  function mark(point, color, radius, {post = 0} = {}) {
    const group = new THREE.Group();
    const material = new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: .95, side: THREE.DoubleSide, depthWrite: false,
    });
    const ring = new THREE.Mesh(new THREE.RingGeometry(Math.max(.06, radius - .1), radius, 32), material);
    ring.position.set(point[0], point[1], .03);
    group.add(ring);
    /* A vertical pin so a 0.4 m mark is still findable from across the site. */
    if (post > 0) {
      const pin = new THREE.Mesh(new THREE.CylinderGeometry(.035, .035, post, 8), material);
      pin.rotation.x = Math.PI / 2;
      pin.position.set(point[0], point[1], post / 2);
      group.add(pin);
    }
    return group;
  }

  /* WebGL ignores lineWidth, and a one-pixel route is invisible over a 50 m
   site. Routes are drawn as thin ribbons so they read at any zoom. */
  function line(points, color, z, width = .18) {
    const group = new THREE.Group();
    const material = new THREE.MeshBasicMaterial({
      color, transparent: true, opacity: .92, side: THREE.DoubleSide, depthWrite: false,
    });
    for (let i = 0; i < points.length - 1; i += 1) {
      const [ax, ay] = points[i];
      const [bx, by] = points[i + 1];
      const length = Math.hypot(bx - ax, by - ay);
      if (length < 1e-4) continue;
      const strip = new THREE.Mesh(new THREE.PlaneGeometry(length, width), material);
      strip.position.set((ax + bx) / 2, (ay + by) / 2, z);
      strip.rotation.z = Math.atan2(by - ay, bx - ax);
      group.add(strip);
    }
    return group;
  }

  /* ---------------------------------------------------------------- tiles */
  async function enableTiles(config, anchor) {
    if (tiles) return status();
    if (!config || !config.available || !config.key) {
      tilesState = 'unavailable';
      tilesMessage = config?.message || 'Photorealistic context unavailable — planning world still active.';
      announce();
      return status();
    }
    tilesState = 'loading';
    tilesMessage = 'Loading photorealistic context…';
    announce();
    try {
      const [{TilesRenderer, WGS84_ELLIPSOID, ENU_FRAME}, plugins] = await Promise.all([
        import('3d-tiles-renderer'),
        import('3d-tiles-renderer/plugins'),
      ]);
      const {GoogleCloudAuthPlugin, TileCompressionPlugin, UpdateOnChangePlugin, UnloadTilesPlugin} = plugins;
      const instance = new TilesRenderer();
      instance.registerPlugin(new GoogleCloudAuthPlugin({apiToken: config.key, autoRefreshToken: true}));
      if (TileCompressionPlugin) instance.registerPlugin(new TileCompressionPlugin());
      if (UpdateOnChangePlugin) instance.registerPlugin(new UpdateOnChangePlugin());
      if (UnloadTilesPlugin) instance.registerPlugin(new UnloadTilesPlugin());
      instance.errorTarget = TILE_ERROR_TARGET;
      instance.lruCache.minSize = TILE_CACHE_MIN;
      instance.lruCache.maxSize = TILE_CACHE_MAX;
      instance.setCamera(camera);
      instance.setResolutionFromRenderer(camera, renderer);

      /* Put the site at the scene origin. This is a display transform on
       * display data; TakeOne's own metre frame is computed server-side by
       * location_scout.geodesy and never comes from here. */
      const matrix = new THREE.Matrix4();
      const heading = ((anchor.heading_deg || 0) * Math.PI) / 180;
      WGS84_ELLIPSOID.getObjectFrame(
        (anchor.lat_deg * Math.PI) / 180,
        (anchor.lon_deg * Math.PI) / 180,
        anchor.alt_m || 0,
        heading, 0, 0, matrix, ENU_FRAME);
      matrix.invert();
      instance.group.matrix.copy(matrix);
      instance.group.matrixAutoUpdate = false;
      instance.group.updateMatrixWorld(true);
      /* The site frame is +X along the heading, +Y 90 deg CCW, +Z up. ENU_FRAME
       * gives +X east, +Y north, +Z up, so rotate the group into TakeOne's. */
      const toSite = new THREE.Matrix4().makeRotationZ(-Math.PI / 2);
      instance.group.matrix.premultiply(toSite);
      instance.group.updateMatrixWorld(true);

      instance.addEventListener('load-tile-set', () => {
        tilesState = 'active';
        tilesMessage = '';
        refreshAttributions();
      });
      instance.addEventListener('load-error', () => {
        if (tilesState !== 'active') {
          tilesState = 'unavailable';
          tilesMessage = 'Photorealistic context unavailable — planning world still active.';
          announce();
        }
      });

      tiles = instance;
      tilesGroup = instance.group;
      scene.add(tilesGroup);
      camera.far = SITE_FAR_M;
      camera.updateProjectionMatrix();
      redraw();
      announce();
    } catch (error) {
      tilesState = 'unavailable';
      tilesMessage = 'Photorealistic context unavailable — planning world still active.';
      announce();
    }
    return status();
  }

  function refreshAttributions() {
    if (!tiles) {attributions = []; announce(); return;}
    let entries = [];
    try {entries = tiles.getAttributions() || [];} catch (error) {entries = [];}
    attributions = entries
      .map(entry => (typeof entry === 'string' ? entry : entry && entry.value))
      .filter(value => typeof value === 'string' && value.length)
      .slice(0, 12);
    announce();
  }

  function disableTiles() {
    if (!tiles) return;
    try {tiles.dispose();} catch (error) {/* disposal is best effort */}
    if (tilesGroup) scene.remove(tilesGroup);
    tiles = null; tilesGroup = null;
    attributions = [];
    tilesState = 'off';
    tilesMessage = '';
    camera.far = savedFar;
    camera.updateProjectionMatrix();
    metrics.activeTiles = 0; metrics.cachedTiles = 0; metrics.downloading = 0; metrics.parsing = 0;
    redraw();
    announce();
  }

  /* Called from the host page's paint(). Returns true while tiles are still
   * settling so the on-demand loop keeps drawing, and false once they are
   * quiet — no unconditional animation frame is ever scheduled here. */
  function update() {
    if (!tiles || !root.visible) return false;
    const started = performance.now();
    tiles.setResolutionFromRenderer(camera, renderer);
    camera.updateMatrixWorld();
    tiles.update();
    metrics.lastUpdateMs = performance.now() - started;
    const stats = tiles.stats || {};
    const downloading = stats.downloading || 0;
    const parsing = stats.parsing || 0;
    if (downloading !== metrics.downloading || parsing !== metrics.parsing) {
      metrics.downloading = downloading;
      metrics.parsing = parsing;
      metrics.activeTiles = stats.visible || 0;
      metrics.cachedTiles = stats.inCache || 0;
      if (!downloading && !parsing) refreshAttributions();
    }
    return downloading > 0 || parsing > 0;
  }

  function showLayers({photoreal = true, planning = true, unknown = true, marks = true, path = true} = {}) {
    if (tilesGroup) tilesGroup.visible = photoreal;
    planningGroup.visible = planning;
    unknownGroup.visible = unknown;
    marksGroup.visible = marks;
    pathGroup.visible = path;
    redraw();
  }

  function setVisible(visible) {
    root.visible = visible && !!record;
    if (tilesGroup) tilesGroup.visible = visible;
    redraw();
  }

  function dispose() {
    disableTiles();
    disposeTree(planningGroup); disposeTree(unknownGroup);
    disposeTree(marksGroup); disposeTree(pathGroup);
    scene.remove(root);
    record = null;
  }

  /* Where the shot actually is, so a caller can frame it. */
  function stagingBounds() {
    if (!staging) return null;
    const xs = staging.points.map(point => point[0]);
    const ys = staging.points.map(point => point[1]);
    return {
      centre: [(Math.min(...xs) + Math.max(...xs)) / 2, (Math.min(...ys) + Math.max(...ys)) / 2],
      radius: Math.max(3, Math.hypot(Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)) / 2),
    };
  }

  return {
    root, setPlanningWorld, setStaging, enableTiles, disableTiles, update,
    showLayers, setVisible, dispose, status, refreshAttributions, stagingBounds,
    get hasWorld() {return !!record;},
  };
}
