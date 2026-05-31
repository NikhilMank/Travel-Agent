import { useState, useEffect, useRef, useCallback } from "react"
import { getChats, createChat, getChat, deleteChat, sendMessage, getWelcome } from "./api"
import "./App.css"

function relativeTime(iso) {
  if (!iso) return ""
  const diff = (Date.now() - new Date(iso).getTime()) / 1000
  if (diff < 60) return "just now"
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff / 86400)}d ago`
  return new Date(iso).toLocaleDateString()
}

function truncate(text, len = 32) {
  if (!text || text.length <= len) return text
  return text.slice(0, len).split(" ").slice(0, -1).join(" ") + "..."
}

export default function App() {
  const [chats, setChats] = useState([])
  const [activeChatId, setActiveChatId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const messagesEnd = useRef(null)

  const scrollToBottom = useCallback(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  useEffect(scrollToBottom, [messages, scrollToBottom])

  useEffect(() => {
    ;(async () => {
      try {
        const chatList = await getChats()
        setChats(chatList)
        if (chatList.length > 0) {
          await loadChat(chatList[0].id)
        } else {
          await newChat()
        }
      } catch (e) {
        console.error(e)
      } finally {
        setLoading(false)
      }
    })()
  }, [])

  async function loadChat(chatId) {
    try {
      const data = await getChat(chatId)
      setActiveChatId(data.id)
      setMessages(data.messages.map((m) => ({ role: m.role, content: m.content })))
    } catch (e) {
      console.error(e)
    }
  }

  async function newChat() {
    try {
      const chat = await createChat()
      setActiveChatId(chat.id)
      setMessages([])
      const welcome = await getWelcome()
      setMessages([{ role: "assistant", content: welcome.response }])
      const chatList = await getChats()
      setChats(chatList)
    } catch (e) {
      console.error(e)
    }
  }

  async function handleDelete(chatId, e) {
    e.stopPropagation()
    try {
      await deleteChat(chatId)
      if (activeChatId === chatId) {
        const chatList = await getChats()
        const remaining = chatList.filter((c) => c.id !== chatId)
        setChats(remaining)
        if (remaining.length > 0) {
          await loadChat(remaining[0].id)
        } else {
          await newChat()
        }
      } else {
        setChats((prev) => prev.filter((c) => c.id !== chatId))
      }
    } catch (e) {
      console.error(e)
    }
  }

  async function handleSend(e) {
    e.preventDefault()
    if (!input.trim() || !activeChatId || sending) return

    const userMsg = input.trim()
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content: userMsg }])
    setSending(true)

    try {
      const response = await sendMessage(userMsg, activeChatId)
      const newMessages = [
        { role: "assistant", content: response.response },
      ]
      if (response.tool_calls?.length || response.worker_sources?.length) {
        const steps = []
        if (response.tool_calls?.length) {
          steps.push(`🔧 ${response.tool_calls.join(", ")}`)
        }
        if (response.worker_sources?.length) {
          steps.push(...response.worker_sources.map((s) => `📚 ${s}`))
        }
        newMessages.push({
          role: "debug",
          content: steps.join("\n"),
        })
      }
      setMessages((prev) => [...prev, ...newMessages])
      if (response.is_complete) {
        setTimeout(() => alert("🎉 Trip plan ready!"), 100)
      }
      const chatList = await getChats()
      setChats(chatList)
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${e.message}` },
      ])
    } finally {
      setSending(false)
    }
  }

  async function handleSelectChat(chatId) {
    if (chatId === activeChatId) return
    await loadChat(chatId)
  }

  if (loading) {
    return (
      <div className="loading">
        <div className="spinner" />
        <p>Loading...</p>
      </div>
    )
  }

  return (
    <div className="app">
      <aside className="sidebar">
        <h1 className="sidebar-title">Travel Agent</h1>
        <button className="new-chat-btn" onClick={newChat}>
          + New Chat
        </button>
        <nav className="chat-list">
          {chats.map((chat) => (
            <div
              key={chat.id}
              className={`chat-item ${chat.id === activeChatId ? "active" : ""}`}
              onClick={() => handleSelectChat(chat.id)}
            >
              <span className="chat-title">{truncate(chat.title)}</span>
              <span className="chat-meta">
                <span className="chat-time">{relativeTime(chat.updated_at)}</span>
                <button
                  className="delete-btn"
                  onClick={(e) => handleDelete(chat.id, e)}
                  title="Delete chat"
                >
                  ✕
                </button>
              </span>
            </div>
          ))}
        </nav>
      </aside>
      <main className="main">
        <div className="messages">
          {messages.length === 0 ? (
            <div className="empty-state">
              <p>Plan your perfect trip! Tell me about your travel plans.</p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <div key={i} className={`message ${msg.role}`}>
                <div className="avatar">
                  {msg.role === "user" ? "👤" : msg.role === "debug" ? "🔍" : "🤖"}
                </div>
                <div className="bubble">{msg.content}</div>
              </div>
            ))
          )}
          <div ref={messagesEnd} />
        </div>
        <form className="input-bar" onSubmit={handleSend}>
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="What's your travel plan?"
            disabled={sending}
          />
          <button type="submit" disabled={sending || !input.trim()}>
            {sending ? "..." : "Send"}
          </button>
        </form>
      </main>
    </div>
  )
}
