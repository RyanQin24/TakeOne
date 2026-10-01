// Request timestamps stay decimal strings across the browser/server boundary.
export function envelope(runtime, operationId) {
  return {
    schema_version: 1,
    operation_id: operationId,
    runtime_epoch: runtime.runtime_epoch,
    expires_monotonic_ns: (BigInt(runtime.now_monotonic_ns) + BigInt(runtime.command_ttl_ns)).toString(),
  };
}

export function sessionScope(session) {
  return {
    session_id: session.session_id,
    expected_revision: session.revision,
    cancellation_generation: session.cancellation_generation,
    take_id: session.take_id,
    plan_id: session.shot ? session.shot.plan_id : null,
  };
}

export class ResponseError extends Error {
  constructor(status, payload) {
    super(payload.message || payload.error || 'The request was rejected.');
    this.status = status;
    this.payload = payload;
  }
}

export async function requestJSON(path, options = {}, transport = fetch) {
  const response = await transport(path, {cache: 'no-store', ...options});
  const payload = await response.json();
  if (!response.ok) throw new ResponseError(response.status, payload);
  return payload;
}
