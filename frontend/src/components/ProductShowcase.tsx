import { useEffect, useRef, useState } from 'react'
import { Button } from 'antd'
import { RightOutlined } from '@ant-design/icons'
import { showcaseProducts } from '../data/products'

interface Props {
  /** large：空会话欢迎页（带"问问看"示例问题）；compact：等待答案期间的小卡片 */
  size?: 'large' | 'compact'
  /** 自动轮换间隔（毫秒） */
  intervalMs?: number
  onAsk?: (question: string) => void
}

/** 商品介绍轮换卡片：自动换片、悬停暂停、圆点可手动切换 */
export default function ProductShowcase({ size = 'large', intervalMs = 5000, onAsk }: Props) {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const timerRef = useRef<number | null>(null)
  const product = showcaseProducts[index % showcaseProducts.length]
  const compact = size === 'compact'

  useEffect(() => {
    if (paused || showcaseProducts.length <= 1) return
    timerRef.current = window.setInterval(
      () => setIndex((i) => (i + 1) % showcaseProducts.length),
      intervalMs
    )
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current)
    }
  }, [paused, intervalMs])

  const imagePx = compact ? 88 : 168

  return (
    <div
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      style={{
        display: 'inline-block',
        textAlign: 'left',
        background: '#FFFFFF',
        border: '1px solid #E8E0D5',
        borderRadius: 12,
        padding: compact ? 10 : 14,
        width: compact ? 360 : 440,
        maxWidth: '100%',
      }}
    >
      <div key={index} className="showcase-fade" style={{ display: 'flex', gap: compact ? 10 : 14 }}>
        <img
          src={product.image}
          alt={product.name}
          width={imagePx}
          height={imagePx}
          style={{ borderRadius: 8, objectFit: 'cover', flexShrink: 0 }}
        />
        <div style={{ display: 'flex', flexDirection: 'column', minWidth: 0 }}>
          <div style={{ fontSize: compact ? 12 : 12, color: '#A68B5A', fontWeight: 600 }}>
            {product.tagline}
          </div>
          <div style={{ fontSize: compact ? 14 : 16, fontWeight: 700, color: '#2D2D2D', margin: '2px 0' }}>
            {product.name}
          </div>
          {!compact && (
            <div style={{ fontSize: 13, color: '#666', lineHeight: 1.6 }}>{product.description}</div>
          )}
          <div style={{ flex: 1 }} />
          {onAsk && (
            <Button
              type="link"
              size="small"
              style={{
                padding: 0,
                color: '#8B6F47',
                alignSelf: 'flex-start',
                whiteSpace: 'normal',
                textAlign: 'left',
                height: 'auto',
                lineHeight: 1.5,
              }}
              onClick={() => onAsk(product.question)}
            >
              问问看：{product.question} <RightOutlined />
            </Button>
          )}
        </div>
      </div>
      {/* 圆点指示器 */}
      <div style={{ display: 'flex', gap: 6, justifyContent: 'center', marginTop: compact ? 8 : 10 }}>
        {showcaseProducts.map((p, i) => (
          <span
            key={p.name}
            onClick={() => setIndex(i)}
            style={{
              width: 8,
              height: 8,
              borderRadius: '50%',
              cursor: 'pointer',
              background: i === index ? '#8B6F47' : '#E8E0D5',
            }}
          />
        ))}
      </div>
    </div>
  )
}
