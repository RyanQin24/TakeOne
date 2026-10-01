// Final, explicit operator commands. Conversation and partial transcripts never
// toggle the transport; Start and Stop are separate, idempotent actions.
export function filmingCommand(transcript) {
  const text = String(transcript || '').toLowerCase().trim().replace(/[.,!]+$/g, '').trim();
  if (/^(?:please )?(?:start (?:filming|shooting|recording)|roll (?:the )?camera)(?: please)?$/.test(text)) return 'start';
  if (/^(?:please )?(?:stop(?: (?:filming|shooting|recording|the shot|shot))?|cut)(?: please)?$/.test(text)) return 'stop';
  return null;
}

export const VOICE_HELP = 'Say “start filming” for the selected shot, or “stop filming” / “cut” to stop.';

export class FilmingVoice {
  constructor({Recognition, onCommand, onStatus = () => {}, now = () => performance.now(),
    setTimer = (fn, delay) => globalThis.setTimeout(fn, delay), clearTimer = timer => globalThis.clearTimeout(timer)}) {
    Object.assign(this, {Recognition, onCommand, onStatus, now, setTimer, clearTimer});
    this.wanted = false;
    this.recognition = null;
    this.retry = null;
    this.last = null;
    this.pendingStart = false;
    this.pendingStop = false;
    this.generation = 0;
  }

  start() {
    if (this.wanted) return;
    if (!this.Recognition) {
      this.onStatus('unavailable', 'Voice commands are unavailable in this browser. Open Record in Chrome and allow microphone access.');
      return;
    }
    this.wanted = true;
    this.last = null;
    this.generation++;
    this.listen();
  }

  listen() {
    if (!this.wanted) return;
    const generation = this.generation;
    const recognition = new this.Recognition();
    this.recognition = recognition;
    recognition.lang = 'en-US';
    recognition.continuous = true;
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    const current = () => this.wanted && this.recognition === recognition && generation === this.generation;
    const consumed = new Set();
    recognition.onstart = () => { if (current()) this.onStatus('listening', VOICE_HELP); };
    recognition.onresult = event => {
      if (!current()) return;
      for (let index = event.resultIndex; index < event.results.length; index++) {
        const result = event.results[index];
        if (!result.isFinal || consumed.has(index)) continue;
        consumed.add(index);
        void this.accept(result[0]?.transcript, generation);
      }
    };
    recognition.onerror = event => {
      if (!current() || event.error === 'no-speech') return;
      const reasons = {
        'not-allowed': 'Microphone access was denied. Allow it for this page, then start voice control again.',
        'service-not-allowed': 'This browser cannot use its speech service. Try Chrome, then start voice control again.',
        'audio-capture': 'No microphone is available. Connect one, then start voice control again.',
        network: 'The browser speech service could not connect. Check your connection, then start voice control again.',
      };
      this.stop();
      this.onStatus('error', reasons[event.error] || `Voice recognition stopped (${event.error}). Start voice control to retry.`);
    };
    recognition.onend = () => {
      if (!current()) return;
      this.recognition = null;
      this.onStatus('connecting', 'Reconnecting the microphone…');
      this.retry = this.setTimer(() => { this.retry = null; this.listen(); }, 300);
    };
    this.onStatus('connecting', 'Allow microphone access to enable filming commands.');
    try { recognition.start(); }
    catch (error) { this.stop(); this.onStatus('error', error.message || 'The microphone could not start.'); }
  }

  async accept(transcript, generation) {
    const command = filmingCommand(transcript);
    if (!command) {
      this.onStatus('listening', `Heard “${String(transcript || '').slice(0, 160)}”. ${VOICE_HELP}`);
      return;
    }
    const time = this.now();
    if (this.last?.command === command && time - this.last.time < 2000) return;
    if (command === 'start' && (this.pendingStart || this.pendingStop)) return;
    if (command === 'stop' && this.pendingStop) return;
    this.last = {command, time};
    const pending = command === 'start' ? 'pendingStart' : 'pendingStop';
    this[pending] = true;
    this.onStatus('listening', command === 'start' ? 'Heard “start filming”. Checking the selected shot…' : 'Heard “stop filming”. Stopping…');
    try {
      const result = await this.onCommand(command);
      if (this.wanted && generation === this.generation && this.last?.command === command)
        this.onStatus('listening', result?.message || VOICE_HELP);
    } catch (error) {
      if (this.wanted && generation === this.generation && this.last?.command === command)
        this.onStatus('listening', error.message || 'The filming command could not complete.');
    } finally { this[pending] = false; }
  }

  stop() {
    this.wanted = false;
    this.generation++;
    this.clearTimer(this.retry);
    this.retry = null;
    const recognition = this.recognition;
    this.recognition = null;
    try { recognition?.abort(); } catch { /* Already disconnected. */ }
    this.onStatus('off', VOICE_HELP);
  }
}
