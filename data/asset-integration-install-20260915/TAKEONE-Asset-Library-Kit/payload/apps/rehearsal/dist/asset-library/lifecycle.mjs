/** Promise-backed, bounded LRU cache. Source resources outlive all their instances. */
export class ResourceCache {
  constructor({maxEntries = 16, maxBytes = 64 * 1024 * 1024, dispose = () => {}} = {}) {
    this.entries = new Map();
    this.maxEntries = maxEntries;
    this.maxBytes = maxBytes;
    this.dispose = dispose;
    this.clock = 0;
  }

  get bytes() {
    return [...this.entries.values()].reduce((sum, entry) => sum + entry.bytes, 0);
  }

  evictOne() {
    const idle = [...this.entries.entries()]
      .filter(([, entry]) => entry.refs === 0 && entry.ready)
      .sort((a, b) => a[1].used - b[1].used);
    if (!idle.length) return false;
    const [key, entry] = idle[0];
    this.entries.delete(key);
    this.dispose(entry.value);
    return true;
  }

  async acquire(key, bytes, load) {
    if (!Number.isFinite(bytes) || bytes <= 0) throw new Error('Missing or invalid asset byte budget.');
    let entry = this.entries.get(key);
    if (!entry) {
      while (this.entries.size >= this.maxEntries || this.bytes + bytes > this.maxBytes) {
        if (!this.evictOne()) throw new Error('Asset cache budget exceeded. Reduce scene detail or configure a measured budget.');
      }
      entry = {refs: 0, ready: false, bytes, used: ++this.clock};
      this.entries.set(key, entry);
      entry.promise = Promise.resolve().then(load).then(value => {
        entry.value = value;
        entry.ready = true;
        return value;
      }).catch(error => {
        if (this.entries.get(key) === entry) this.entries.delete(key);
        throw error;
      });
    }
    entry.refs++;
    entry.used = ++this.clock;
    let released = false;
    const release = () => {
      if (released) return;
      released = true;
      entry.refs--;
      entry.used = ++this.clock;
    };
    try {
      return {value: await entry.promise, release};
    } catch (error) {
      release();
      throw error;
    }
  }

  clearIdle() {
    while (this.evictOne()) { /* Evict only this cache's unused sources. */ }
  }
}

/** A stale scene load must release resources, never appear in the next scene. */
export class LoadEpoch {
  constructor() { this.value = 0; }
  advance() { return ++this.value; }
  current(value) { return value === this.value; }
}
