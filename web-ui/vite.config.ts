import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg}']
      },
      manifest: {
        name: 'LawnBerryPi Control',
        short_name: 'LawnBerryPi',
        description: 'LawnBerryPi - Autonomous Lawn Mower Control Interface',
        theme_color: '#2E7D32',
        background_color: '#FAFAFA',
        display: 'standalone',
        icons: [
          {
            src: 'assets/LawnBerryPi_logo.png',
            sizes: '192x192',
            type: 'image/png'
          },
          {
            src: 'assets/LawnBerryPi_logo.png',
            sizes: '512x512',
            type: 'image/png'
          }
        ]
      }
    })
  ],
  envPrefix: ['VITE_', 'REACT_APP_'],
  server: {
    host: '0.0.0.0',
    port: 3000,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true
      },
      '/ws': {
        target: 'ws://localhost:9002',
        ws: true
      }
    }
  },
  build: {
    outDir: 'dist',
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          ui: ['@mui/material', '@mui/icons-material'],
          maps: ['@googlemaps/js-api-loader']
        }
      }
    }
  },
  optimizeDeps: {
    include: ['react', 'react-dom', '@mui/material', 'socket.io-client']
  }
})
