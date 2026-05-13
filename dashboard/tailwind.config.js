/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./frontend/index.html",
    "./frontend/src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Inter', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'monospace'],
      },
      colors: {
        // Tesla / Apple minimal palette
        ts: {
          bg: '#000000',
          base: '#0c0c0c',
          panel: '#161616',
          text: '#ffffff',
          muted: '#8e8e93',
          border: 'rgba(255,255,255,0.1)',
          accent: '#3478f6', // Clean vibrant blue
        }
      },
      animation: {
        'ts-fade-in': 'ts-fade-in 0.4s ease-out forwards',
        'ts-slide-up': 'ts-slide-up 0.5s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        'ts-float': 'ts-float 10s infinite ease-in-out',
      },
      keyframes: {
        'ts-fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' },
        },
        'ts-slide-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'ts-float': {
          '0%, 100%': { transform: 'translateY(0) translateX(0)' },
          '33%': { transform: 'translateY(-20px) translateX(10px)' },
          '66%': { transform: 'translateY(15px) translateX(-15px)' },
        }
      }
    },
  },
  plugins: [],
}
