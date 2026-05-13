import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App'
import './index.css'

const rootElement = document.getElementById('root')!

document.documentElement.style.width = '100%'
document.documentElement.style.minHeight = '100%'
document.body.style.margin = '0'
document.body.style.padding = '0'
document.body.style.width = '100vw'
document.body.style.minHeight = '100dvh'
document.body.style.overflow = 'hidden'
rootElement.style.display = 'block'
rootElement.style.width = '100vw'
rootElement.style.minHeight = '100dvh'

createRoot(rootElement).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
