async function unwrap(res) {
  if (res.ok) return res
  let message = res.statusText || `HTTP ${res.status}`
  try {
    const body = await res.json()
    if (body && body.detail) {
      message = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    }
  } catch {
    // 非 JSON 错误体，保留状态文本
  }
  throw new Error(message)
}

export async function getJson(url) {
  return (await unwrap(await fetch(url))).json()
}

export async function postJson(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  return (await unwrap(res)).json()
}
