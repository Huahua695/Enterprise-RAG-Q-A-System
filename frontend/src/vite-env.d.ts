/// <reference types="vite/client" />

declare module '*.tsx' {
  import React from 'react'
  const component: React.FC
  export default component
}

declare module '*.css' {
  const content: Record<string, string>
  export default content
}
