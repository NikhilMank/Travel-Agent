import { useState, useEffect, useRef, useCallback } from "react"
import { BrowserRouter, Routes, Route, useNavigate } from "react-router-dom"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"
import { getChats, createChat, getChat, deleteChat, sendMessage, syncChat, API_BASE, onAuthError } from "./api"
import { AuthProvider, useAuth } from "./contexts/AuthContext"
import ProtectedRoute from "./components/ProtectedRoute"
import LoginPage from "./pages/LoginPage"
import RegisterPage from "./pages/RegisterPage"
import "./App.css"

const WELCOME = "Hi! I'm your travel agent assistant. I'll help you plan your perfect trip. Where would you like to go?"

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

function ChatApp() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [chats, setChats] = useState([])
  const [activeChatId, setActiveChatId] = useState(null)
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState("")
  const [sending, setSending] = useState(false)
  const [loading, setLoading] = useState(true)
  const messagesEnd = useRef(null)
  const inputRef = useRef(null)
  const dirtyRef = useRef(false)
  const activeChatIdRef = useRef(null)
  const messagesRef = useRef([])
  const [darkMode, setDarkMode] = useState(() => {
    const saved = localStorage.getItem("darkMode")
    if (saved !== null) return saved === "true"
    return window.matchMedia("(prefers-color-scheme: dark)").matches
  })

  useEffect(() => {
    onAuthError(() => {
      logout()
      navigate("/login")
    })
  }, [logout, navigate])

  const scrollToBottom = useCallback(() => {
    messagesEnd.current?.scrollIntoView({ behavior: "smooth" })
  }, [])

  useEffect(scrollToBottom, [messages, scrollToBottom])

  useEffect(() => {
    document.body.classList.toggle("dark", darkMode)
    localStorage.setItem("darkMode", darkMode)
    return () => document.body.classList.remove("dark")
  }, [darkMode])

  useEffect(() => {
    inputRef.current?.focus()
  }, [])

  useEffect(() => {
    activeChatIdRef.current = activeChatId
  }, [activeChatId])

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  function handleLogout() {
    syncCurrentChat()
    logout()
    navigate("/login")
  }

  async function syncCurrentChat() {
    if (!dirtyRef.current || !activeChatIdRef.current) return
    const msgs = messagesRef.current
    if (msgs.length === 0) return
    try {
      await syncChat(activeChatIdRef.current, msgs)
      dirtyRef.current = false
    } catch (e) {
      console.error("Sync failed:", e)
    }
  }

  useEffect(() => {
    function handleBeforeUnload(e) {
      if (!dirtyRef.current || !activeChatIdRef.current) return
      const msgs = messagesRef.current
      if (msgs.length === 0) return
      const token = localStorage.getItem("token")
      fetch(
        `${API_BASE}/chats/${activeChatIdRef.current}/sync`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            ...(token ? { Authorization: `Bearer ${token}` } : {}),
          },
          body: JSON.stringify({ messages: msgs.map((m) => ({ role: m.role, content: m.content, created_at: m.created_at })) }),
          keepalive: true,
        }
      ).catch(() => {})
    }
    window.addEventListener("beforeunload", handleBeforeUnload)
    return () => window.removeEventListener("beforeunload", handleBeforeUnload)
  }, [])

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

  function markDirty() {
    dirtyRef.current = true
  }

  async function loadChat(chatId) {
    try {
      const data = await getChat(chatId)
      setActiveChatId(data.id)
      activeChatIdRef.current = data.id
      const msgs = data.messages.map((m) => ({ role: m.role, content: m.content, created_at: m.created_at }))
      setMessages(msgs)
      messagesRef.current = msgs
      dirtyRef.current = false
    } catch (e) {
      console.error(e)
    }
  }

  async function newChat() {
    try {
      await syncCurrentChat()
      const chat = await createChat()
      const msgs = [{ role: "assistant", content: WELCOME, created_at: new Date().toISOString() }]
      setActiveChatId(chat.id)
      activeChatIdRef.current = chat.id
      setMessages(msgs)
      messagesRef.current = msgs
      dirtyRef.current = true
      const chatList = await getChats()
      setChats(chatList)
    } catch (e) {
      console.error(e)
    }
  }

  async function handleDelete(chatId, e) {
    e.stopPropagation()
    try {
      if (chatId === activeChatId) {
        await syncCurrentChat()
      }
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

  async function handleSelectChat(chatId) {
    await syncCurrentChat()
    await loadChat(chatId)
  }

  async function handleSend(e) {
    e.preventDefault()
    if (!input.trim() || !activeChatId || sending) return

    const userMsg = input.trim()
    setInput("")
    setMessages((prev) => [...prev, { role: "user", content: userMsg, created_at: new Date().toISOString() }])
    markDirty()
    setSending(true)

    try {
      const response = await sendMessage(userMsg, activeChatId)
      const ts = new Date().toISOString()
      const newMessages = [
        { role: "assistant", content: response.response, created_at: ts },
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
          created_at: ts,
        })
      }
      setMessages((prev) => [...prev, ...newMessages])
      markDirty()
      if (response.is_complete) {
        setTimeout(() => alert("🎉 Trip plan ready!"), 100)
      }
      const chatList = await getChats()
      setChats(chatList)
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: `Error: ${e.message}`, created_at: new Date().toISOString() },
      ])
    } finally {
      setSending(false)
      inputRef.current?.focus()
    }
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
        <div className="sidebar-header">
          <h1 className="sidebar-title">Travel Agent</h1>
          <button
            className="theme-toggle"
            onClick={() => setDarkMode((d) => !d)}
            title={darkMode ? "Switch to light mode" : "Switch to dark mode"}
          >
            {darkMode ? "☀️" : "🌙"}
          </button>
        </div>
        <div className="user-info">
          <span className="user-email">{user?.email}</span>
          <button className="logout-btn" onClick={handleLogout} title="Logout">
            ⏻
          </button>
        </div>
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
                <div className="bubble">
                  {msg.role === "assistant" || msg.role === "debug" ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    msg.content
                  )}
                </div>
              </div>
            ))
          )}
          <div ref={messagesEnd} />
        </div>
        <form className="input-bar" onSubmit={handleSend}>
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter your message"
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

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <ChatApp />
              </ProtectedRoute>
            }
          />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  )
}
