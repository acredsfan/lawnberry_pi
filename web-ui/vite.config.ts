import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// NOTE (LawnBerryPi Bookworm ARM64):
// We explicitly set a production base path (/ui/) so that the FastAPI backend
// mounting the static dist at /ui serves all chunk + asset URLs correctly.
// Without this, index.html would reference /assets/* which won't resolve
// because the StaticFiles mount is namespaced. This avoids brittle backend
// remount hacks and keeps a single source of truth here.
// Also corrected the WebSocket proxy target to backend (8000) instead of 9002.
// Keep bundle size under control on Pi by tweaking build options (chunking, no large sourcemaps).

// Export function form so we can differentiate dev vs build for base path.
// Dev should use '/' to avoid 404s when visiting :3000 directly; production build uses '/ui/'.
export default defineConfig(({ command }) => ({
  base: command === 'build' ? '/ui/' : '/',
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
        // Development WebSocket proxy to FastAPI backend (mounted at /ws)
        target: 'ws://localhost:8000',
        ws: true
      }
    }
  },
  build: {
    outDir: 'dist',
    // On Raspberry Pi we keep build lean: disable large sourcemaps, leverage chunk splitting
    sourcemap: false,
  // Reduce memory/time on constrained Pi by disabling minification (avoids OOM / SIGTERM during build)
  minify: false,
    rollupOptions: {
      output: {
        manualChunks: {
          vendor: ['react', 'react-dom'],
          router: ['react-router-dom'],
          ui: ['@mui/material', '@mui/icons-material'],
          maps: ['@googlemaps/js-api-loader', 'leaflet', 'leaflet-draw', 'react-leaflet'],
          charts: ['recharts']
        }
      }
    },
    chunkSizeWarningLimit: 900,
    target: 'es2018'
  },
  optimizeDeps: {
    include: ['react', 'react-dom', '@mui/material', 'socket.io-client']
  }
}))
