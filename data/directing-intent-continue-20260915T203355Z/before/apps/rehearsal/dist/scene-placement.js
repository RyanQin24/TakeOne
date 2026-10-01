// World-space placement uses metres. The editor displays feet at its boundary.
export const sceneDefaults=()=>({actor_position_m:[0,0],cart_start_m:null,route_rotation_rad:0,
  actor_facing:'opening',actor_heading_rad:0,filming_side:'phone',actor_motion:'preset',walk_distance_m:1.5,walk_heading_rad:0});

export function transformRoute(points,start=null,angle=0) {
  if(!points.length)return [];
  const origin=points[0],target=start||origin,c=Math.cos(angle),s=Math.sin(angle);
  return points.map(p=>{const x=p[0]-origin[0],y=p[1]-origin[1];return [target[0]+c*x-s*y,target[1]+s*x+c*y];});
}

export function editablePath(settings) {
  // The drawing canvas edits world points. Bake an imported route placement
  // once, then clear only that transform so redraw/save cannot apply it twice.
  const scene={...sceneDefaults(),...settings.scene};
  return {...settings,points_m:transformRoute(settings.points_m,scene.cart_start_m,scene.route_rotation_rad),
    scene:{...scene,cart_start_m:null,route_rotation_rad:0}};
}
