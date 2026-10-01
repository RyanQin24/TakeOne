// Read-only planning requests may be retried across a local server restart.
// Robot start/stop requests deliberately use their own client.
export async function plannerRequest(url, body, {
  request = fetch, retries = 20, delay = ms => new Promise(resolve => setTimeout(resolve, ms)),
  onRetry = () => {},
} = {}) {
  const options = body === undefined ? undefined : {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body),
  };
  for (let attempt = 0; ; attempt++) {
    let response, result;
    try {
      response = await request(url, options);
      result = await response.json();
    } catch (error) {
      if (!(error instanceof TypeError) || attempt >= retries) throw error;
      onRetry('Reconnecting to the simulator…');
      await delay(1000);
      continue;
    }
    if (response.ok) return result;
    const message = result.error || result.message || 'The simulator could not calculate this.';
    const restarting = result.code === 'planner_restarting' || message.includes('stale code or drive settings');
    if (attempt >= retries || (!restarting && response.status !== 503)) throw new Error(message);
    onRetry(restarting ? 'Simulator restarting into the new code…' : 'Waiting for the planner…');
    await delay(1000);
  }
}
