import React from 'react'
import ReactDOM from 'react-dom/client'
import { Provider } from 'react-redux'
import { BrowserRouter } from 'react-router-dom'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import CssBaseline from '@mui/material/CssBaseline'
import { QueryClient, QueryClientProvider } from 'react-query'
import { store } from './store/store'
import App from './App'
import './index.css'

declare module '@mui/material/styles' {
  interface Palette {
    surface: {
      main: string;
    };
    accent: {
      main: string;
      purple: string;
      orange: string;
    };
  }

  interface PaletteOptions {
    surface?: {
      main?: string;
    };
    accent?: {
      main?: string;
      purple?: string;
      orange?: string;
    };
  }
}

// LawnBerryPi 80's Retro Theme inspired by the logo
const theme = createTheme({
  palette: {
    mode: 'dark',
    primary: {
      main: '#00FFD1', // Bright cyan (80's neon)
      light: '#4DFFA6', // Electric mint
      dark: '#00B8A3', // Deep teal
    },
    secondary: {
      main: '#FF1493', // Hot pink (80's neon)
      light: '#FF69B4', // Light pink
      dark: '#C71585', // Medium violet red
    },
    background: {
      default: '#0a0a0a', // Deep black for retro feel
      paper: '#1a1a2e', // Dark blue-grey
    },
    surface: {
      main: '#16213e', // Navy blue surface
    },
    accent: {
      main: '#FFFF00', // Electric yellow
      purple: '#9D4EDD', // Retro purple
      orange: '#FF6B35', // Sunset orange
    },
    success: {
      main: '#39FF14', // Electric lime green
    },
    warning: {
      main: '#FFD700', // Gold
    },
    error: {
      main: '#FF073A', // Electric red
    },
    text: {
      primary: '#FFFFFF',
      secondary: '#B0BEC5',
    },
  },
  typography: {
    fontFamily: [
      '"Orbitron"', // Futuristic 80's font
      '"Share Tech Mono"', // Monospace retro
      'Monaco',
      'Menlo',
      '"Courier New"',
      'monospace',
    ].join(','),
    h1: {
      fontWeight: 700,
      textShadow: '0 0 10px currentColor',
    },
    h2: {
      fontWeight: 600,
      textShadow: '0 0 8px currentColor',
    },
    h3: {
      fontWeight: 600,
      textShadow: '0 0 6px currentColor',
    },
    h4: {
      fontWeight: 600,
      textShadow: '0 0 4px currentColor',
    },
    h5: {
      fontWeight: 600,
      textShadow: '0 0 4px currentColor',
    },
    h6: {
      fontWeight: 600,
      textShadow: '0 0 2px currentColor',
    },
    button: {
      textTransform: 'uppercase',
      fontWeight: 700,
      letterSpacing: '0.1em',
    },
  },
  shape: {
    borderRadius: 0, // Sharp 80's edges
  },
  components: {
    MuiButton: {
      styleOverrides: {
        root: {
          textTransform: 'uppercase',
          borderRadius: 0,
          fontWeight: 700,
          letterSpacing: '0.1em',
          border: '2px solid transparent',
          background: 'linear-gradient(45deg, #00FFD1, #FF1493)',
          color: '#000',
          boxShadow: '0 0 20px rgba(0, 255, 209, 0.5)',
          transition: 'all 0.3s ease',
          '&:hover': {
            boxShadow: '0 0 30px rgba(255, 20, 147, 0.8)',
            transform: 'translateY(-2px)',
            background: 'linear-gradient(45deg, #FF1493, #FFFF00)',
          },
          '&:active': {
            transform: 'translateY(0)',
          },
        },
        contained: {
          background: 'linear-gradient(45deg, #00FFD1, #FF1493)',
          '&:hover': {
            background: 'linear-gradient(45deg, #FF1493, #FFFF00)',
          },
        },
        outlined: {
          background: 'transparent',
          border: '2px solid #00FFD1',
          color: '#00FFD1',
          '&:hover': {
            border: '2px solid #FF1493',
            color: '#FF1493',
            background: 'rgba(255, 20, 147, 0.1)',
          },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 0,
          background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
          border: '1px solid #00FFD1',
          boxShadow: '0 0 20px rgba(0, 255, 209, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.1)',
          backdropFilter: 'blur(10px)',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: '2px',
            background: 'linear-gradient(90deg, #00FFD1, #FF1493, #FFFF00, #00FFD1)',
            backgroundSize: '200% 100%',
            animation: 'neon-border 3s linear infinite',
          },
        },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          background: 'linear-gradient(90deg, #0a0a0a 0%, #1a1a2e 50%, #0a0a0a 100%)',
          borderBottom: '2px solid #00FFD1',
          boxShadow: '0 0 30px rgba(0, 255, 209, 0.5)',
          backdropFilter: 'blur(20px)',
        },
      },
    },
    MuiDrawer: {
      styleOverrides: {
        paper: {
          background: 'linear-gradient(180deg, #0a0a0a 0%, #1a1a2e 100%)',
          borderRight: '2px solid #FF1493',
          '&::before': {
            content: '""',
            position: 'absolute',
            top: 0,
            right: 0,
            bottom: 0,
            width: '2px',
            background: 'linear-gradient(180deg, #FF1493, #00FFD1, #FFFF00, #FF1493)',
            backgroundSize: '100% 200%',
            animation: 'neon-border 4s linear infinite',
          },
        },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: {
          backgroundColor: 'rgba(0, 255, 209, 0.2)',
          '& .MuiLinearProgress-bar': {
            background: 'linear-gradient(90deg, #00FFD1, #FF1493)',
            boxShadow: '0 0 10px currentColor',
          },
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: 0,
          border: '1px solid #00FFD1',
          backgroundColor: 'rgba(0, 255, 209, 0.1)',
          color: '#00FFD1',
          fontWeight: 700,
          textTransform: 'uppercase',
          letterSpacing: '0.05em',
          boxShadow: '0 0 10px rgba(0, 255, 209, 0.5)',
        },
        colorSuccess: {
          border: '1px solid #39FF14',
          backgroundColor: 'rgba(57, 255, 20, 0.1)',
          color: '#39FF14',
        },
        colorWarning: {
          border: '1px solid #FFD700',
          backgroundColor: 'rgba(255, 215, 0, 0.1)',
          color: '#FFD700',
        },
        colorError: {
          border: '1px solid #FF073A',
          backgroundColor: 'rgba(255, 7, 58, 0.1)',
          color: '#FF073A',
        },
      },
    },
  },
})

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
      staleTime: 30000,
    },
  },
})

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Provider store={store}>
      <QueryClientProvider client={queryClient}>
        <ThemeProvider theme={theme}>
          <CssBaseline />
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </ThemeProvider>
      </QueryClientProvider>
    </Provider>
  </React.StrictMode>,
)
