<template>
  <div class="docs-view">
    <div class="page-header">
      <h1>Documentation Hub</h1>
      <p class="text-muted">Complete setup guides, documentation, and troubleshooting resources</p>
    </div>

    <!-- Search and Quick Actions -->
    <div class="search-section">
      <div class="search-bar">
        <input 
          v-model="searchQuery"
          type="text" 
          placeholder="Search documentation..."
          class="search-input"
          @input="performSearch"
        >
        <button class="search-button">🔍</button>
      </div>
      <div class="quick-actions">
        <button class="btn btn-primary" @click="showQuickStart">⚡ Quick Start</button>
        <button class="btn btn-secondary" @click="showTroubleshooting">🔧 Troubleshooting</button>
        <button class="btn btn-info" @click="showAPIRef">📖 API Reference</button>
      </div>
    </div>

    <div class="docs-layout">
      <!-- Sidebar Navigation -->
      <div class="sidebar">
        <div class="nav-section">
          <h3>📚 Documentation</h3>
          <div class="nav-tree">
            <div 
              v-for="section in docSections" 
              :key="section.id"
              class="nav-category"
            >
              <button 
                class="category-toggle"
                :class="{ expanded: expandedSections.includes(section.id) }"
                @click="toggleSection(section.id)"
              >
                {{ section.icon }} {{ section.title }}
              </button>
              <div 
                v-if="expandedSections.includes(section.id)"
                class="nav-items"
              >
                <button 
                  v-for="doc in section.docs" 
                  :key="doc.id"
                  class="nav-item"
                  :class="{ active: selectedDoc?.id === doc.id }"
                  @click="selectDoc(doc)"
                >
                  {{ doc.title }}
                </button>
              </div>
            </div>
          </div>
        </div>

        <!-- Search Results -->
        <div v-if="searchResults.length > 0" class="search-results">
          <h3>🔍 Search Results</h3>
          <div class="result-list">
            <button 
              v-for="result in searchResults" 
              :key="result.id"
              class="search-result"
              @click="selectDoc(result)"
            >
              <div class="result-title">{{ result.title }}</div>
              <div class="result-excerpt">{{ result.excerpt }}</div>
            </button>
          </div>
        </div>
      </div>

      <!-- Main Content -->
      <div class="main-content">
        <div v-if="!selectedDoc" class="welcome-content">
          <div class="welcome-header">
            <h2>Welcome to LawnBerry Pi Documentation</h2>
            <p>Your comprehensive guide to setup, configuration, and operation</p>
          </div>

          <!-- Featured Guides -->
          <div class="featured-guides">
            <div 
              v-for="guide in featuredGuides" 
              :key="guide.id"
              class="guide-card"
              @click="selectDoc(guide)"
            >
              <div class="guide-icon">{{ guide.icon }}</div>
              <div class="guide-content">
                <h3>{{ guide.title }}</h3>
                <p>{{ guide.description }}</p>
                <span class="guide-time">{{ guide.estimatedTime }}</span>
              </div>
            </div>
          </div>

          <!-- Status Overview -->
          <div class="status-overview">
            <h3>📊 System Status</h3>
            <div class="status-grid">
              <div class="status-item">
                <div class="status-icon">🟢</div>
                <div class="status-info">
                  <span class="status-label">Documentation</span>
                  <span class="status-value">{{ totalDocs }} docs available</span>
                </div>
              </div>
              <div class="status-item">
                <div class="status-icon">📱</div>
                <div class="status-info">
                  <span class="status-label">Offline Access</span>
                  <span class="status-value">Enabled</span>
                </div>
              </div>
              <div class="status-item">
                <div class="status-icon">🔄</div>
                <div class="status-info">
                  <span class="status-label">Last Updated</span>
                  <span class="status-value">{{ lastUpdated }}</span>
                </div>
              </div>
            </div>
          </div>
        </div>

        <!-- Document Content -->
        <div v-else class="document-content">
          <div class="document-header">
            <div class="breadcrumb">
              <button class="breadcrumb-item" @click="selectedDoc = null">
                📚 Documentation
              </button>
              <span class="breadcrumb-separator">›</span>
              <span class="breadcrumb-current">{{ selectedDoc.title }}</span>
            </div>
            <div class="document-actions">
              <button class="btn btn-sm btn-secondary" @click="printDoc">🖨️ Print</button>
              <button class="btn btn-sm btn-info" @click="shareDoc">🔗 Share</button>
              <button class="btn btn-sm btn-primary" @click="downloadDoc">📥 Download</button>
            </div>
          </div>

          <div class="document-body">
            <h1>{{ selectedDoc.title }}</h1>
            <div class="document-meta">
              <span>📅 Updated: {{ formatDate(selectedDoc.lastUpdated) }}</span>
              <span>⏱️ Read time: {{ selectedDoc.readTime }}</span>
              <span v-if="selectedDoc.difficulty">🎯 {{ selectedDoc.difficulty }}</span>
            </div>

            <div class="content-wrapper">
              <div v-if="selectedDoc.type === 'setup_guide'" class="setup-guide">
                <!-- Step-by-step setup guide -->
                <div class="guide-progress">
                  <div class="progress-bar">
                    <div 
                      class="progress-fill" 
                      :style="{ width: `${(currentStep / selectedDoc.steps.length) * 100}%` }"
                    />
                  </div>
                  <span class="progress-text">Step {{ currentStep }} of {{ selectedDoc.steps.length }}</span>
                </div>

                <div class="step-content">
                  <div 
                    v-for="(step, index) in selectedDoc.steps" 
                    :key="index"
                    class="setup-step"
                    :class="{ 
                      active: index === currentStep - 1,
                      completed: index < currentStep - 1 
                    }"
                  >
                    <div class="step-header">
                      <div class="step-number">{{ index + 1 }}</div>
                      <h3>{{ step.title }}</h3>
                    </div>
                    <div v-if="index === currentStep - 1" class="step-body">
                      <div class="step-description" v-html="renderMarkdown(step.description)" />
                      <div v-if="step.code" class="code-block">
                        <div class="code-header">
                          <span>{{ step.codeLanguage || 'bash' }}</span>
                          <button class="copy-btn" @click="copyCode(step.code)">📋 Copy</button>
                        </div>
                        <pre><code>{{ step.code }}</code></pre>
                      </div>
                      <div v-if="step.warning" class="warning-box">
                        ⚠️ {{ step.warning }}
                      </div>
                      <div class="step-actions">
                        <button 
                          v-if="index > 0"
                          class="btn btn-secondary"
                          @click="currentStep = index"
                        >
                          ← Previous
                        </button>
                        <button 
                          v-if="index < selectedDoc.steps.length - 1"
                          class="btn btn-primary"
                          @click="currentStep = index + 2"
                        >
                          Next →
                        </button>
                        <button 
                          v-else
                          class="btn btn-success"
                          @click="completeGuide"
                        >
                          ✅ Complete Guide
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div v-else class="standard-content">
                <div class="content" v-html="renderMarkdown(selectedDoc.content)" />
                
                <!-- Table of Contents for longer documents -->
                <div v-if="selectedDoc.toc && selectedDoc.toc.length > 0" class="toc">
                  <h4>📑 Table of Contents</h4>
                  <ul>
                    <li v-for="item in selectedDoc.toc" :key="item.id">
                      <a :href="`#${item.id}`" @click="scrollToSection(item.id)">
                        {{ item.title }}
                      </a>
                    </li>
                  </ul>
                </div>
              </div>
            </div>

            <!-- Related Documents -->
            <div v-if="relatedDocs.length > 0" class="related-docs">
              <h4>📖 Related Documentation</h4>
              <div class="related-list">
                <button 
                  v-for="doc in relatedDocs" 
                  :key="doc.id"
                  class="related-item"
                  @click="selectDoc(doc)"
                >
                  <span class="related-icon">{{ doc.icon }}</span>
                  <span class="related-title">{{ doc.title }}</span>
                  <span class="related-type">{{ doc.type }}</span>
                </button>
              </div>
            </div>

            <!-- Feedback Section -->
            <div class="feedback-section">
              <h4>💬 Was this helpful?</h4>
              <div class="feedback-buttons">
                <button class="btn btn-success" @click="submitFeedback('helpful')">👍 Yes</button>
                <button class="btn btn-secondary" @click="submitFeedback('not-helpful')">👎 No</button>
              </div>
              <div v-if="showFeedbackForm" class="feedback-form">
                <textarea 
                  v-model="feedbackText"
                  placeholder="Tell us how we can improve this documentation..."
                  class="feedback-textarea"
                />
                <button class="btn btn-primary" @click="submitDetailedFeedback">Send Feedback</button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Status Messages -->
    <div v-if="statusMessage" class="alert" :class="statusSuccess ? 'alert-success' : 'alert-danger'">
      {{ statusMessage }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { renderMarkdownSafe } from '@/utils/markdown'
import api from '@/composables/useApi'

interface DocInfo {
  id: string
  title: string
  description?: string
  content?: string
  type: 'guide' | 'setup_guide' | 'reference' | 'troubleshooting'
  category: string
  icon: string
  lastUpdated: Date
  readTime: string
  difficulty?: 'Beginner' | 'Intermediate' | 'Advanced'
  tags: string[]
  toc?: { id: string; title: string }[]
  steps?: {
    title: string
    description: string
    code?: string
    codeLanguage?: string
    warning?: string
  }[]
  estimatedTime?: string
}

interface DocSection {
  id: string
  title: string
  icon: string
  docs: DocInfo[]
}

// Core state
const docs = ref<DocInfo[]>([])
const selectedDoc = ref<DocInfo | null>(null)
const searchQuery = ref('')
const searchResults = ref<DocInfo[]>([])
const expandedSections = ref<string[]>(['getting-started'])
const currentStep = ref(1)

// UI state
const showFeedbackForm = ref(false)
const feedbackText = ref('')
const statusMessage = ref('')
const statusSuccess = ref(false)

// Featured guides for welcome page
const featuredGuides = ref<DocInfo[]>([
  {
    id: 'quick-start',
    title: 'Quick Start Guide',
    description: 'Get your LawnBerry Pi up and running in 30 minutes',
    type: 'setup_guide',
    category: 'getting-started',
    icon: '🚀',
    lastUpdated: new Date(),
    readTime: '30 min',
    difficulty: 'Beginner',
    tags: ['setup', 'beginner'],
    estimatedTime: '30 minutes',
    steps: [
      {
        title: 'Hardware Setup',
        description: 'Connect your Raspberry Pi and sensors according to the hardware specification.',
        code: 'sudo systemctl enable lawnberry-backend\nsudo systemctl start lawnberry-backend',
        warning: 'Ensure all connections are secure before powering on'
      },
      {
        title: 'Software Installation',
        description: 'Install the LawnBerry Pi software stack.',
        code: 'git clone https://github.com/lawnberry/lawnberry-pi\ncd lawnberry-pi\n./install.sh'
      },
      {
        title: 'Initial Configuration',
        description: 'Configure your system settings and network.',
        code: 'sudo lawnberry-pi config --setup-wizard'
      }
    ]
  },
  {
    id: 'remote-access-setup',
    title: 'Remote Access Setup',
    description: 'Configure secure remote access with Cloudflare or ngrok',
    type: 'setup_guide',
    category: 'networking',
    icon: '🌐',
    lastUpdated: new Date(),
    readTime: '20 min',
    difficulty: 'Intermediate',
    tags: ['remote', 'security', 'cloudflare'],
    estimatedTime: '20 minutes',
    steps: [
      {
        title: 'Choose Remote Access Method',
        description: 'Select between Cloudflare Tunnel (recommended) or ngrok for remote access.',
        warning: 'Cloudflare Tunnel provides better security and reliability'
      },
      {
        title: 'Configure Cloudflare Tunnel',
        description: 'Set up Cloudflare Tunnel for secure remote access.',
        code: 'sudo cloudflared tunnel create lawnberry\nsudo cloudflared tunnel route dns lawnberry yourdomain.com'
      },
      {
        title: 'Enable ACME TLS',
        description: 'Configure automatic TLS certificate provisioning.',
        code: 'lawnberry-pi config remote-access --enable-acme --domain yourdomain.com'
      }
    ]
  },
  {
    id: 'auth-setup',
    title: 'Authentication Setup',
    description: 'Configure security levels from basic password to enterprise auth',
    type: 'setup_guide',
    category: 'security',
    icon: '🔐',
    lastUpdated: new Date(),
    readTime: '15 min',
    difficulty: 'Intermediate',
    tags: ['auth', 'security', 'totp'],
    estimatedTime: '15 minutes',
    steps: [
      {
        title: 'Basic Password Setup',
        description: 'Set up basic password authentication.',
        code: 'lawnberry-pi config auth --level password --set-password'
      },
      {
        title: 'Enable Two-Factor Authentication',
        description: 'Add TOTP for enhanced security.',
        code: 'lawnberry-pi config auth --level totp --setup-totp'
      },
      {
        title: 'Google OAuth Integration',
        description: 'Configure Google OAuth for enterprise security.',
        code: 'lawnberry-pi config auth --level google --client-id YOUR_CLIENT_ID'
      }
    ]
  },
  {
    id: 'maps-api-setup',
    title: 'Maps API Configuration',
    description: 'Set up Google Maps API or configure OpenStreetMap fallback',
    type: 'setup_guide',
    category: 'mapping',
    icon: '🗺️',
    lastUpdated: new Date(),
    readTime: '10 min',
    difficulty: 'Beginner',
    tags: ['maps', 'google', 'osm'],
    estimatedTime: '10 minutes',
    steps: [
      {
        title: 'Google Maps API Key',
        description: 'Obtain and configure Google Maps API key for premium mapping.',
        code: 'lawnberry-pi config maps --provider google --api-key YOUR_API_KEY'
      },
      {
        title: 'OpenStreetMap Fallback',
        description: 'Configure OpenStreetMap as fallback or primary provider.',
        code: 'lawnberry-pi config maps --provider osm --enable-fallback'
      },
      {
        title: 'GPS Policy Configuration',
        description: 'Configure GPS behavior and dead reckoning policies.',
        code: 'lawnberry-pi config gps --dead-reckoning-limit 120 --reduced-speed-factor 0.5'
      }
    ]
  }
])

// Documentation sections structure
const docSections = computed<DocSection[]>(() => [
  {
    id: 'getting-started',
    title: 'Getting Started',
    icon: '🚀',
    docs: docs.value.filter(doc => doc.category === 'getting-started')
  },
  {
    id: 'hardware',
    title: 'Hardware Setup',
    icon: '🔧',
    docs: docs.value.filter(doc => doc.category === 'hardware')
  },
  {
    id: 'networking',
    title: 'Networking & Remote Access',
    icon: '🌐',
    docs: docs.value.filter(doc => doc.category === 'networking')
  },
  {
    id: 'security',
    title: 'Security & Authentication',
    icon: '🔐',
    docs: docs.value.filter(doc => doc.category === 'security')
  },
  {
    id: 'mapping',
    title: 'Mapping & Navigation',
    icon: '🗺️',
    docs: docs.value.filter(doc => doc.category === 'mapping')
  },
  {
    id: 'ai',
    title: 'AI & Machine Learning',
    icon: '🤖',
    docs: docs.value.filter(doc => doc.category === 'ai')
  },
  {
    id: 'troubleshooting',
    title: 'Troubleshooting',
    icon: '🔧',
    docs: docs.value.filter(doc => doc.category === 'troubleshooting')
  },
  {
    id: 'api',
    title: 'API Reference',
    icon: '📖',
    docs: docs.value.filter(doc => doc.category === 'api')
  }
])

// Computed properties
const totalDocs = computed(() => docs.value.length)
const lastUpdated = computed(() => {
  const latest = docs.value.reduce((latest, doc) => 
    doc.lastUpdated > latest ? doc.lastUpdated : latest, new Date(0))
  return formatDate(latest)
})

const relatedDocs = computed(() => {
  if (!selectedDoc.value) return []
  
  return docs.value
    .filter(doc => 
      doc.id !== selectedDoc.value?.id &&
      (doc.category === selectedDoc.value?.category ||
       doc.tags.some(tag => selectedDoc.value?.tags.includes(tag)))
    )
    .slice(0, 3)
})

// Methods - Navigation
function toggleSection(sectionId: string) {
  const index = expandedSections.value.indexOf(sectionId)
  if (index === -1) {
    expandedSections.value.push(sectionId)
  } else {
    expandedSections.value.splice(index, 1)
  }
}

function selectDoc(doc: DocInfo) {
  selectedDoc.value = doc
  currentStep.value = 1
  scrollToTop()
}

// Methods - Search
function performSearch() {
  if (!searchQuery.value.trim()) {
    searchResults.value = []
    return
  }

  const query = searchQuery.value.toLowerCase()
  searchResults.value = docs.value.filter(doc =>
    doc.title.toLowerCase().includes(query) ||
    doc.description?.toLowerCase().includes(query) ||
    doc.tags.some(tag => tag.toLowerCase().includes(query)) ||
    doc.content?.toLowerCase().includes(query)
  ).map(doc => ({
    ...doc,
    excerpt: extractExcerpt(doc, query)
  }))
}

function extractExcerpt(doc: DocInfo, query: string): string {
  const content = doc.content || doc.description || ''
  const queryIndex = content.toLowerCase().indexOf(query.toLowerCase())
  if (queryIndex === -1) return content.substring(0, 150) + '...'
  
  const start = Math.max(0, queryIndex - 50)
  const end = Math.min(content.length, queryIndex + query.length + 50)
  return (start > 0 ? '...' : '') + content.substring(start, end) + (end < content.length ? '...' : '')
}

// Methods - Quick Actions
function showQuickStart() {
  const quickStart = featuredGuides.value.find(g => g.id === 'quick-start')
  if (quickStart) selectDoc(quickStart)
}

function showTroubleshooting() {
  expandedSections.value.push('troubleshooting')
  const troubleshootingDocs = docs.value.filter(doc => doc.category === 'troubleshooting')
  if (troubleshootingDocs.length > 0) selectDoc(troubleshootingDocs[0])
}

function showAPIRef() {
  expandedSections.value.push('api')
  const apiDocs = docs.value.filter(doc => doc.category === 'api')
  if (apiDocs.length > 0) selectDoc(apiDocs[0])
}

// Methods - Document Actions
function printDoc() {
  window.print()
}

function shareDoc() {
  if (navigator.share && selectedDoc.value) {
    navigator.share({
      title: selectedDoc.value.title,
      url: window.location.href
    })
  } else {
    navigator.clipboard.writeText(window.location.href)
    showStatus('Link copied to clipboard!', true)
  }
}

function downloadDoc() {
  if (!selectedDoc.value) return
  
  const content = `# ${selectedDoc.value.title}\n\n${selectedDoc.value.content || ''}`
  const blob = new Blob([content], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${selectedDoc.value.title.replace(/[^a-zA-Z0-9]/g, '_')}.md`
  a.click()
  URL.revokeObjectURL(url)
}

function copyCode(code: string) {
  navigator.clipboard.writeText(code)
  showStatus('Code copied to clipboard!', true)
}

// Methods - Setup Guide
function completeGuide() {
  showStatus('🎉 Guide completed! Great job!', true)
  // Could track completion status in localStorage
  localStorage.setItem(`guide_completed_${selectedDoc.value?.id}`, 'true')
}

// Methods - Feedback
function submitFeedback(type: 'helpful' | 'not-helpful') {
  if (type === 'not-helpful') {
    showFeedbackForm.value = true
  } else {
    showStatus('Thank you for your feedback!', true)
  }
}

function submitDetailedFeedback() {
  // Send feedback to backend
  console.log('Feedback submitted:', feedbackText.value)
  showStatus('Thank you for your detailed feedback!', true)
  showFeedbackForm.value = false
  feedbackText.value = ''
}

// Methods - Utilities
function renderMarkdown(content: string): string {
  return renderMarkdownSafe(content)
}

function formatDate(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    year: 'numeric',
    month: 'short',
    day: 'numeric'
  }).format(date)
}

function scrollToSection(id: string) {
  const element = document.getElementById(id)
  if (element) {
    element.scrollIntoView({ behavior: 'smooth' })
  }
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function showStatus(message: string, success = false) {
  statusMessage.value = message
  statusSuccess.value = success
  setTimeout(() => {
    statusMessage.value = ''
  }, 3000)
}

// Initialize documentation with featured guides and offline docs
async function loadDocumentation() {
  try {
    // Load featured guides as base documentation
    docs.value = [...featuredGuides.value]
    
    // Add additional offline documentation
    const offlineDocs: DocInfo[] = [
      {
        id: 'hardware-spec',
        title: 'Hardware Specification',
        description: 'Complete hardware requirements and compatibility guide',
        type: 'reference',
        category: 'hardware',
        icon: '🔩',
        lastUpdated: new Date(),
        readTime: '10 min',
        tags: ['hardware', 'raspberry-pi', 'sensors'],
        content: `
# Hardware Specification

## Supported Platforms
- **Primary**: Raspberry Pi 5 (4GB/8GB)
- **Compatible**: Raspberry Pi 4B (4GB/8GB)
- **OS**: Raspberry Pi OS Bookworm 64-bit

## Required Sensors
- GPS Module (ZED-F9P USB or NEO-8M UART; NEO-9M recommendation only)
- IMU/Compass (BNO085 baseline; backups: BNO055/MPU-9250)
- Camera Module v2
- Motor Controllers
- Power Management Board

## Optional Hardware
- (Non-baseline items removed: LiDAR, additional cameras, weather station, cellular modem)

## Power Requirements
- 5V 4A Power Supply (recommended)
- UPS/Battery Backup (optional)
- Solar Panel Integration (optional)
        `
      },
      {
        id: 'api-reference',
        title: 'REST API Reference',
        description: 'Complete API documentation for v1 and v2 endpoints',
        type: 'reference',
        category: 'api',
        icon: '🔌',
        lastUpdated: new Date(),
        readTime: '25 min',
        tags: ['api', 'rest', 'websocket'],
        content: `
# REST API Reference

## Base URLs
- **v1**: \`/api/v1\` - Legacy compatibility
- **v2**: \`/api/v2\` - Enhanced features

## Authentication
All endpoints require authentication except health checks.

### Headers
\`\`\`
Authorization: Bearer <token>
Content-Type: application/json
\`\`\`

## Core Endpoints

### GET /api/v2/telemetry
Get current system telemetry data.

### POST /api/v2/control/move
Send movement commands to the mower.

### GET /api/v2/settings
Retrieve system configuration.

### WebSocket: /ws/v2
Real-time telemetry and control interface.
        `
      },
      {
        id: 'troubleshooting-guide',
        title: 'Common Issues & Solutions',
        description: 'Troubleshooting guide for common problems',
        type: 'troubleshooting',
        category: 'troubleshooting',
        icon: '🚨',
        lastUpdated: new Date(),
        readTime: '15 min',
        tags: ['troubleshooting', 'debug', 'issues'],
        content: `
# Troubleshooting Guide

## GPS Issues
**Problem**: GPS not acquiring signal
**Solution**: 
1. Check antenna connection
2. Verify clear sky view
3. Configure dead reckoning fallback

## Network Connectivity
**Problem**: Cannot access web interface
**Solution**:
1. Check WiFi configuration
2. Verify firewall settings
3. Test local network connectivity

## Sensor Malfunctions
**Problem**: Sensors not responding
**Solution**:
1. Check power connections
2. Verify I2C/GPIO configuration
3. Run hardware self-test

## Performance Issues
**Problem**: System running slowly
**Solution**:
1. Check CPU/memory usage
2. Optimize AI model settings
3. Review log files for errors
        `
      }
    ]
    
    docs.value.push(...offlineDocs)
    
    // Try to load additional docs from backend
    try {
      const response = await api.get('/docs/list')
      if (response.data) {
        // Convert backend format to our format
        const backendDocs = response.data.map((doc: any) => ({
          id: doc.path,
          title: doc.name,
          type: 'reference' as const,
          category: 'reference',
          icon: '📄',
          lastUpdated: new Date(),
          readTime: '5 min',
          tags: ['reference'],
          content: doc.content || ''
        }))
        docs.value.push(...backendDocs)
      }
    } catch (error) {
      console.log('Backend docs not available, using offline documentation')
    }
    
  } catch (error) {
    console.error('Failed to load documentation:', error)
    showStatus('Using offline documentation only', false)
  }
}

// Lifecycle
onMounted(() => {
  loadDocumentation()
})

// Watch for search query changes
watch(searchQuery, (newQuery) => {
  if (newQuery.trim()) {
    performSearch()
  } else {
    searchResults.value = []
  }
})
</script>

<style scoped>
/* Page Structure */
.docs-view {
  max-width: 1400px;
  margin: 0 auto;
  padding: 2rem;
  color: #e6e6e6;
}

.page-header {
  text-align: center;
  margin-bottom: 2rem;
}

.page-header h1 {
  color: #00ff9f;
  font-size: 2.5rem;
  margin-bottom: 0.5rem;
  text-shadow: 0 0 10px #00ff9f33;
}

/* Search Section */
.search-section {
  margin-bottom: 2rem;
}

.search-bar {
  display: flex;
  max-width: 600px;
  margin: 0 auto 1rem;
  border: 2px solid #2c3e50;
  border-radius: 25px;
  overflow: hidden;
  background: #0b111b;
}

.search-input {
  flex: 1;
  padding: 0.75rem 1rem;
  background: transparent;
  border: none;
  color: #e6e6e6;
  font-size: 1rem;
}

.search-input:focus {
  outline: none;
}

.search-button {
  padding: 0.75rem 1rem;
  background: #00ff9f;
  border: none;
  color: #0b111b;
  cursor: pointer;
  font-size: 1rem;
}

.quick-actions {
  display: flex;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;
}

/* Layout */
.docs-layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 2rem;
  min-height: 600px;
}

@media (max-width: 1024px) {
  .docs-layout {
    grid-template-columns: 1fr;
  }
  
  .sidebar {
    order: 2;
  }
}

/* Sidebar */
.sidebar {
  background: #0b111b;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 1.5rem;
  height: fit-content;
  position: sticky;
  top: 2rem;
}

.nav-section h3 {
  color: #00ff9f;
  margin-bottom: 1rem;
  font-size: 1.1rem;
}

.nav-tree {
  space-y: 0.5rem;
}

.nav-category {
  margin-bottom: 1rem;
}

.category-toggle {
  display: flex;
  align-items: center;
  width: 100%;
  padding: 0.5rem;
  background: transparent;
  border: 1px solid #2c3e50;
  border-radius: 4px;
  color: #e6e6e6;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
}

.category-toggle:hover {
  background: #1a2332;
  border-color: #00ff9f;
}

.category-toggle.expanded {
  background: #1a2332;
  border-color: #00ff9f;
}

.nav-items {
  margin-top: 0.5rem;
  padding-left: 1rem;
  border-left: 2px solid #2c3e50;
}

.nav-item {
  display: block;
  width: 100%;
  padding: 0.4rem 0.5rem;
  background: transparent;
  border: none;
  color: #9aa4b2;
  cursor: pointer;
  text-align: left;
  border-radius: 4px;
  margin-bottom: 0.25rem;
  transition: all 0.2s;
}

.nav-item:hover {
  background: #1a2332;
  color: #e6e6e6;
}

.nav-item.active {
  background: #00ff9f22;
  color: #00ff9f;
  border-left: 3px solid #00ff9f;
}

/* Search Results */
.search-results {
  margin-top: 2rem;
  padding-top: 1rem;
  border-top: 1px solid #2c3e50;
}

.search-results h3 {
  color: #00ff9f;
  margin-bottom: 1rem;
  font-size: 1.1rem;
}

.result-list {
  space-y: 0.5rem;
}

.search-result {
  display: block;
  width: 100%;
  padding: 0.75rem;
  background: transparent;
  border: 1px solid #2c3e50;
  border-radius: 4px;
  color: #e6e6e6;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
  margin-bottom: 0.5rem;
}

.search-result:hover {
  background: #1a2332;
  border-color: #00ff9f;
}

.result-title {
  font-weight: 500;
  margin-bottom: 0.25rem;
  color: #00ff9f;
}

.result-excerpt {
  font-size: 0.875rem;
  color: #9aa4b2;
  line-height: 1.4;
}

/* Main Content */
.main-content {
  background: #0b111b;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 2rem;
  min-height: 600px;
}

/* Welcome Content */
.welcome-content {
  text-align: center;
}

.welcome-header h2 {
  color: #00ff9f;
  font-size: 2rem;
  margin-bottom: 0.5rem;
}

.welcome-header p {
  color: #9aa4b2;
  font-size: 1.1rem;
  margin-bottom: 2rem;
}

.featured-guides {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-bottom: 3rem;
}

.guide-card {
  background: #1a2332;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 1.5rem;
  cursor: pointer;
  transition: all 0.3s;
  text-align: left;
}

.guide-card:hover {
  background: #243447;
  border-color: #00ff9f;
  transform: translateY(-2px);
  box-shadow: 0 4px 20px rgba(0, 255, 159, 0.1);
}

.guide-icon {
  font-size: 2rem;
  margin-bottom: 1rem;
}

.guide-content h3 {
  color: #00ff9f;
  margin-bottom: 0.5rem;
}

.guide-content p {
  color: #9aa4b2;
  margin-bottom: 1rem;
  line-height: 1.5;
}

.guide-time {
  color: #58a6ff;
  font-size: 0.875rem;
  font-weight: 500;
}

/* Status Overview */
.status-overview {
  background: #1a2332;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 1.5rem;
}

.status-overview h3 {
  color: #00ff9f;
  margin-bottom: 1rem;
}

.status-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.status-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}

.status-icon {
  font-size: 1.5rem;
}

.status-info {
  display: flex;
  flex-direction: column;
}

.status-label {
  color: #9aa4b2;
  font-size: 0.875rem;
}

.status-value {
  color: #e6e6e6;
  font-weight: 500;
}

/* Document Content */
.document-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2rem;
  padding-bottom: 1rem;
  border-bottom: 1px solid #2c3e50;
}

.breadcrumb {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #9aa4b2;
}

.breadcrumb-item {
  background: none;
  border: none;
  color: #58a6ff;
  cursor: pointer;
  padding: 0;
}

.breadcrumb-current {
  color: #e6e6e6;
  font-weight: 500;
}

.document-actions {
  display: flex;
  gap: 0.5rem;
}

.document-body h1 {
  color: #00ff9f;
  font-size: 2rem;
  margin-bottom: 1rem;
}

.document-meta {
  display: flex;
  gap: 1rem;
  margin-bottom: 2rem;
  color: #9aa4b2;
  font-size: 0.875rem;
  flex-wrap: wrap;
}

/* Setup Guide */
.setup-guide {
  max-width: 800px;
}

.guide-progress {
  background: #1a2332;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 1rem;
  margin-bottom: 2rem;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: #2c3e50;
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: linear-gradient(90deg, #00ff9f, #58a6ff);
  transition: width 0.3s ease;
}

.progress-text {
  color: #e6e6e6;
  font-size: 0.875rem;
  font-weight: 500;
}

.setup-step {
  margin-bottom: 2rem;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  overflow: hidden;
}

.setup-step.active {
  border-color: #00ff9f;
  box-shadow: 0 0 20px rgba(0, 255, 159, 0.1);
}

.setup-step.completed {
  border-color: #58a6ff;
  opacity: 0.7;
}

.step-header {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 1rem;
  background: #1a2332;
}

.step-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #00ff9f;
  color: #0b111b;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: bold;
  font-size: 0.875rem;
}

.step-header h3 {
  color: #e6e6e6;
  margin: 0;
}

.step-body {
  padding: 1.5rem;
}

.step-description {
  margin-bottom: 1.5rem;
  line-height: 1.6;
}

.code-block {
  background: #0f1722;
  border: 1px solid #2c3e50;
  border-radius: 4px;
  margin: 1rem 0;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 1rem;
  background: #1a2332;
  border-bottom: 1px solid #2c3e50;
  font-size: 0.875rem;
}

.copy-btn {
  background: none;
  border: none;
  color: #58a6ff;
  cursor: pointer;
  font-size: 0.875rem;
}

.code-block pre {
  margin: 0;
  padding: 1rem;
  overflow-x: auto;
}

.code-block code {
  background: none;
  border: none;
  padding: 0;
  color: #e6e6e6;
}

.warning-box {
  background: #4a1a0f;
  border: 1px solid #8b4513;
  border-radius: 4px;
  padding: 1rem;
  margin: 1rem 0;
  color: #ffb366;
}

.step-actions {
  display: flex;
  gap: 1rem;
  justify-content: flex-end;
  margin-top: 2rem;
}

/* Standard Content */
.standard-content {
  max-width: 800px;
}

.content {
  line-height: 1.6;
}

.content h1, .content h2, .content h3, .content h4, .content h5, .content h6 {
  color: #00ff9f;
  margin: 1.5rem 0 0.75rem;
}

.content h1 { font-size: 2rem; }
.content h2 { font-size: 1.5rem; }
.content h3 { font-size: 1.25rem; }

.content p {
  margin: 0.75rem 0;
  color: #e6e6e6;
}

.content ul, .content ol {
  margin: 0.75rem 0;
  padding-left: 2rem;
}

.content li {
  margin: 0.25rem 0;
  color: #e6e6e6;
}

.content code {
  background: #0f1722;
  border: 1px solid #2c3e50;
  border-radius: 4px;
  padding: 0.2rem 0.4rem;
  color: #00ff9f;
  font-size: 0.9em;
}

.content pre {
  background: #0f1722;
  border: 1px solid #2c3e50;
  border-radius: 4px;
  padding: 1rem;
  overflow-x: auto;
  margin: 1rem 0;
}

.content pre code {
  background: none;
  border: none;
  padding: 0;
  color: #e6e6e6;
}

.content a {
  color: #58a6ff;
  text-decoration: none;
}

.content a:hover {
  text-decoration: underline;
}

.content blockquote {
  border-left: 4px solid #00ff9f;
  background: #1a2332;
  padding: 1rem;
  margin: 1rem 0;
  color: #9aa4b2;
}

/* Table of Contents */
.toc {
  background: #1a2332;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 1.5rem;
  margin: 2rem 0;
}

.toc h4 {
  color: #00ff9f;
  margin-bottom: 1rem;
}

.toc ul {
  list-style: none;
  padding-left: 0;
}

.toc li {
  margin-bottom: 0.5rem;
}

.toc a {
  color: #58a6ff;
  text-decoration: none;
  padding: 0.25rem 0;
  display: block;
}

.toc a:hover {
  color: #00ff9f;
}

/* Related Documents */
.related-docs {
  background: #1a2332;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 1.5rem;
  margin: 2rem 0;
}

.related-docs h4 {
  color: #00ff9f;
  margin-bottom: 1rem;
}

.related-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.related-item {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  padding: 0.75rem;
  background: transparent;
  border: 1px solid #2c3e50;
  border-radius: 4px;
  color: #e6e6e6;
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
}

.related-item:hover {
  background: #243447;
  border-color: #00ff9f;
}

.related-icon {
  font-size: 1.2rem;
}

.related-title {
  flex: 1;
  font-weight: 500;
}

.related-type {
  color: #9aa4b2;
  font-size: 0.875rem;
}

/* Feedback Section */
.feedback-section {
  background: #1a2332;
  border: 1px solid #2c3e50;
  border-radius: 8px;
  padding: 1.5rem;
  margin: 2rem 0;
}

.feedback-section h4 {
  color: #00ff9f;
  margin-bottom: 1rem;
}

.feedback-buttons {
  display: flex;
  gap: 0.5rem;
  margin-bottom: 1rem;
}

.feedback-form {
  margin-top: 1rem;
}

.feedback-textarea {
  width: 100%;
  min-height: 100px;
  padding: 0.75rem;
  background: #0b111b;
  border: 1px solid #2c3e50;
  border-radius: 4px;
  color: #e6e6e6;
  resize: vertical;
  margin-bottom: 1rem;
}

.feedback-textarea:focus {
  outline: none;
  border-color: #00ff9f;
}

/* Buttons */
.btn {
  padding: 0.5rem 1rem;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-weight: 500;
  transition: all 0.2s;
  text-decoration: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
}

.btn-primary {
  background: #00ff9f;
  color: #0b111b;
}

.btn-primary:hover {
  background: #00e68c;
}

.btn-secondary {
  background: #2c3e50;
  color: #e6e6e6;
}

.btn-secondary:hover {
  background: #3a4f6a;
}

.btn-info {
  background: #58a6ff;
  color: #0b111b;
}

.btn-info:hover {
  background: #4c94e6;
}

.btn-success {
  background: #28a745;
  color: white;
}

.btn-success:hover {
  background: #218838;
}

.btn-sm {
  padding: 0.375rem 0.75rem;
  font-size: 0.875rem;
}

/* Alerts */
.alert {
  padding: 1rem;
  border-radius: 4px;
  margin: 1rem 0;
  position: fixed;
  top: 2rem;
  right: 2rem;
  z-index: 1000;
  max-width: 400px;
}

.alert-success {
  background: #28a74533;
  border: 1px solid #28a745;
  color: #28a745;
}

.alert-danger {
  background: #dc354533;
  border: 1px solid #dc3545;
  color: #dc3545;
}

/* Responsive Design */
@media (max-width: 768px) {
  .docs-view {
    padding: 1rem;
  }
  
  .page-header h1 {
    font-size: 2rem;
  }
  
  .main-content {
    padding: 1rem;
  }
  
  .document-header {
    flex-direction: column;
    align-items: flex-start;
    gap: 1rem;
  }
  
  .quick-actions {
    flex-direction: column;
    align-items: center;
  }
  
  .featured-guides {
    grid-template-columns: 1fr;
  }
  
  .status-grid {
    grid-template-columns: 1fr;
  }
  
  .step-actions {
    flex-direction: column;
  }
  
  .feedback-buttons {
    flex-direction: column;
  }
  
  .alert {
    position: relative;
    top: auto;
    right: auto;
    max-width: none;
  }
}
</style>
