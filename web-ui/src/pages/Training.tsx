import React, { useState, useCallback } from 'react'
import { Box, Card, CardContent, Typography, Grid, Button, ImageList, ImageListItem, ImageListItemBar, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Chip, LinearProgress, Alert } from '@mui/material'
import { CloudUpload as UploadIcon, Delete as DeleteIcon, Label as LabelIcon, Download as DownloadIcon, SmartToy as ModelIcon } from '@mui/icons-material'
import { useDropzone } from 'react-dropzone'
import { TrainingImage } from '../types'

const Training: React.FC = () => {
  const [images, setImages] = useState<TrainingImage[]>([])
  const [selectedImage, setSelectedImage] = useState<TrainingImage | null>(null)
  const [labelDialog, setLabelDialog] = useState(false)
  const [newLabel, setNewLabel] = useState('')
  const [uploadProgress, setUploadProgress] = useState(0)
  const [isUploading, setIsUploading] = useState(false)
  const [trainingProgress, setTrainingProgress] = useState(0)
  const [isTraining, setIsTraining] = useState(false)

  const onDrop = useCallback((acceptedFiles: File[]) => {
    setIsUploading(true)
    setUploadProgress(0)

    // Simulate upload process
    const uploadPromises = acceptedFiles.map((file, index) => {
      return new Promise<TrainingImage>((resolve) => {
        const reader = new FileReader()
        reader.onload = () => {
          const newImage: TrainingImage = {
            id: Date.now().toString() + index,
            filename: file.name,
            timestamp: Date.now(),
            labels: [],
            processed: false
          }
          
          // Simulate upload delay
          setTimeout(() => {
            setUploadProgress((prev) => prev + (100 / acceptedFiles.length))
            resolve(newImage)
          }, 500)
        }
        reader.readAsDataURL(file)
      })
    })

    Promise.all(uploadPromises).then((newImages) => {
      setImages(prev => [...prev, ...newImages])
      setIsUploading(false)
      setUploadProgress(0)
    })
  }, [])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.jpeg', '.jpg', '.png', '.webp']
    },
    multiple: true
  })

  const handleDeleteImage = (imageId: string) => {
    setImages(prev => prev.filter(img => img.id !== imageId))
  }

  const handleLabelImage = (image: TrainingImage) => {
    setSelectedImage(image)
    setLabelDialog(true)
  }

  const handleAddLabel = () => {
    if (!selectedImage || !newLabel.trim()) return

    const updatedImage = {
      ...selectedImage,
      labels: [
        ...selectedImage.labels,
        {
          id: Date.now().toString(),
          name: newLabel.trim(),
          bbox: { x: 0, y: 0, width: 100, height: 100 }, // Simplified for demo
          confidence: 1.0
        }
      ]
    }

    setImages(prev => prev.map(img => 
      img.id === selectedImage.id ? updatedImage : img
    ))

    setNewLabel('')
    setLabelDialog(false)
    setSelectedImage(null)
  }

  const handleStartTraining = () => {
    setIsTraining(true)
    setTrainingProgress(0)

    // Simulate training process
    const interval = setInterval(() => {
      setTrainingProgress(prev => {
        if (prev >= 100) {
          clearInterval(interval)
          setIsTraining(false)
          return 100
        }
        return prev + Math.random() * 10
      })
    }, 1000)
  }

  const handleExportData = () => {
    const dataStr = JSON.stringify(images, null, 2)
    const dataUri = 'data:application/json;charset=utf-8,'+ encodeURIComponent(dataStr)
    
    const exportFileDefaultName = `training_data_${new Date().toISOString().split('T')[0]}.json`
    
    const linkElement = document.createElement('a')
    linkElement.setAttribute('href', dataUri)
    linkElement.setAttribute('download', exportFileDefaultName)
    linkElement.click()
  }

  const labeledImages = images.filter(img => img.labels.length > 0)
  const unlabeledImages = images.filter(img => img.labels.length === 0)

  return (
    <Box sx={{ height: '100%', overflow: 'auto' }}>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={3}>
        <Typography variant="h4">AI Training</Typography>
        <Box display="flex" gap={2}>
          <Button
            variant="outlined"
            startIcon={<DownloadIcon />}
            onClick={handleExportData}
            disabled={images.length === 0}
          >
            Export Data
          </Button>
          <Button
            variant="contained"
            startIcon={<ModelIcon />}
            onClick={handleStartTraining}
            disabled={labeledImages.length < 10 || isTraining}
            color="secondary"
          >
            {isTraining ? 'Training...' : 'Start Training'}
          </Button>
        </Box>
      </Box>

      {isTraining && (
        <Alert severity="info" sx={{ mb: 2 }}>
          <Box sx={{ width: '100%' }}>
            <Typography variant="body2" gutterBottom>
              Training in progress... {trainingProgress.toFixed(0)}%
            </Typography>
            <LinearProgress variant="determinate" value={trainingProgress} />
          </Box>
        </Alert>
      )}

      <Grid container spacing={3}>
        {/* Upload Area */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Box
                {...getRootProps()}
                sx={{
                  border: '2px dashed',
                  borderColor: isDragActive ? 'primary.main' : 'grey.300',
                  borderRadius: 2,
                  p: 4,
                  textAlign: 'center',
                  cursor: 'pointer',
                  backgroundColor: isDragActive ? 'primary.light' : 'transparent',
                  '&:hover': {
                    backgroundColor: 'grey.50',
                    borderColor: 'primary.main'
                  }
                }}
              >
                <input {...getInputProps()} />
                <UploadIcon sx={{ fontSize: 48, color: 'primary.main', mb: 2 }} />
                <Typography variant="h6" gutterBottom>
                  {isDragActive ? 'Drop images here' : 'Drag & drop images or click to select'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Supported formats: JPEG, PNG, WebP
                </Typography>
                
                {isUploading && (
                  <Box sx={{ mt: 2, width: '50%', mx: 'auto' }}>
                    <LinearProgress variant="determinate" value={uploadProgress} />
                    <Typography variant="caption" color="text.secondary">
                      Uploading... {uploadProgress.toFixed(0)}%
                    </Typography>
                  </Box>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Statistics */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Statistics</Typography>
              <Box display="flex" flexDirection="column" gap={1}>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Total Images:</Typography>
                  <Typography variant="body2" fontWeight="bold">{images.length}</Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Labeled:</Typography>
                  <Typography variant="body2" fontWeight="bold" sx={(theme) => ({ color: theme.palette.success.main })}>
                    {labeledImages.length}
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Unlabeled:</Typography>
                  <Typography variant="body2" fontWeight="bold" sx={(theme) => ({ color: theme.palette.warning.main })}>
                    {unlabeledImages.length}
                  </Typography>
                </Box>
                <Box display="flex" justifyContent="space-between">
                  <Typography variant="body2">Total Labels:</Typography>
                  <Typography variant="body2" fontWeight="bold">
                    {images.reduce((sum, img) => sum + img.labels.length, 0)}
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Training Status */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Training Status</Typography>
              <Box display="flex" flexDirection="column" gap={1}>
                <Typography variant="body2" color="text.secondary">
                  Ready to train: {labeledImages.length >= 10 ? 'Yes' : 'No'}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Minimum images needed: 10
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  Recommended: 100+ images per class
                </Typography>
                {labeledImages.length < 10 && (
                  <Alert severity="warning" sx={{ mt: 1 }}>
                    Need {10 - labeledImages.length} more labeled images to start training
                  </Alert>
                )}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Common Labels */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>Common Labels</Typography>
              <Box display="flex" flexWrap="wrap" gap={1}>
                {['person', 'pet', 'toy', 'furniture', 'tree', 'rock', 'hose', 'sprinkler'].map(label => (
                  <Chip 
                    key={label} 
                    label={label} 
                    size="small" 
                    onClick={() => setNewLabel(label)}
                    sx={{ cursor: 'pointer' }}
                  />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Image Gallery */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Image Gallery ({images.length} images)
              </Typography>
              
              {images.length === 0 ? (
                <Box textAlign="center" py={4}>
                  <Typography variant="body2" color="text.secondary">
                    No images uploaded yet. Drag and drop images above to get started.
                  </Typography>
                </Box>
              ) : (
                <ImageList variant="masonry" cols={4} gap={8}>
                  {images.map((image) => (
                    <ImageListItem key={image.id}>
                      <div
                        style={{
                          width: '100%',
                          height: 200,
                          backgroundColor: '#f0f0f0',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          borderRadius: 8
                        }}
                      >
                        <Typography variant="caption" color="text.secondary">
                          {image.filename}
                        </Typography>
                      </div>
                      <ImageListItemBar
                        title={
                          <Box display="flex" alignItems="center" gap={1}>
                            <Typography variant="caption">
                              {image.filename}
                            </Typography>
                            {image.labels.length > 0 && (
                              <Chip 
                                label={`${image.labels.length} labels`}
                                size="small"
                                color="success"
                              />
                            )}
                          </Box>
                        }
                        actionIcon={
                          <Box>
                            <Button
                              size="small"
                              startIcon={<LabelIcon />}
                              onClick={() => handleLabelImage(image)}
                              sx={{ mr: 1, color: 'white' }}
                            >
                              Label
                            </Button>
                            <Button
                              size="small"
                              startIcon={<DeleteIcon />}
                              onClick={() => handleDeleteImage(image.id)}
                              sx={{ color: 'white' }}
                            >
                              Delete
                            </Button>
                          </Box>
                        }
                      />
                    </ImageListItem>
                  ))}
                </ImageList>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Label Dialog */}
      <Dialog open={labelDialog} onClose={() => setLabelDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Add Label</DialogTitle>
        <DialogContent>
          <TextField
            fullWidth
            label="Label Name"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
            placeholder="e.g., person, pet, toy, obstacle"
            margin="normal"
            autoFocus
          />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Enter a descriptive name for the object you want to label in this image.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLabelDialog(false)}>Cancel</Button>
          <Button onClick={handleAddLabel} variant="contained" disabled={!newLabel.trim()}>
            Add Label
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Training
