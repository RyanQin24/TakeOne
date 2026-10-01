// Microphone capture for the live director conversation. Runs on the audio
// thread: accumulate 128-frame render quanta into ~20 ms blocks and post them
// with an RMS reading so the main thread can gate on energy without touching
// samples twice. No network, no state beyond the current block.
class TakeOneCapture extends AudioWorkletProcessor {
  constructor() {
    super();
    this.block = new Float32Array(320); // 20 ms at 16 kHz
    this.filled = 0;
  }
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (!channel) return true;
    let offset = 0;
    while (offset < channel.length) {
      const take = Math.min(channel.length - offset, this.block.length - this.filled);
      this.block.set(channel.subarray(offset, offset + take), this.filled);
      this.filled += take;
      offset += take;
      if (this.filled === this.block.length) {
        let sum = 0;
        for (let i = 0; i < this.block.length; i++) sum += this.block[i] * this.block[i];
        const samples = this.block;
        this.port.postMessage(
          {samples, rms: Math.sqrt(sum / samples.length)},
          [samples.buffer],
        );
        this.block = new Float32Array(320);
        this.filled = 0;
      }
    }
    return true;
  }
}
registerProcessor('takeone-capture', TakeOneCapture);
