const API_BASE = import.meta.env.VITE_API_URL || "https://lmccfnmydj.execute-api.eu-central-1.amazonaws.com/api"

export async function getChats() {
  const r = await fetch(`${API_BASE}/chats`)
  if (!r.ok) throw new Error("Failed to fetch chats")
  return r.json()
}

export async function createChat() {
  const r = await fetch(`${API_BASE}/chats`, { method: "POST" })
  if (!r.ok) throw new Error("Failed to create chat")
  return r.json()
}

export async function getChat(chatId) {
  const r = await fetch(`${API_BASE}/chats/${chatId}`)
  if (!r.ok) throw new Error("Chat not found")
  return r.json()
}

export async function deleteChat(chatId) {
  const r = await fetch(`${API_BASE}/chats/${chatId}`, { method: "DELETE" })
  if (!r.ok) throw new Error("Failed to delete chat")
  return r.json()
}

export async function sendMessage(message, sessionId) {
  const r = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, session_id: sessionId }),
  })
  if (!r.ok) throw new Error("Failed to send message")
  return r.json()
}

export async function syncChat(chatId, messages) {
  const r = await fetch(`${API_BASE}/chats/${chatId}/sync`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: messages.map((m) => ({ role: m.role, content: m.content })) }),
  })
  if (!r.ok) throw new Error("Failed to sync chat")
  return r.json()
}


