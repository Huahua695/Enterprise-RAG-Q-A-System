import api from './api'

export interface Message {
  id: number
  session_id: number
  role: string
  content: string
  references?: string
  created_at: string
}

export interface Session {
  id: number
  title: string
  user_id: number
  created_at: string
  updated_at: string
}

export const chatAPI = {
  // 会话管理
  getSessions: () => api.get('/chat/sessions'),
  createSession: (title: string, kbIds?: number[]) =>
    api.post('/chat/sessions', { title, knowledge_base_ids: kbIds }),
  deleteSession: (sessionId: number) =>
    api.delete(`/chat/sessions/${sessionId}`),
  getMessages: (sessionId: number) =>
    api.get(`/chat/sessions/${sessionId}/messages`),

  // 发送消息（流式）
  sendQuestion: async (
    sessionId: number,
    question: string,
    onChunk: (chunk: string) => void,
    onReferences?: (refs: any[]) => void,
    signal?: AbortSignal
  ) => {
    const response = await fetch('/api/chat/send', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${localStorage.getItem('token')}`,
      },
      body: JSON.stringify({ session_id: sessionId, message: question }),
      signal,
    })

    if (!response.ok) throw new Error('请求失败')

    const reader = response.body?.getReader()
    if (!reader) throw new Error('无法读取响应')

    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() || ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          try {
            const data = JSON.parse(line.slice(6))
            if (data.type === 'answer') {
              onChunk(data.content)
            } else if (data.type === 'references') {
              onReferences?.(data.references)
            }
          } catch {}
        }
      }
    }
  },

  // 知识库管理
  getKnowledgeBases: () => api.get('/knowledge/knowledge-bases'),
  createKnowledgeBase: (name: string, description?: string) =>
    api.post('/knowledge/knowledge-bases', { name, description }),
  deleteKnowledgeBase: (kbId: number) =>
    api.delete(`/knowledge/knowledge-bases/${kbId}`),
  listDocuments: (kbId?: number) =>
    api.get('/knowledge/documents', { params: { knowledge_base_id: kbId } }),
  uploadDocument: (kbId: number, file: File) => {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('knowledge_base_id', String(kbId))
    return api.post('/knowledge/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
  },
  getDocumentContent: (docId: number) =>
    api.get(`/knowledge/documents/${docId}/content`),
}
