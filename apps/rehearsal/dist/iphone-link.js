// Only explicitly linked film-lens changes enter this bounded queue.
export class LatestZoom {
  constructor(send, failed=()=>{}, period=100) {
    Object.assign(this, {send, failed, period, enabled:false, busy:false, desired:null,
      sent:null, inFlight:false, timer:null});
  }
  offer(focal) {if(Number.isFinite(focal))this.desired=focal;this.schedule();}
  setEnabled(value) {this.enabled=value;this.schedule();}
  setBusy(value) {this.busy=value;this.schedule();}
  schedule() {
    if(!this.enabled || this.busy) {clearTimeout(this.timer);this.timer=null;return;}
    if(this.timer!==null || this.inFlight || this.desired===null || this.desired===this.sent)return;
    this.timer=setTimeout(()=>{this.timer=null;this.flush();},this.period);
  }
  async flush() {
    if(!this.enabled || this.busy || this.inFlight || this.desired===null)return;
    const target=this.desired;this.inFlight=true;
    try {await this.send(target);this.sent=target;}
    catch(error) {this.enabled=false;this.failed(error);}
    finally {this.inFlight=false;this.schedule();}
  }
  close() {this.enabled=false;clearTimeout(this.timer);this.timer=null;}
}
