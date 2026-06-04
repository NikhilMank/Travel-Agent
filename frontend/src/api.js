export const API_BASE = import.meta.env.VITE_API_URL || "https://lmccfnmydj.execute-api.eu-central-1.amazonaws.com/api"

function getToken() {
  return localStorage.getItem("token")
}

function authHeaders(extra = {}) {
  const token = getToken()
  const headers = { ...extra }
  if (token) {
    headers["Authorization"] = `Bearer ${token}`
  }
  return headers
}

function handle401(r) {
  if (r.status === 401) {
    localStorage.removeItem("token")
    window.location.href = "/login"
    throw new Error("Session expired")
  }
}

export async function getChats() {
  const r = await fetch(`${API_BASE}/chats`, {
    headers: authHeaders(),
  })
  handle401(r)
  if (!r.ok) throw new Error("Failed to fetch chats")
  return r.json()
}

export async function createChat() {
  const r = await fetch(`${API_BASE}/chats`, {
    method: "POST",
    headers: authHeaders(),
  })
  handle401(r)
  if (!r.ok) throw new Error("Failed to create chat")
  return r.json()
}

export async function getChat(chatId) {
  const r = await fetch(`${API_BASE}/chats/${chatId}`, {
    headers: authHeaders(),
  })
  handle401(r)
  if (!r.ok) throw new Error("Chat not found")
  return r.json()
}

export async function deleteChat(chatId) {
  const r = await fetch(`${API_BASE}/chats/${chatId}`, {
    method: "DELETE",
    headers: authHeaders(),
  })
  handle401(r)
  if (!r.ok) throw new Error("Failed to delete chat")
  return r.json()
}

export async function sendMessage(message, sessionId) {
  const r = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  handle401(r)
  if (!r.ok) throw new Error("Failed to send message")
  return r.json()
}

export async function syncChat(chatId, messages) {
  const r = await fetch(`${API_BASE}/chats/${chatId}/sync`, {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify({ messages: messages.map((m) => ({ role: m.role, content: m.content, created_at: m.created_at })) }),
  })
  handle401(r)
  if (!r.ok) throw new Error("Failed to sync chat")
  return r.json()
}
