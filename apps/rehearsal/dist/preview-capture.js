// Opt-in deterministic simulation capture. No device or recording-app API.
// The application supplies its existing pose/render functions; no second scene.
export function installPreviewCapture({ready,info,seek,render}) {
  if(!new URLSearchParams(location.search).has('capture'))return;
  const canvas=document.createElement('canvas'),context=canvas.getContext('2d');
  window.takeonePreview=Object.freeze({
    get ready(){return ready();},
    info(){if(!ready())throw new Error('Preview is not ready.');return info();},
    frame(seconds,view='phone',width=960,height=540){
      if(!ready())throw new Error('Capture is unavailable during compilation or robot activity.');
      if(!Number.isFinite(seconds)||seconds<0||seconds>info().duration_s)throw new Error('Capture time is outside this preview.');
      if(!['phone','world','both'].includes(view)||!Number.isInteger(width)||!Number.isInteger(height)||width<320||width>1920||height<180||height>1080)throw new Error('Invalid capture view or dimensions.');
      seek(seconds);const images=render(view,width,height),meta=info();
      const outputWidth=width*images.length;
      if(canvas.width!==outputWidth||canvas.height!==height+28){canvas.width=outputWidth;canvas.height=height+28;}
      images.forEach((image,index)=>context.drawImage(image,index*width,0,width,height));
      context.fillStyle='rgba(12,20,26,.8)';context.fillRect(0,height,outputWidth,28);
      context.fillStyle='#ffffff';context.font='14px monospace';
      context.fillText(`SIMULATED ${view.toUpperCase()} | ${meta.shot_id||'shot'} | ${seconds.toFixed(3)} s | ${meta.document_digest?.slice(0,12)||meta.plan_id?.slice(0,12)||''}`,12,height+19);
      return {png:canvas.toDataURL('image/png'),...meta,time_s:seconds,viewpoint:view,width:outputWidth,height:height+28,content_height:height};
    }
  });
}
