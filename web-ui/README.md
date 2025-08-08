# Lawnberry Web UI

A responsive React-based web interface for controlling and monitoring the autonomous lawn mower system.

## Features

### 🎛️ **Real-time Dashboard**
- Live system status monitoring with <500ms latency
- Real-time sensor data visualization with historical charts
- Live camera feed with object detection overlays
- Battery status with detailed power metrics
- Weather integration display

### 🗺️ **Interactive Navigation**
- Google Maps integration with satellite view
- Real-time mower position tracking with breadcrumb trail
- Boundary setting via click-to-define GPS coordinates
- No-go zone management with visual drawing tools
- Home position setting for charging/storage location
- Multiple mowing pattern selection (parallel, checkerboard, spiral, waves, crosshatch)
- Coverage visualization with completed area tracking
- Obstacle detection display with confidence levels

### ⚙️ **Control Interface**
- Start/stop mowing operations
- Emergency stop with 100ms response time
- Pattern selection and preview
- Speed control (default 1.0 m/s, adjustable)
- Schedule management (daily/weekly with time selection)
- Manual navigation controls

### 🎨 **AI Training Tools**
- Image collection interface for custom model training
- Drag-and-drop image upload
- Simple labeling tool for object annotation
- Training progress monitoring
- Model management and deployment
- Data export for analysis

### ⚙️ **Settings & Configuration**
- Unit switching (metric/imperial, Celsius/Fahrenheit)
- Safety parameter configuration
- Obstacle detection sensitivity adjustment
- Battery threshold management
- Theme selection (light/dark/auto)
- Advanced options for power users

## Technology Stack

- **Frontend Framework**: React 18 with TypeScript
- **UI Library**: Material-UI (MUI) v5
- **State Management**: Redux Toolkit
- **Real-time Communication**: Socket.IO client
- **Maps**: Google Maps JavaScript API
- **Charts**: Recharts for data visualization
- **Build Tool**: Vite for fast development and optimized builds
- **PWA**: Progressive Web App with offline capability

## Performance Optimizations

### 🚀 **Resource Efficiency**
- Optimized for Raspberry Pi constraints
- Code splitting with vendor/UI/maps chunks
- Lazy loading of non-critical components
- Efficient rendering with React.memo and useMemo
- Memory usage monitoring and optimization

### 📱 **Mobile Optimization**
- Fully responsive design for all screen sizes
- Touch-friendly interface elements
- Progressive Web App (PWA) capabilities
- Offline functionality for critical features
- Native app-like experience on mobile devices

### 🌐 **Real-time Performance**
- WebSocket connection with automatic reconnection
- <500ms latency for live data updates
- Efficient data streaming and caching
- Connection status monitoring
- Performance metrics tracking

## Getting Started

### Prerequisites
- Node.js 16+ and npm/yarn
- Google Maps API key
- Backend API server running on port 8000
- WebSocket server running on port 9002

### Installation

```bash
cd web-ui
npm install
```

### Environment Setup

Create a `.env` file in the web-ui directory:

```env
REACT_APP_GOOGLE_MAPS_API_KEY=your_google_maps_api_key_here
VITE_API_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:9002
```

### Development

```bash
# Start development server
npm run dev

# Access at http://localhost:3000
```

### Production Build

```bash
# Build for production
npm run build

# Serve production build
npm run serve
```

## Project Structure

```
web-ui/
├── src/
│   ├── components/          # Reusable UI components
│   │   ├── Layout/         # Main layout with navigation
│   │   ├── ConnectionStatus/ # Connection monitoring
│   │   └── EmergencyButton/ # Safety controls
│   ├── pages/              # Main application pages
│   │   ├── Dashboard.tsx   # Real-time monitoring
│   │   ├── Navigation.tsx  # Maps and mowing control
│   │   ├── Settings.tsx    # Configuration
│   │   └── Training.tsx    # AI model training
│   ├── store/              # Redux state management
│   │   └── slices/         # Redux slices for different domains
│   ├── services/           # External service integrations
│   │   └── websocket.ts    # WebSocket communication
│   ├── hooks/              # Custom React hooks
│   ├── types/              # TypeScript type definitions
│   └── utils/              # Utility functions
├── public/                 # Static assets
└── dist/                   # Production build output
```

## API Integration

### WebSocket Events
- `mower_status` - Real-time mower state updates
- `sensor_data` - Live sensor readings
- `weather_data` - Weather information updates
- `navigation_update` - Position and path updates
- `notification` - System alerts and messages

### REST API Endpoints (Selected)
- `GET /health` – Basic liveness (no auth)
- `GET /api/v1/meta` – API service meta (version, uptime, MQTT) (no auth)
- `GET /api/v1/maps` (and related read-only map endpoints) – Public read access
- `GET /api/v1/status` – Mower runtime status (auth required)
- `POST /api/v1/navigation/start` – Start mowing
- `POST /api/v1/navigation/stop` – Stop mowing
- `GET /api/v1/camera/stream` – Live camera feed
- `POST /api/v1/boundaries` – Boundary management
- `GET /api/v1/weather` – Weather data

Public endpoints are intentionally limited to map visualization and service health/metadata. All mutation and control endpoints require valid authentication.

### SPA Mount Path
The production build is served under `/ui/` by FastAPI with an internal fallback so deep links like `/ui/maps` resolve directly. Top-level convenience redirects (e.g. `/maps` → `/ui/maps`) are provided.

## Browser Compatibility

### Supported Browsers
- Chrome 88+ (recommended)
- Firefox 85+
- Safari 14+
- Edge 88+
- Mobile Safari (iOS 14+)
- Chrome Mobile (Android 8+)

### PWA Features
- Install as native app on mobile/desktop
- Offline functionality for critical features
- Push notifications for alerts
- Background sync when connection restored

## Performance Targets

- **Initial Load**: <3 seconds
- **Real-time Updates**: <500ms latency
- **Map Interactions**: 60fps smooth scrolling
- **Memory Usage**: <100MB on mobile devices
- **Battery Impact**: Minimal on mobile devices

## Security Features

- WebSocket connection encryption (WSS in production)
- API request authentication via JWT tokens
- Input validation and sanitization
- XSS protection via React's built-in defenses
- CSRF protection for state-changing operations

## Accessibility

- WCAG 2.1 AA compliance
- Keyboard navigation support
- Screen reader compatibility
- High contrast mode support
- Touch accessibility for mobile users

## Development Guidelines

### Code Style
- TypeScript strict mode enabled
- ESLint configuration for code quality
- Prettier for consistent formatting
- Functional components with hooks
- Custom hooks for reusable logic

### Testing
- Unit tests with Jest and React Testing Library
- Integration tests for critical user flows
- E2E tests with Cypress
- Performance testing with Lighthouse
- Cross-browser compatibility testing

## Deployment

### Production Checklist
- [ ] Google Maps API key configured
- [ ] Backend API endpoints accessible
- [ ] WebSocket server running
- [ ] HTTPS enabled for PWA features
- [ ] Service worker registered
- [ ] Performance optimizations applied

### Docker Deployment

```dockerfile
FROM node:18-alpine as builder
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## Troubleshooting

### Common Issues
- **Map not loading**: Check Google Maps API key and billing
- **WebSocket connection failed**: Verify backend server running
- **Slow performance**: Check network latency and memory usage
- **Mobile layout issues**: Test responsive breakpoints

### Debug Mode
Enable debug logging by setting `localStorage.debug = 'lawnberry:*'` in browser console.

## Contributing

1. Follow existing code patterns and TypeScript types
2. Ensure responsive design on all screen sizes
3. Test real-time features with actual WebSocket data
4. Optimize for Raspberry Pi performance constraints
5. Maintain <500ms latency targets for live updates

## License

Part of the Lawnberry autonomous mower project.
