import { useState, useEffect, useRef } from 'react'
import { Layout, Menu, Input, Button, message, Typography } from 'antd'
import { MessageOutlined, PlusOutlined, DeleteOutlined, BookOutlined, SettingOutlined, LogoutOutlined } from '@ant-design/icons'
import { chatAPI, type Session, type Message as ChatMessage } from '../services/chatService'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'

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

export default function ChatPage() {
  const navigate = useNavigate()
  const [sessions, setSessions] = useState<Session[]>([])
  const [activeSessionId, setActiveSessionId] = useState<number | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [inputValue, setInputValue] = useState('')
  const [loading, setLoading] = useState(false)
  const [streamingAnswer, setStreamingAnswer] = useState('')
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const isAdmin = localStorage.getItem('role') === 'admin'

  // 加载会话列表
  useEffect(() => {
    loadSessions()
  }, [])

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingAnswer])

  const loadSessions = async () => {
    try {
      const res = await chatAPI.getSessions()
      setSessions(res.data)
    } catch {
      message.error('加载会话失败')
    }
  }

  const createNewSession = async () => {
    try {
      const res = await chatAPI.createSession('新对话')
      setSessions([res.data, ...sessions])
      setActiveSessionId(res.data.id)
      setMessages([])
      setStreamingAnswer('')
    } catch {
      message.error('创建会话失败')
    }
  }

  const deleteSession = async (sessionId: number) => {
    try {
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
      setStreamingAnswer('')
    } catch {
      message.error('加载消息失败')
    }
  }

  const sendMessage = async () => {
    if (!inputValue.trim() || !activeSessionId) return

    const userMessage: ChatMessage = {
      id: Date.now(),
      session_id: activeSessionId,
      role: 'user',
      content: inputValue,
      created_at: new Date().toISOString(),
    }

    setMessages(prev => [...prev, userMessage])
    setInputValue('')
    setLoading(true)
    setStreamingAnswer('')

    try {
      let fullAnswer = ''
      const refs: any[] = []

      await chatAPI.sendQuestion(
        activeSessionId,
        inputValue,
        (chunk) => {
          fullAnswer += chunk
          setStreamingAnswer(fullAnswer)
        },
        (referenceRefs) => {
          refs.push(...referenceRefs)
        }
      )

      // 刷新消息列表
      const res = await chatAPI.getMessages(activeSessionId)
      setMessages(res.data)
      setStreamingAnswer('')
    } catch (error: any) {
      message.error(error.response?.data?.detail || '发送失败，请重试')
    } finally {
      setLoading(false)
    }
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
            {messages.length === 0 && !streamingAnswer && (
              <div style={{ textAlign: 'center', padding: 40, color: '#999' }}>
                <p style={{ fontSize: 16 }}>开始提问关于电商商品的问题吧！</p>
                <p style={{ fontSize: 14 }}>例如："这款手机的电池容量是多少？"</p>
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
            {streamingAnswer && (
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 16 }}>
                <div style={{
                  maxWidth: '70%',
                  padding: '12px 16px',
                  borderRadius: 12,
                  background: '#F5EDE3',
                }}>
                  <ReactMarkdown>{streamingAnswer}</ReactMarkdown>
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
              disabled={loading || !activeSessionId}
              style={{ flex: 1 }}
            />
            <Button
              type="primary"
              onClick={sendMessage}
              loading={loading}
              disabled={!inputValue.trim() || !activeSessionId}
              style={{ borderRadius: 8, alignSelf: 'flex-end' }}
            >
              发送
            </Button>
          </div>
        </Content>
      </Layout>
    </Layout>
  )
}
