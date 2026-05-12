import { ReactNode } from 'react'
import { TopNav } from './TopNav'

interface AppShellProps {
  children: ReactNode
}

export function AppShell({ children }: AppShellProps) {
  return (
    <div
      style={{
        minHeight: '100vh',
        background: '#fff',
        overflowX: 'hidden',
      }}
    >
      <TopNav />
      <main
        style={{
          maxWidth: '1440px',
          margin: '0 auto',
          padding: 'clamp(84px, 10vw, 112px) clamp(10px, 2.2vw, 16px) clamp(24px, 4vw, 48px)',
        }}
      >
        {children}
      </main>
    </div>
  )
}
