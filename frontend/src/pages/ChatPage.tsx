import { useState, useEffect, useRef } from 'react'
import { Layout, Menu, Input, Button, message, Typography } from 'antd'
import { MessageOutlined, PlusOutlined, DeleteOutlined, BookOutlined, SettingOutlined, LogoutOutlined, SyncOutlined, StopOutlined } from '@ant-design/icons'
import { chatAPI, type Session, type Message as ChatMessage } from '../services/chatService'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import ProductShowcase from '../components/ProductShowcase'

const { Sider, Content, Header } = Layout
const { TextArea } = Input
const { Text } = Typography

// 解析助手消息中的引用来源（JSON 字符串）
function ReferenceList({ references }: { references?: string }) {
  if (!references) return null
  try {
    const refs = JSON.parse(references)
    if (!Array.isArray(refs) || refs.length === 0) return null
    return (
      <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px dashed #D9CDBB', fontSize: 12, color: '#8B6F47' }}>
        <div style={{ fontWeight: 600, marginBottom: 4 }}>引用来源：</div>
        {refs.map((r: any, i: number) => (
          <div key={i} style={{ marginBottom: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            [{i + 1}] {String(r.content || '').slice(0, 60)}...
          </div>
        ))}
      </div>
    )
  } catch {
    return null
  }
}

// 进行中的流式回答状态，按会话 ID 隔离：
// 生成期间切换会话时，等待/流式气泡只出现在发起请求的那个会话里
interface StreamState {
  stage: 'searching' | 'generating'
  streamingAnswer: string
  // SSE references 事件即时到达的引用，不再等流结束才展示
  liveReferences: any[]
}

export default function ChatPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [streams, setStreams] = useState<Record<number, StreamState>>({})
  const abortMapRef = useRef<Record<number, AbortController>>({})
  const activeSessionIdRef = useRef<number | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const isAdmin = localStorage.getItem('role') === 'admin'

  const currentStream = activeSessionId != null ? streams[activeSessionId] : undefined

  useEffect(() => {
    activeSessionIdRef.current = activeSessionId
  }, [activeSessionId])

  // 加载会话列表
  useEffect(() => {
    loadSessions()
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, currentStream?.streamingAnswer, currentStream?.stage, activeSessionId])

  const loadSessions = async () => {
    try {
      const res = await chatAPI.getSessions()
      setSessions(res.data)
    } catch {
      message.error('加载会话失败')
    }
  }

  const createNewSession = async (): Promise<number | null> => {
    try {
      const res = await chatAPI.createSession('新对话')
      setSessions([res.data, ...sessions])
      setActiveSessionId(res.data.id)
      setMessages([])
      return res.data.id
    } catch {
      message.error('创建会话失败')
      return null
    }
  }

  const deleteSession = async (sessionId: number) => {
    try {
      // 该会话还有回答在生成时先中断，避免流结束后回写已删除的会话
      abortMapRef.current[sessionId]?.abort()
      await chatAPI.deleteSession(sessionId)
      setSessions(sessions.filter(s => s.id !== sessionId))
      if (activeSessionId === sessionId) {
        setActiveSessionId(null)
        setMessages([])
      }
      message.success('会话已删除')
    } catch {
      message.error('删除会话失败')
    }
  }

  const loadMessages = async (sessionId: number) => {
    try {
      const res = await chatAPI.getMessages(sessionId)
      setMessages(res.data)
    } catch {
      message.error('加载消息失败')
    }
  }

  const updateStream = (sid: number, patch: Partial<StreamState> | null) => {
    setStreams(prev => {
      if (patch === null) {
        const { [sid]: _finished, ...rest } = prev
        return rest
      }
      const base: StreamState = prev[sid] ?? { stage: 'searching', streamingAnswer: '', liveReferences: [] }
      return { ...prev, [sid]: { ...base, ...patch } }
    })
  }

  const sendMessage = async (textArg?: string, sessionIdArg?: number) => {
    const content = (textArg ?? inputValue).trim()
    const sid = sessionIdArg ?? activeSessionId
    if (!content || !sid) return
    // 该会话已有回答在生成中，忽略重复发送
    if (abortMapRef.current[sid]) return

    const userMessage: ChatMessage = {
      id: Date.now(),
      session_id: sid,
      role: 'user',
      content,
      created_at: new Date().toISOString(),
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    updateStream(sid, { stage: 'searching', streamingAnswer: '', liveReferences: [] })

    const controller = new AbortController()
    abortMapRef.current[sid] = controller

    let fullAnswer = ''
    const refs: any[] = []

    try {
      await chatAPI.sendQuestion(
        sid,
        content,
        (chunk) => {
          fullAnswer += chunk
          updateStream(sid, { streamingAnswer: fullAnswer })
        },
        (referenceRefs) => {
          refs.push(...referenceRefs)
          updateStream(sid, { stage: 'generating', liveReferences: referenceRefs })
        },
        controller.signal
      )

      // 生成完成：仅当用户仍停留在该会话时刷新消息列表，
      // 否则不打扰当前视图，切回时 loadMessages 会从服务端加载
      if (activeSessionIdRef.current === sid) {
        const res = await chatAPI.getMessages(sid)
        setMessages(res.data)
      }
      updateStream(sid, null)
    } catch (error: any) {
      if (error?.name === 'AbortError') {
        // 用户主动停止：后端会持久化已生成的部分回答；
        // 若仍停留在此会话，本地先补一条保持展示
        if (fullAnswer && activeSessionIdRef.current === sid) {
          setMessages(prev => [...prev, {
            id: Date.now() + 1,
            session_id: sid,
            role: 'assistant',
            content: `${fullAnswer}\n\n> （已停止生成）`,
            references: refs.length ? JSON.stringify(refs) : undefined,
            created_at: new Date().toISOString(),
          }])
        }
        updateStream(sid, null)
      } else {
        message.error(error.response?.data?.detail || '发送失败，请重试')
        updateStream(sid, null)
      }
    } finally {
      delete abortMapRef.current[sid]
    }
  }

  const stopGeneration = () => {
    const sid = activeSessionIdRef.current
    if (sid != null) abortMapRef.current[sid]?.abort()
  }

  // 空会话欢迎页的示例问题：没有会话时先自动建一个再发送
  const askShowcase = async (question: string) => {
    const sid = activeSessionId ?? await createNewSession()
    if (sid != null) sendMessage(question, sid)
  }

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  return (
    <Layout style={{ minHeight: '100vh' }}>
      {/* 侧边栏 */}
      <Sider
        width={260}
        style={{
          background: '#FFFFFF',
          borderRight: '1px solid #E8E0D5',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div style={{ padding: 20 }}>
          <Button
            type="primary"
            block
            icon={<PlusOutlined />}
            onClick={createNewSession}
            style={{ borderRadius: 8, marginBottom: 16 }}
          >
            新建对话
          </Button>
        </div>
        <Menu
          mode="inline"
          selectedKeys={[activeSessionId?.toString() || '']}
          items={sessions.map(s => ({
            key: s.id.toString(),
            label: s.title,
            icon: <MessageOutlined />,
            extra: (
              <DeleteOutlined
                onClick={(e) => {
                  e.stopPropagation()
                  deleteSession(s.id)
                }}
                style={{ color: '#999', cursor: 'pointer' }}
              />
            ),
          }))}
          onClick={({ key }) => {
            const sid = parseInt(key)
            setActiveSessionId(sid)
            loadMessages(sid)
          }}
        />
      </Sider>

      {/* 主内容区 */}
      <Layout>
        <Header style={{
          background: '#FAF8F5',
          borderBottom: '1px solid #E8E0D5',
          padding: '0 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <BookOutlined style={{ fontSize: 24, color: '#8B6F47' }} />
            <Text strong style={{ fontSize: 18, color: '#8B6F47' }}>RAG 知识库问答</Text>
          </div>
          <div style={{ display: 'flex', gap: 8 }}>
            {isAdmin && (
              <Button icon={<SettingOutlined />} onClick={() => navigate('/knowledge')}>
                知识库管理
              </Button>
            )}
            <Button
              icon={<LogoutOutlined />}
              onClick={() => {
                localStorage.removeItem('token')
                localStorage.removeItem('role')
                navigate('/login')
              }}
            >
              退出登录
            </Button>
          </div>
        </Header>

        <Content style={{
          background: '#FAF8F5',
          padding: 24,
          display: 'flex',
          flexDirection: 'column',
          height: 'calc(100vh - 64px)',
        }}>
          {/* 消息列表 */}
          <div style={{
            flex: 1,
            overflowY: 'auto',
            padding: 20,
            background: '#FFFFFF',
            borderRadius: 12,
            marginBottom: 16,
          }}>
            {messages.length === 0 && !currentStream && (
              <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>
                <p style={{ fontSize: 16 }}>开始提问，我会基于知识库回答～</p>
                <ProductShowcase size="large" onAsk={askShowcase} />
              </div>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                style={{
                  display: 'flex',
                  justifyContent: msg.role === 'user' ? 'flex-end' : 'flex-start',
                  marginBottom: 16,
                }}
              >
                <div style={{
                  maxWidth: '70%',
                  padding: '12px 16px',
                  borderRadius: 12,
                  background: msg.role === 'user' ? '#8B6F47' : '#F5EDE3',
                  color: msg.role === 'user' ? '#fff' : '#2D2D2D',
                }}>
                  {msg.role === 'user' ? (
                    <div style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</div>
                  ) : (
                    <>
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                      <ReferenceList references={msg.references} />
                    </>
                  )}
                </div>
              </div>
            ))}
            {currentStream && !currentStream.streamingAnswer && (
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
                <div style={{
                  maxWidth: '70%',
                  padding: '12px 16px',
                  borderRadius: 12,
                  background: '#F5EDE3',
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: '#8B6F47', fontSize: 14 }}>
                    <SyncOutlined spin />
                    <span>
                      {currentStream.stage === 'searching'
                        ? '正在检索知识库…'
                        : `已找到 ${currentStream.liveReferences.length} 条相关资料，正在生成答案…`}
                    </span>
                  </div>
                  {currentStream.stage === 'generating' && (
                    <>
                      <div style={{ marginTop: 8 }}>
                        <span className="typing-dot" />
                        <span className="typing-dot" style={{ marginLeft: 4 }} />
                        <span className="typing-dot" style={{ marginLeft: 4 }} />
                      </div>
                      {currentStream.liveReferences.length > 0 && (
                        <ReferenceList references={JSON.stringify(currentStream.liveReferences.slice(0, 4))} />
                      )}
                    </>
                  )}
                  {currentStream.stage === 'searching' && (
                    <div style={{ marginTop: 10 }}>
                      <div style={{ fontSize: 12, color: '#999', marginBottom: 6 }}>等待期间看看今日好物</div>
                      <ProductShowcase size="compact" />
                    </div>
                  )}
                </div>
              </div>
            )}
            {currentStream?.streamingAnswer && (
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
                <div style={{
                  maxWidth: '70%',
                  padding: '12px 16px',
                  borderRadius: 12,
                  background: '#F5EDE3',
                }}>
                  <ReactMarkdown>{currentStream.streamingAnswer}</ReactMarkdown>
                  {currentStream.liveReferences.length > 0 && (
                    <ReferenceList references={JSON.stringify(currentStream.liveReferences)} />
                  )}
                </div>
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>

          {/* 输入框 */}
          <div style={{ display: 'flex', gap: 12 }}>
            <TextArea
              value={inputValue}
              onChange={(e) => setInputValue(e.target.value)}
              onKeyDown={handleKeyPress}
              placeholder="输入你的问题..."
              autoSize={{ minRows: 1, maxRows: 4 }}
              disabled={!!currentStream || !activeSessionId}
              style={{ flex: 1 }}
            />
            {currentStream ? (
              <Button
                danger
                icon={<StopOutlined />}
                onClick={stopGeneration}
                style={{ borderRadius: 8, alignSelf: 'flex-end' }}
              >
                停止
              </Button>
            ) : (
              <Button
                type="primary"
                onClick={() => sendMessage()}
                disabled={!inputValue.trim() || !activeSessionId}
                style={{ borderRadius: 8, alignSelf: 'flex-end' }}
              >
                发送
              </Button>
            )}
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
