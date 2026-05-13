/**
 * Stream an AI generation/edit over Server-Sent Events.
 *
 * @param {{prompt:string, currentHtml?:string, path?:string}} payload
 * @param {{onDelta?:(text:string)=>void, onDone?:(r:{html:string,raw:string})=>void,
 *          onError?:(msg:string)=>void, signal?:AbortSignal}} handlers
 */
export async function streamChat(payload, handlers = {}) {
  const { onDelta, onDone, onError, signal } = handlers
  let resp
  try {
    resp = await fetch('/api/ai/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal
    })
  } catch (e) {
    if (e.name === 'AbortError') return
    onError?.(e.message || 'network error')
    return
  }

  if (!resp.ok || !resp.body) {
    let msg = `HTTP ${resp.status}`
    try {
      const j = await resp.json()
      msg = j.error || msg
    } catch { /* ignore */ }
    onError?.(msg)
    return
  }

  const reader = resp.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  try {
    while (true) {
      const { value, done } = await reader.read()
      if (done) break
      buf += decoder.decode(value, { stream: true })
      let idx
      while ((idx = buf.indexOf('\n\n')) !== -1) {
        const frame = buf.slice(0, idx)
        buf = buf.slice(idx + 2)
        const line = frame.split('\n').find((l) => l.startsWith('data:'))
        if (!line) continue
        let evt
        try {
          evt = JSON.parse(line.slice(5).trim())
        } catch { continue }
        if (evt.type === 'delta') onDelta?.(evt.text || '')
        else if (evt.type === 'done') onDone?.({ html: evt.html || '', raw: evt.raw || '' })
        else if (evt.type === 'error') onError?.(evt.message || 'error')
      }
    }
  } catch (e) {
    if (e.name !== 'AbortError') onError?.(e.message || 'stream error')
  }
}
