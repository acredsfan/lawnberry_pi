<template>
  <div class="ai-view">
    <div class="page-header">
      <h1>AI Training</h1>
      <p class="text-muted">Machine learning dataset management and model training</p>
    </div>

    <!-- Quick Stats -->
    <div class="stats-grid">
      <div class="stat-card">
        <div class="stat-icon">📊</div>
        <div class="stat-content">
          <div class="stat-value">{{ totalImages.toLocaleString() }}</div>
          <div class="stat-label">Total Images</div>
        </div>
      </div>
      
      <div class="stat-card">
        <div class="stat-icon">🏷️</div>
        <div class="stat-content">
          <div class="stat-value">{{ labeledImages.toLocaleString() }}</div>
          <div class="stat-label">Labeled Images</div>
        </div>
      </div>
      
      <div class="stat-card">
        <div class="stat-icon">🤖</div>
        <div class="stat-content">
          <div class="stat-value">{{ modelAccuracy }}%</div>
          <div class="stat-label">Model Accuracy</div>
        </div>
      </div>
      
      <div class="stat-card">
        <div class="stat-icon">💾</div>
        <div class="stat-content">
          <div class="stat-value">{{ (datasetSize / 1024 / 1024).toFixed(1) }} MB</div>
          <div class="stat-label">Dataset Size</div>
        </div>
      </div>
    </div>

    <!-- Training Tabs -->
    <div class="training-tabs">
      <button 
        v-for="tab in tabs" 
        :key="tab.id"
        :class="{ active: activeTab === tab.id }"
        @click="activeTab = tab.id"
        class="tab-button"
      >
        {{ tab.label }}
      </button>
    </div>

    <!-- Dataset Management -->
    <div v-if="activeTab === 'dataset'" class="tab-content">
      <div class="card">
        <div class="card-header">
          <h3>Dataset Overview</h3>
          <div class="header-actions">
            <button @click="refreshDataset" class="btn btn-sm btn-secondary">
              🔄 Refresh
            </button>
            <button @click="showUploadModal = true" class="btn btn-sm btn-primary">
              📤 Upload Images
            </button>
          </div>
        </div>
        <div class="card-body">
          <div class="dataset-categories">
            <div 
              v-for="category in datasetCategories" 
              :key="category.name"
              class="category-card"
              :class="{ selected: selectedCategory === category.name }"
              @click="selectedCategory = category.name"
            >
              <div class="category-header">
                <h4>{{ category.name }}</h4>
                <span class="image-count">{{ category.count }} images</span>
              </div>
              <div class="category-progress">
                <div class="progress-bar">
                  <div 
                    class="progress-fill" 
                    :style="{ width: `${(category.labeled / category.count) * 100}%` }"
                  ></div>
                </div>
                <span class="progress-text">{{ category.labeled }}/{{ category.count }} labeled</span>
              </div>
              <div class="category-actions">
                <button @click.stop="labelCategory(category)" class="btn btn-xs btn-success">
                  🏷️ Label
                </button>
                <button @click.stop="exportCategory(category)" class="btn btn-xs btn-info">
                  📥 Export
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Image Gallery -->
      <div v-if="selectedCategory" class="card">
        <div class="card-header">
          <h3>{{ selectedCategory }} Images</h3>
          <div class="gallery-controls">
            <select v-model="imageFilter" class="form-control-sm">
              <option value="all">All Images</option>
              <option value="labeled">Labeled Only</option>
              <option value="unlabeled">Unlabeled Only</option>
            </select>
            <button @click="selectAllImages" class="btn btn-xs btn-secondary">
              Select All
            </button>
            <button @click="clearSelection" class="btn btn-xs btn-secondary">
              Clear Selection
            </button>
          </div>
        </div>
        <div class="card-body">
          <div class="image-gallery">
            <div 
              v-for="image in filteredImages" 
              :key="image.id"
              class="image-item"
              :class="{ 
                selected: selectedImages.includes(image.id),
                labeled: image.labels.length > 0 
              }"
              @click="toggleImageSelection(image.id)"
            >
              <div class="image-wrapper">
                <img :src="image.thumbnail_url" :alt="image.filename" />
                <div class="image-overlay">
                  <div class="image-info">
                    <span class="filename">{{ image.filename }}</span>
                    <span class="timestamp">{{ formatDateTime(image.captured_at) }}</span>
                  </div>
                  <div class="label-badges">
                    <span 
                      v-for="label in image.labels" 
                      :key="label.id"
                      class="label-badge"
                      :class="`label-${label.category}`"
                    >
                      {{ label.name }}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
          
          <div v-if="selectedImages.length > 0" class="batch-actions">
            <div class="selection-info">
              {{ selectedImages.length }} images selected
            </div>
            <div class="action-buttons">
              <button @click="batchLabel" class="btn btn-success">
                🏷️ Batch Label
              </button>
              <button @click="batchExport" class="btn btn-info">
                📥 Export Selected
              </button>
              <button @click="batchDelete" class="btn btn-danger">
                🗑️ Delete Selected
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Export Management -->
    <div v-if="activeTab === 'export'" class="tab-content">
      <div class="card">
        <div class="card-header">
          <h3>Dataset Export</h3>
          <button @click="createNewExport" class="btn btn-sm btn-primary">
            ➕ Create Export
          </button>
        </div>
        <div class="card-body">
          <div class="export-formats">
            <div class="format-grid">
              <div 
                v-for="format in exportFormats" 
                :key="format.id"
                class="format-card"
                :class="{ selected: selectedExportFormat === format.id }"
                @click="selectedExportFormat = format.id"
              >
                <div class="format-icon">{{ format.icon }}</div>
                <div class="format-info">
                  <h4>{{ format.name }}</h4>
                  <p>{{ format.description }}</p>
                  <div class="format-details">
                    <span>{{ format.fileType }}</span>
                    <span>{{ format.compatibility }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="export-options">
            <h4>Export Configuration</h4>
            <div class="options-grid">
              <div class="option-group">
                <label>Categories to Include</label>
                <div class="category-checkboxes">
                  <label v-for="category in datasetCategories" :key="category.name" class="checkbox-label">
                    <input 
                      type="checkbox" 
                      :value="category.name"
                      v-model="exportConfig.categories"
                    />
                    {{ category.name }} ({{ category.count }})
                  </label>
                </div>
              </div>
              
              <div class="option-group">
                <label>
                  <input 
                    type="checkbox" 
                    v-model="exportConfig.includeUnlabeled"
                  />
                  Include unlabeled images
                </label>
              </div>
              
              <div class="option-group">
                <label>Train/Test Split</label>
                <div class="split-controls">
                  <label>Train: {{ exportConfig.trainSplit }}%</label>
                  <input 
                    v-model.number="exportConfig.trainSplit" 
                    type="range" 
                    min="60" 
                    max="90" 
                    step="5"
                    @input="exportConfig.testSplit = 100 - exportConfig.trainSplit"
                  />
                  <label>Test: {{ exportConfig.testSplit }}%</label>
                </div>
              </div>
              
              <div class="option-group">
                <label>Image Size</label>
                <select v-model="exportConfig.imageSize" class="form-control">
                  <option value="original">Original Size</option>
                  <option value="224x224">224x224 (Standard)</option>
                  <option value="416x416">416x416 (YOLO)</option>
                  <option value="512x512">512x512 (High Resolution)</option>
                </select>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Export History -->
      <div class="card">
        <div class="card-header">
          <h3>Export History</h3>
        </div>
        <div class="card-body">
          <div class="export-list">
            <div 
              v-for="exportJob in exportHistory" 
              :key="exportJob.id"
              class="export-item"
            >
              <div class="export-header">
                <div class="export-info">
                  <h4>{{ exportJob.name }}</h4>
                  <span class="export-format">{{ exportJob.format }}</span>
                  <span class="export-status" :class="`status-${exportJob.status}`">
                    {{ formatExportStatus(exportJob.status) }}
                  </span>
                </div>
                <div class="export-actions">
                  <button 
                    v-if="exportJob.status === 'completed'"
                    @click="downloadExport(exportJob)"
                    class="btn btn-xs btn-success"
                  >
                    📥 Download
                  </button>
                  <button @click="deleteExport(exportJob)" class="btn btn-xs btn-danger">
                    🗑️ Delete
                  </button>
                </div>
              </div>
              
              <div class="export-details">
                <span>Created: {{ formatDateTime(exportJob.created_at) }}</span>
                <span>Size: {{ (exportJob.file_size / 1024 / 1024).toFixed(1) }} MB</span>
                <span>Images: {{ exportJob.image_count }}</span>
                <span v-if="exportJob.download_count">Downloads: {{ exportJob.download_count }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Model Training -->
    <div v-if="activeTab === 'training'" class="tab-content">
      <div class="card">
        <div class="card-header">
          <h3>Model Training</h3>
          <button 
            @click="startTraining" 
            class="btn btn-sm btn-primary"
            :disabled="isTraining"
          >
            {{ isTraining ? '🔄 Training...' : '🚀 Start Training' }}
          </button>
        </div>
        <div class="card-body">
          <div class="training-status">
            <div v-if="!isTraining && !trainingHistory.length" class="no-training">
              <p>No training sessions yet. Configure your training parameters and start your first training run.</p>
            </div>
            
            <div v-if="isTraining" class="current-training">
              <div class="training-progress">
                <h4>Current Training Session</h4>
                <div class="progress-info">
                  <span>Epoch {{ currentTraining.current_epoch }}/{{ currentTraining.total_epochs }}</span>
                  <span>{{ currentTraining.progress }}% complete</span>
                </div>
                <div class="progress-bar">
                  <div class="progress-fill" :style="{ width: `${currentTraining.progress}%` }"></div>
                </div>
                <div class="training-metrics">
                  <div class="metric">
                    <label>Loss</label>
                    <span>{{ currentTraining.current_loss.toFixed(4) }}</span>
                  </div>
                  <div class="metric">
                    <label>Accuracy</label>
                    <span>{{ (currentTraining.current_accuracy * 100).toFixed(2) }}%</span>
                  </div>
                  <div class="metric">
                    <label>Learning Rate</label>
                    <span>{{ currentTraining.learning_rate.toExponential(2) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- Training Configuration -->
          <div class="training-config">
            <h4>Training Configuration</h4>
            <div class="config-grid">
              <div class="config-group">
                <label>Model Architecture</label>
                <select v-model="trainingConfig.architecture" class="form-control">
                  <option value="mobilenet">MobileNet (Fast, Mobile)</option>
                  <option value="resnet50">ResNet50 (Balanced)</option>
                  <option value="efficientnet">EfficientNet (Accurate)</option>
                  <option value="yolo">YOLO (Object Detection)</option>
                </select>
              </div>
              
              <div class="config-group">
                <label>Learning Rate</label>
                <input 
                  v-model.number="trainingConfig.learningRate" 
                  type="number" 
                  step="0.0001"
                  min="0.0001"
                  max="0.1"
                  class="form-control"
                />
              </div>
              
              <div class="config-group">
                <label>Batch Size</label>
                <select v-model.number="trainingConfig.batchSize" class="form-control">
                  <option value="8">8 (Low Memory)</option>
                  <option value="16">16 (Balanced)</option>
                  <option value="32">32 (High Memory)</option>
                </select>
              </div>
              
              <div class="config-group">
                <label>Epochs</label>
                <input 
                  v-model.number="trainingConfig.epochs" 
                  type="number" 
                  min="1"
                  max="1000"
                  class="form-control"
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- Training History -->
      <div v-if="trainingHistory.length" class="card">
        <div class="card-header">
          <h3>Training History</h3>
        </div>
        <div class="card-body">
          <div class="training-list">
            <div 
              v-for="session in trainingHistory" 
              :key="session.id"
              class="training-item"
            >
              <div class="training-header">
                <div class="training-info">
                  <h4>{{ session.name }}</h4>
                  <span class="training-architecture">{{ session.architecture }}</span>
                  <span class="training-status" :class="`status-${session.status}`">
                    {{ formatTrainingStatus(session.status) }}
                  </span>
                </div>
                <div class="training-actions">
                  <button 
                    v-if="session.status === 'completed'"
                    @click="deployModel(session)"
                    class="btn btn-xs btn-primary"
                  >
                    🚀 Deploy
                  </button>
                  <button @click="viewTrainingDetails(session)" class="btn btn-xs btn-info">
                    📊 Details
                  </button>
                </div>
              </div>
              
              <div class="training-details">
                <span>Duration: {{ session.duration_minutes }} min</span>
                <span>Final Accuracy: {{ (session.final_accuracy * 100).toFixed(2) }}%</span>
                <span>Epochs: {{ session.epochs_completed }}/{{ session.total_epochs }}</span>
                <span>Dataset Size: {{ session.dataset_size }} images</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- Upload Modal -->
    <div v-if="showUploadModal" class="modal-overlay" @click="closeUploadModal">
      <div class="modal-content" @click.stop>
        <div class="modal-header">
          <h3>Upload Training Images</h3>
          <button @click="closeUploadModal" class="btn btn-sm btn-secondary">✖️</button>
        </div>
        <div class="modal-body">
          <div class="upload-area" @dragover.prevent @drop="handleDrop">
            <div class="upload-content">
              <div class="upload-icon">📤</div>
              <p>Drag and drop images here, or click to select</p>
              <input 
                type="file" 
                multiple 
                accept="image/*"
                @change="handleFileSelect"
                class="file-input"
              />
            </div>
          </div>
          
          <div v-if="uploadFiles.length" class="upload-preview">
            <h4>Files to Upload ({{ uploadFiles.length }})</h4>
            <div class="file-list">
              <div v-for="(file, index) in uploadFiles" :key="index" class="file-item">
                <span>{{ file.name }}</span>
                <span>{{ (file.size / 1024).toFixed(1) }} KB</span>
                <button @click="removeFile(index)" class="btn btn-xs btn-danger">✖️</button>
              </div>
            </div>
          </div>
          
          <div class="upload-options">
            <div class="form-group">
              <label>Category</label>
              <select v-model="uploadCategory" class="form-control">
                <option v-for="category in datasetCategories" :key="category.name" :value="category.name">
                  {{ category.name }}
                </option>
                <option value="new">Create New Category...</option>
              </select>
            </div>
            
            <div v-if="uploadCategory === 'new'" class="form-group">
              <label>New Category Name</label>
              <input v-model="newCategoryName" type="text" class="form-control" />
            </div>
          </div>
        </div>
        <div class="modal-footer">
          <button @click="closeUploadModal" class="btn btn-secondary">Cancel</button>
          <button 
            @click="uploadImages" 
            class="btn btn-primary"
            :disabled="uploading || uploadFiles.length === 0"
          >
            {{ uploading ? 'Uploading...' : 'Upload Images' }}
          </button>
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
import { ref, computed, onMounted } from 'vue'
import { useApiService } from '@/services/api'

const api = useApiService()

// State
const activeTab = ref('dataset')
const selectedCategory = ref('')
const selectedImages = ref<string[]>([])
const imageFilter = ref('all')
const selectedExportFormat = ref('coco')
const showUploadModal = ref(false)
const uploading = ref(false)
const uploadFiles = ref<File[]>([])
const uploadCategory = ref('')
const newCategoryName = ref('')
const isTraining = ref(false)
const statusMessage = ref('')
const statusSuccess = ref(false)

// Tabs
const tabs = [
  { id: 'dataset', label: 'Dataset' },
  { id: 'export', label: 'Export' },
  { id: 'training', label: 'Training' }
]

// Data
const totalImages = ref(1247)
const labeledImages = ref(892)
const modelAccuracy = ref(94.2)
const datasetSize = ref(245.7 * 1024 * 1024) // bytes

const datasetCategories = ref([
  { name: 'grass', count: 456, labeled: 398 },
  { name: 'obstacles', count: 234, labeled: 187 },
  { name: 'boundaries', count: 189, labeled: 156 },
  { name: 'flowers', count: 156, labeled: 89 },
  { name: 'weeds', count: 212, labeled: 62 }
])

const exportFormats = ref([
  {
    id: 'coco',
    name: 'COCO Format',
    icon: '🏷️',
    description: 'Common Objects in COntext format',
    fileType: 'JSON + Images',
    compatibility: 'TensorFlow, PyTorch'
  },
  {
    id: 'yolo',
    name: 'YOLO Format',
    icon: '🎯',
    description: 'You Only Look Once format',
    fileType: 'TXT + Images',
    compatibility: 'YOLO, Darknet'
  },
  {
    id: 'pascal',
    name: 'Pascal VOC',
    icon: '📋',
    description: 'Pascal Visual Object Classes',
    fileType: 'XML + Images',
    compatibility: 'Classic ML frameworks'
  },
  {
    id: 'tensorflow',
    name: 'TensorFlow',
    icon: '🤖',
    description: 'TensorFlow TFRecord format',
    fileType: 'TFRecord',
    compatibility: 'TensorFlow, TensorFlow Lite'
  }
])

const exportConfig = ref({
  categories: ['grass', 'obstacles'],
  includeUnlabeled: false,
  trainSplit: 80,
  testSplit: 20,
  imageSize: '224x224'
})

const exportHistory = ref([
  {
    id: 1,
    name: 'Full Dataset Export',
    format: 'COCO',
    status: 'completed',
    created_at: '2024-09-27T14:30:00',
    file_size: 45.2 * 1024 * 1024,
    image_count: 892,
    download_count: 3
  },
  {
    id: 2,
    name: 'Grass Detection Dataset',
    format: 'YOLO',
    status: 'processing',
    created_at: '2024-09-28T10:15:00',
    file_size: 0,
    image_count: 456,
    download_count: 0
  }
])

const trainingConfig = ref({
  architecture: 'mobilenet',
  learningRate: 0.001,
  batchSize: 16,
  epochs: 50
})

const currentTraining = ref({
  current_epoch: 23,
  total_epochs: 50,
  progress: 46,
  current_loss: 0.3245,
  current_accuracy: 0.8967,
  learning_rate: 0.001
})

const trainingHistory = ref([
  {
    id: 1,
    name: 'Grass Classification v1',
    architecture: 'MobileNet',
    status: 'completed',
    duration_minutes: 125,
    final_accuracy: 0.942,
    epochs_completed: 50,
    total_epochs: 50,
    dataset_size: 892
  },
  {
    id: 2,
    name: 'Multi-class Detection',
    architecture: 'YOLO',
    status: 'failed',
    duration_minutes: 67,
    final_accuracy: 0.0,
    epochs_completed: 12,
    total_epochs: 100,
    dataset_size: 1247
  }
])

// Mock images for selected category
const categoryImages = ref([
  {
    id: '1',
    filename: 'IMG_001.jpg',
    thumbnail_url: '/api/v2/training/images/1/thumbnail',
    captured_at: '2024-09-28T10:30:00',
    labels: [
      { id: 1, name: 'grass', category: 'vegetation' },
      { id: 2, name: 'healthy', category: 'condition' }
    ]
  },
  {
    id: '2',
    filename: 'IMG_002.jpg',
    thumbnail_url: '/api/v2/training/images/2/thumbnail',
    captured_at: '2024-09-28T10:31:00',
    labels: []
  }
  // ... more images would be loaded from API
])

// Computed
const filteredImages = computed(() => {
  if (!selectedCategory.value) return []
  
  switch (imageFilter.value) {
    case 'labeled':
      return categoryImages.value.filter(img => img.labels.length > 0)
    case 'unlabeled':
      return categoryImages.value.filter(img => img.labels.length === 0)
    default:
      return categoryImages.value
  }
})

// Methods
async function refreshDataset() {
  try {
    const response = await api.get('/api/v2/training/dataset')
    // Update dataset statistics
    showStatus('Dataset refreshed', true)
  } catch (error) {
    showStatus('Failed to refresh dataset', false)
  }
}

function toggleImageSelection(imageId: string) {
  const index = selectedImages.value.indexOf(imageId)
  if (index > -1) {
    selectedImages.value.splice(index, 1)
  } else {
    selectedImages.value.push(imageId)
  }
}

function selectAllImages() {
  selectedImages.value = filteredImages.value.map(img => img.id)
}

function clearSelection() {
  selectedImages.value = []
}

function labelCategory(category: any) {
  showStatus(`Labeling interface for ${category.name} coming soon`, true)
}

async function exportCategory(category: any) {
  try {
    const response = await api.post('/api/v2/training/export', {
      categories: [category.name],
      format: selectedExportFormat.value,
      ...exportConfig.value
    })
    showStatus(`Export started for ${category.name}`, true)
  } catch (error) {
    showStatus(`Failed to export ${category.name}`, false)
  }
}

function createNewExport() {
  showStatus('Creating export with current configuration...', true)
}

async function downloadExport(exportJob: any) {
  try {
    const response = await api.get(`/api/v2/training/export/${exportJob.id}/download`, {
      responseType: 'blob'
    })
    
    // Create download link
    const url = window.URL.createObjectURL(new Blob([response.data]))
    const link = document.createElement('a')
    link.href = url
    link.download = `${exportJob.name}.zip`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    
    showStatus('Download started', true)
  } catch (error) {
    showStatus('Download failed', false)
  }
}

function batchLabel() {
  showStatus(`Batch labeling ${selectedImages.value.length} images coming soon`, true)
}

function batchExport() {
  showStatus(`Exporting ${selectedImages.value.length} selected images coming soon`, true)
}

async function batchDelete() {
  if (!confirm(`Delete ${selectedImages.value.length} selected images?`)) return
  
  try {
    await api.delete('/api/v2/training/images', {
      data: { image_ids: selectedImages.value }
    })
    showStatus(`Deleted ${selectedImages.value.length} images`, true)
    selectedImages.value = []
    await refreshDataset()
  } catch (error) {
    showStatus('Failed to delete images', false)
  }
}

function closeUploadModal() {
  showUploadModal.value = false
  uploadFiles.value = []
  uploadCategory.value = ''
  newCategoryName.value = ''
}

function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement
  if (target.files) {
    uploadFiles.value = Array.from(target.files)
  }
}

function handleDrop(event: DragEvent) {
  event.preventDefault()
  if (event.dataTransfer?.files) {
    uploadFiles.value = Array.from(event.dataTransfer.files)
  }
}

function removeFile(index: number) {
  uploadFiles.value.splice(index, 1)
}

async function uploadImages() {
  if (uploadFiles.value.length === 0) return
  
  uploading.value = true
  try {
    const formData = new FormData()
    uploadFiles.value.forEach(file => {
      formData.append('images', file)
    })
    formData.append('category', uploadCategory.value === 'new' ? newCategoryName.value : uploadCategory.value)
    
    await api.post('/api/v2/training/images/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' }
    })
    
    showStatus(`Uploaded ${uploadFiles.value.length} images successfully`, true)
    closeUploadModal()
    await refreshDataset()
  } catch (error) {
    showStatus('Upload failed', false)
  } finally {
    uploading.value = false
  }
}

async function startTraining() {
  isTraining.value = true
  try {
    await api.post('/api/v2/training/start', trainingConfig.value)
    showStatus('Training started successfully', true)
  } catch (error) {
    showStatus('Failed to start training', false)
    isTraining.value = false
  }
}

function deployModel(session: any) {
  showStatus(`Deploying model ${session.name} coming soon`, true)
}

function viewTrainingDetails(session: any) {
  showStatus(`Training details for ${session.name} coming soon`, true)
}

function deleteExport(exportJob: any) {
  if (confirm(`Delete export "${exportJob.name}"?`)) {
    showStatus(`Export ${exportJob.name} deleted`, true)
  }
}

function formatExportStatus(status: string): string {
  const statusMap = {
    processing: 'Processing',
    completed: 'Completed',
    failed: 'Failed'
  }
  return statusMap[status as keyof typeof statusMap] || status
}

function formatTrainingStatus(status: string): string {
  const statusMap = {
    completed: 'Completed',
    failed: 'Failed',
    running: 'Running'
  }
  return statusMap[status as keyof typeof statusMap] || status
}

function formatDateTime(dateString: string): string {
  try {
    return new Date(dateString).toLocaleString()
  } catch {
    return dateString
  }
}

function showStatus(message: string, success: boolean) {
  statusMessage.value = message
  statusSuccess.value = success
  setTimeout(() => {
    statusMessage.value = ''
  }, 3000)
}

onMounted(async () => {
  await refreshDataset()
  
  // Set default upload category
  if (datasetCategories.value.length > 0) {
    uploadCategory.value = datasetCategories.value[0].name
  }
})
</script>

<style scoped>
.ai-view {
  padding: 0;
}

.page-header {
  margin-bottom: 2rem;
}

.page-header h1 {
  margin-bottom: 0.5rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.stat-card {
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  padding: 1.5rem;
  display: flex;
  align-items: center;
  gap: 1rem;
}

.stat-icon {
  font-size: 2rem;
}

.stat-content {
  flex: 1;
}

.stat-value {
  font-size: 2rem;
  font-weight: 600;
  color: var(--accent-green);
  margin-bottom: 0.25rem;
}

.stat-label {
  color: var(--text-muted);
  font-size: 0.875rem;
}

.training-tabs {
  display: flex;
  border-bottom: 2px solid var(--primary-dark);
  margin-bottom: 2rem;
  overflow-x: auto;
}

.tab-button {
  background: none;
  border: none;
  padding: 1rem 2rem;
  color: var(--text-color);
  font-weight: 500;
  cursor: pointer;
  border-bottom: 3px solid transparent;
  transition: all 0.3s ease;
  white-space: nowrap;
}

.tab-button:hover {
  background-color: var(--primary-dark);
  color: var(--primary-light);
}

.tab-button.active {
  border-bottom-color: var(--accent-green);
  color: var(--accent-green);
  background-color: var(--primary-dark);
}

.tab-content {
  animation: slideIn 0.3s ease;
}

@keyframes slideIn {
  from {
    opacity: 0;
    transform: translateX(20px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}

.card {
  background: var(--secondary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  margin-bottom: 2rem;
}

.card-header {
  background: var(--primary-dark);
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--primary-light);
  border-radius: 8px 8px 0 0;
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.card-header h3 {
  margin: 0;
  color: var(--accent-green);
  font-size: 1.25rem;
}

.header-actions, .gallery-controls {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}

.card-body {
  padding: 1.5rem;
}

.dataset-categories {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
}

.category-card {
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
}

.category-card:hover {
  border-color: var(--accent-green);
  transform: translateY(-2px);
}

.category-card.selected {
  border-color: var(--accent-green);
  background: rgba(0, 255, 146, 0.1);
}

.category-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

.category-header h4 {
  margin: 0;
  color: var(--text-color);
}

.image-count {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.category-progress {
  margin-bottom: 1rem;
}

.progress-bar {
  width: 100%;
  height: 8px;
  background: var(--primary-light);
  border-radius: 4px;
  overflow: hidden;
  margin-bottom: 0.5rem;
}

.progress-fill {
  height: 100%;
  background: var(--accent-green);
  transition: width 0.3s ease;
}

.progress-text {
  font-size: 0.875rem;
  color: var(--text-muted);
}

.category-actions {
  display: flex;
  gap: 0.5rem;
}

.image-gallery {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.image-item {
  border: 2px solid var(--primary-light);
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  transition: all 0.3s ease;
}

.image-item:hover {
  border-color: var(--accent-green);
}

.image-item.selected {
  border-color: var(--accent-green);
  box-shadow: 0 0 0 2px rgba(0, 255, 146, 0.3);
}

.image-item.labeled {
  border-color: #28a745;
}

.image-wrapper {
  position: relative;
}

.image-wrapper img {
  width: 100%;
  height: 150px;
  object-fit: cover;
}

.image-overlay {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  background: linear-gradient(transparent, rgba(0, 0, 0, 0.8));
  padding: 1rem;
  color: white;
}

.image-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  margin-bottom: 0.5rem;
}

.filename {
  font-weight: 500;
  font-size: 0.875rem;
}

.timestamp {
  font-size: 0.75rem;
  opacity: 0.8;
}

.label-badges {
  display: flex;
  gap: 0.25rem;
  flex-wrap: wrap;
}

.label-badge {
  padding: 0.125rem 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 500;
}

.label-vegetation {
  background: #28a745;
  color: white;
}

.label-condition {
  background: #007bff;
  color: white;
}

.batch-actions {
  background: var(--primary-dark);
  padding: 1rem;
  border-radius: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 1rem;
}

.selection-info {
  font-weight: 500;
  color: var(--text-color);
}

.action-buttons {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.format-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1rem;
  margin-bottom: 2rem;
}

.format-card {
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  padding: 1rem;
  cursor: pointer;
  transition: all 0.3s ease;
  display: flex;
  gap: 1rem;
}

.format-card:hover {
  border-color: var(--accent-green);
}

.format-card.selected {
  border-color: var(--accent-green);
  background: rgba(0, 255, 146, 0.1);
}

.format-icon {
  font-size: 2rem;
}

.format-info h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-color);
}

.format-info p {
  margin: 0 0 0.5rem 0;
  color: var(--text-muted);
  font-size: 0.875rem;
}

.format-details {
  display: flex;
  gap: 1rem;
  font-size: 0.75rem;
  color: var(--text-muted);
}

.export-options {
  background: var(--primary-dark);
  padding: 1.5rem;
  border-radius: 8px;
}

.export-options h4 {
  margin: 0 0 1rem 0;
  color: var(--accent-green);
}

.options-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 1.5rem;
}

.option-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.option-group label {
  color: var(--text-color);
  font-weight: 500;
}

.category-checkboxes {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: var(--secondary-dark);
  border-radius: 4px;
  cursor: pointer;
}

.split-controls {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.export-list, .training-list {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.export-item, .training-item {
  background: var(--primary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  padding: 1rem;
}

.export-header, .training-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 1rem;
}

.export-info, .training-info {
  flex: 1;
}

.export-info h4, .training-info h4 {
  margin: 0 0 0.5rem 0;
  color: var(--text-color);
}

.export-format, .training-architecture {
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-right: 1rem;
}

.export-status, .training-status {
  padding: 0.25rem 0.75rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 600;
  text-transform: uppercase;
}

.status-completed {
  background: rgba(40, 167, 69, 0.2);
  color: #28a745;
  border: 1px solid #28a745;
}

.status-processing, .status-running {
  background: rgba(0, 255, 146, 0.2);
  color: var(--accent-green);
  border: 1px solid var(--accent-green);
}

.status-failed {
  background: rgba(255, 67, 67, 0.2);
  color: #ff4343;
  border: 1px solid #ff4343;
}

.export-actions, .training-actions {
  display: flex;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.export-details, .training-details {
  display: flex;
  gap: 1rem;
  font-size: 0.875rem;
  color: var(--text-muted);
  flex-wrap: wrap;
}

.training-config {
  background: var(--primary-dark);
  padding: 1.5rem;
  border-radius: 8px;
  margin-top: 2rem;
}

.training-config h4 {
  margin: 0 0 1rem 0;
  color: var(--accent-green);
}

.config-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.config-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.config-group label {
  color: var(--text-color);
  font-weight: 500;
}

.current-training {
  background: var(--primary-dark);
  padding: 1.5rem;
  border-radius: 8px;
  margin-bottom: 2rem;
}

.training-progress h4 {
  margin: 0 0 1rem 0;
  color: var(--accent-green);
}

.progress-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-muted);
}

.training-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
  margin-top: 1rem;
}

.metric {
  text-align: center;
  padding: 0.75rem;
  background: var(--secondary-dark);
  border-radius: 4px;
}

.metric label {
  display: block;
  font-size: 0.875rem;
  color: var(--text-muted);
  margin-bottom: 0.25rem;
}

.metric span {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-color);
}

.no-training {
  text-align: center;
  padding: 3rem 1rem;
  color: var(--text-muted);
}

.btn {
  padding: 0.75rem 1.5rem;
  border: none;
  border-radius: 4px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.3s ease;
}

.btn-primary {
  background: var(--accent-green);
  color: var(--primary-dark);
}

.btn-secondary {
  background: var(--primary-light);
  color: var(--text-color);
}

.btn-success {
  background: #28a745;
  color: white;
}

.btn-info {
  background: #17a2b8;
  color: white;
}

.btn-danger {
  background: #ff4343;
  color: white;
}

.btn:hover:not(:disabled) {
  transform: translateY(-2px);
}

.btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.btn-sm {
  padding: 0.5rem 1rem;
  font-size: 0.875rem;
}

.btn-xs {
  padding: 0.25rem 0.5rem;
  font-size: 0.75rem;
}

.form-control, .form-control-sm {
  width: 100%;
  padding: 0.75rem;
  background: var(--secondary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 4px;
  color: var(--text-color);
  font-size: 1rem;
}

.form-control-sm {
  padding: 0.375rem 0.5rem;
  font-size: 0.875rem;
}

.form-control:focus, .form-control-sm:focus {
  outline: none;
  border-color: var(--accent-green);
  box-shadow: 0 0 0 2px rgba(0, 255, 146, 0.2);
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-content {
  background: var(--secondary-dark);
  border: 1px solid var(--primary-light);
  border-radius: 8px;
  width: 90%;
  max-width: 600px;
  max-height: 90vh;
  overflow-y: auto;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1rem;
  border-bottom: 1px solid var(--primary-light);
}

.modal-header h3 {
  margin: 0;
  color: var(--accent-green);
}

.modal-body {
  padding: 1.5rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
  padding: 1rem;
  border-top: 1px solid var(--primary-light);
}

.upload-area {
  border: 2px dashed var(--primary-light);
  border-radius: 8px;
  padding: 3rem 1rem;
  text-align: center;
  transition: border-color 0.3s ease;
  margin-bottom: 1.5rem;
}

.upload-area:hover {
  border-color: var(--accent-green);
}

.upload-content {
  position: relative;
}

.upload-icon {
  font-size: 3rem;
  margin-bottom: 1rem;
}

.file-input {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  opacity: 0;
  cursor: pointer;
}

.upload-preview {
  background: var(--primary-dark);
  padding: 1rem;
  border-radius: 8px;
  margin-bottom: 1.5rem;
}

.upload-preview h4 {
  margin: 0 0 1rem 0;
  color: var(--accent-green);
}

.file-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.file-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
  background: var(--secondary-dark);
  border-radius: 4px;
  font-size: 0.875rem;
}

.upload-options {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.form-group label {
  color: var(--text-color);
  font-weight: 500;
}

.alert {
  padding: 1rem;
  border-radius: 4px;
  margin-top: 2rem;
}

.alert-success {
  background: rgba(0, 255, 146, 0.1);
  border: 1px solid var(--accent-green);
  color: var(--accent-green);
}

.alert-danger {
  background: rgba(255, 67, 67, 0.1);
  border: 1px solid #ff4343;
  color: #ff4343;
}

@media (max-width: 768px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  
  .training-tabs {
    flex-direction: column;
  }
  
  .tab-button {
    padding: 0.75rem 1rem;
    text-align: left;
  }
  
  .dataset-categories, .format-grid {
    grid-template-columns: 1fr;
  }
  
  .image-gallery {
    grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  }
  
  .batch-actions {
    flex-direction: column;
    align-items: stretch;
  }
  
  .export-header, .training-header {
    flex-direction: column;
    gap: 1rem;
    align-items: stretch;
  }
  
  .export-details, .training-details {
    flex-direction: column;
    gap: 0.5rem;
  }
  
  .config-grid, .options-grid {
    grid-template-columns: 1fr;
  }
  
  .training-metrics {
    grid-template-columns: 1fr;
  }
}
</style>