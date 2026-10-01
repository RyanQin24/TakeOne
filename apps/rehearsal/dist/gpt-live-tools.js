// Responses delegation has nested events. A completed response's output is empty;
// collect finished function items, then return ALL outputs before response.create.
export class LiveToolLoop {
  constructor({execute, send, report = () => {}}) {
    Object.assign(this, {execute, send, report});
    this.responses = new Map();
    this.current = new Map();
    this.closed = false;
  }

  close() { this.closed = true; this.responses.clear(); this.current.clear(); }

  async handle(envelope) {
    if (this.closed || envelope.type !== 'response.event') return;
    const event = envelope.event;
    const delegation = envelope.delegation_id;
    if (event?.type === 'response.created') {
      const id = event.response.id;
      this.current.set(delegation, id);
      this.responses.set(id, {calls: new Map(), processing: false});
    }
    const id = event?.response?.id || event?.response_id || this.current.get(delegation);
    const response = this.responses.get(id);
    if (!response) return;
    if (event.type === 'response.output_item.done' && event.item?.type === 'function_call') {
      response.calls.set(event.item.call_id, event.item);
    }
    if (['response.failed', 'response.incomplete', 'response.cancelled'].includes(event.type)) {
      this.responses.delete(id);
      this.report('Backend request failed', {ok: false, message: event.response?.error?.message || event.type});
      return;
    }
    if (event.type !== 'response.completed' || response.processing) return;
    response.processing = true;
    for (const call of response.calls.values()) {
      if (this.closed) return;
      let result;
      try {
        result = await this.execute({call_id: call.call_id, name: call.name, arguments: JSON.parse(call.arguments)});
      } catch (error) {
        result = {ok: false, code: 'tool_transport_failed', message: error.message, physical_state: 'unknown'};
      }
      if (this.closed) return;
      this.report(call.name, result);
      this.send({type: 'response.item.create', event_id: `result_${call.call_id}`,
        item: {type: 'function_call_output', call_id: call.call_id, output: JSON.stringify(result)}});
    }
    if (!this.closed && response.calls.size) this.send({type: 'response.create'});
    this.responses.delete(id);
  }
}
