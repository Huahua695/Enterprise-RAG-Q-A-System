import { useState, useEffect } from 'react'
import { Layout, Table, Button, Modal, Form, Input, Upload, message, Typography, Spin, Tag, Tooltip } from 'antd'
import { PlusOutlined, DeleteOutlined, InboxOutlined, BookOutlined, FileTextOutlined } from '@ant-design/icons'
import { chatAPI } from '../services/chatService'

const { Title } = Typography
const { Dragger } = Upload
const { Content } = Layout

const STATUS_META: Record<string, { label: string; color: string }> = {
  pending: { label: '待处理', color: 'default' },
  processing: { label: '处理中', color: 'processing' },
  completed: { label: '已完成', color: 'success' },
  failed: { label: '失败', color: 'error' },
}

export default function KnowledgeBase() {
  const [kbs, setKbs] = useState<any[]>([])
  const [docs, setDocs] = useState<any[]>([])
  const [modalOpen, setModalOpen] = useState(false)
  const [form] = Form.useForm()
  const [selectedKB, setSelectedKB] = useState<number | null>(null)
  const [uploading, setUploading] = useState(false)
  const [contentModal, setContentModal] = useState({ open: false, filename: '', content: '', loading: false })

  useEffect(() => {
    loadKnowledgeBases()
  }, [])

  useEffect(() => {
    if (selectedKB !== null) {
      loadDocuments()
    }
  }, [selectedKB])

  // 存在处理中/待处理的文档时每 2s 轮询刷新，全部完成或失败后自动停止
  useEffect(() => {
    if (selectedKB === null) return
    const hasProcessing = docs.some(d => d.status === 'processing' || d.status === 'pending')
    if (!hasProcessing) return
    const timer = setInterval(loadDocuments, 2000)
    return () => clearInterval(timer)
  }, [docs, selectedKB])

  const loadKnowledgeBases = async () => {
    try {
      const res = await chatAPI.getKnowledgeBases()
      setKbs(res.data)
    } catch {
      message.error('加载知识库失败')
    }
  }

  const loadDocuments = async () => {
    try {
      const res = await chatAPI.listDocuments(selectedKB || undefined)
      setDocs(res.data)
    } catch {
      message.error('加载文档失败')
    }
  }

  const handleCreateKB = async (values: any) => {
    try {
      await chatAPI.createKnowledgeBase(values.name, values.description)
      message.success('知识库创建成功')
      setModalOpen(false)
      form.resetFields()
      loadKnowledgeBases()
    } catch {
      message.error('创建失败')
    }
  }

  const handleDeleteKB = async (kbId: number) => {
    try {
      await chatAPI.deleteKnowledgeBase(kbId)
      message.success('知识库已删除')
      loadKnowledgeBases()
      if (selectedKB === kbId) {
        setSelectedKB(null)
        setDocs([])
      }
    } catch {
      message.error('删除失败')
    }
  }

  const handleUpload = async (file: File) => {
    if (!selectedKB) return false
    setUploading(true)
    try {
      await chatAPI.uploadDocument(selectedKB, file)
      message.success('文档已上传，后台向量化中...')
      loadDocuments()
      return false
    } catch {
      message.error('上传失败')
      return true
    } finally {
      setUploading(false)
    }
  }

  const handleViewContent = async (docId: number) => {
    setContentModal({ open: true, filename: '加载中...', content: '', loading: true })
    try {
      const res = await chatAPI.getDocumentContent(docId)
      setContentModal({ open: true, filename: res.data.filename, content: res.data.content, loading: false })
    } catch {
      message.error('获取文档内容失败')
      setContentModal(prev => ({ ...prev, open: false }))
    }
  }

  const kbColumns = [
    { title: 'ID', dataIndex: 'id', key: 'id', width: 60 },
    { title: '名称', dataIndex: 'name', key: 'name' },
    { title: '描述', dataIndex: 'description', key: 'description' },
    { title: '文档数', dataIndex: 'document_count', key: 'document_count' },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => (
        <div style={{ display: 'flex', gap: 8 }}>
          <Button
            type="link"
            onClick={() => { setSelectedKB(record.id); loadDocuments() }}
          >
            查看文档
          </Button>
          <Button
            type="link"
            danger
            icon={<DeleteOutlined />}
            onClick={() => handleDeleteKB(record.id)}
          />
        </div>
      ),
    },
  ]

  const docColumns = [
    { title: '文件名', dataIndex: 'filename', key: 'filename' },
    { title: '类型', dataIndex: 'file_type', key: 'file_type' },
    { title: '分块数', dataIndex: 'chunk_count', key: 'chunk_count' },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string, record: any) => {
        const meta = STATUS_META[status] || { label: status, color: 'default' }
        const tag = <Tag color={meta.color}>{meta.label}</Tag>
        return status === 'failed' && record.error_message ? (
          <Tooltip title={record.error_message}>{tag}</Tooltip>
        ) : tag
      },
    },
    {
      title: '操作',
      key: 'action',
      render: (_: any, record: any) => (
        <Button
          type="link"
          icon={<FileTextOutlined />}
          onClick={() => handleViewContent(record.id)}
        >
          查看内容
        </Button>
      ),
    },
  ]

  return (
    <Layout style={{ minHeight: '100vh', background: '#FAF8F5' }}>
      <Content style={{ padding: 24 }}>
        <Title level={3} style={{ color: '#8B6F47', marginBottom: 24 }}>
          <BookOutlined /> 知识库管理后台
        </Title>

        <div style={{ display: 'flex', gap: 24 }}>
          {/* 左侧：知识库列表 */}
          <div style={{ flex: 1, background: '#fff', padding: 24, borderRadius: 12 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 16 }}>
              <Title level={5}>知识库列表</Title>
              <Button type="primary" icon={<PlusOutlined />} onClick={() => setModalOpen(true)}>
                新建知识库
              </Button>
            </div>
            <Table
              columns={kbColumns}
              dataSource={kbs}
              rowKey="id"
              pagination={false}
            />
          </div>

          {/* 右侧：文档管理 */}
          {selectedKB && (
            <div style={{ flex: 1, background: '#fff', padding: 24, borderRadius: 12 }}>
              <Title level={5}>文档管理</Title>
              <Dragger
                accept=".pdf,.docx,.txt,.md,.markdown,.xlsx,.xls"
                multiple
                customRequest={({ file }: any) => handleUpload(file as File)}
                disabled={uploading}
                style={{ marginBottom: 16 }}
              >
                <p className="ant-upload-drag-icon">
                  <InboxOutlined />
                </p>
                <p>点击或拖拽文件到此区域上传</p>
                <p style={{ fontSize: 12, color: '#999' }}>支持 PDF、Word、TXT、Markdown、Excel 格式</p>
              </Dragger>
              <Table
                columns={docColumns}
                dataSource={docs}
                rowKey="id"
                pagination={false}
              />
            </div>
          )}
        </div>

        {/* 新建知识库弹窗 */}
        <Modal
          open={modalOpen}
          onCancel={() => setModalOpen(false)}
          onOk={() => form.submit()}
          title="新建知识库"
        >
          <Form form={form} onFinish={handleCreateKB} layout="vertical">
            <Form.Item name="name" label="名称" rules={[{ required: true }]}>
              <Input placeholder="输入知识库名称" />
            </Form.Item>
            <Form.Item name="description" label="描述">
              <Input.TextArea placeholder="输入知识库描述" rows={3} />
            </Form.Item>
          </Form>
        </Modal>

        {/* 文档内容预览弹窗 */}
        <Modal
          open={contentModal.open}
          onCancel={() => setContentModal(prev => ({ ...prev, open: false }))}
          title={`文档内容: ${contentModal.filename}`}
          width={800}
          footer={null}
        >
          {contentModal.loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}>
              <Spin tip="加载中..." />
            </div>
          ) : (
            <pre style={{
              maxHeight: 500, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              background: '#FAF8F5', padding: 16, borderRadius: 8, fontSize: 13, lineHeight: 1.8,
              color: '#2D2D2D', border: '1px solid #E8E0D5',
            }}>
              {contentModal.content || '(该文档暂无内容记录，可能是旧版本上传的。请重新上传以获取内容预览。)'}
            </pre>
          )}
        </Modal>
      </Content>
    </Layout>
  )
}
