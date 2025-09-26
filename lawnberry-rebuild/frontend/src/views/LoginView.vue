<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <img src="/lawnberry-icon.svg" alt="LawnBerry Pi" class="login-logo" />
        <h1>LawnBerry Pi v2</h1>
        <p>Autonomous Lawn Care System</p>
      </div>
      
      <form @submit.prevent="handleLogin" class="login-form">
        <div class="form-group">
          <label class="form-label" for="username">Username</label>
          <input
            id="username"
            v-model="credentials.username"
            type="text"
            class="form-control"
            :class="{ error: errors.username }"
            required
            :disabled="isLoading"
          />
          <div v-if="errors.username" class="form-error">{{ errors.username }}</div>
        </div>
        
        <div class="form-group">
          <label class="form-label" for="password">Password</label>
          <input
            id="password"
            v-model="credentials.password"
            type="password"
            class="form-control"
            :class="{ error: errors.password }"
            required
            :disabled="isLoading"
          />
          <div v-if="errors.password" class="form-error">{{ errors.password }}</div>
        </div>
        
        <div v-if="authError" class="form-error text-center" role="alert">
          <strong>{{ authError }}</strong>
        </div>
        
        <button
          type="submit"
          class="btn btn-primary w-100"
          :disabled="isLoading"
          :aria-label="isLoading ? 'Signing in, please wait' : 'Sign in to your account'"
        >
          <span v-if="isLoading" class="spinner" aria-hidden="true"></span>
          {{ isLoading ? 'Signing In...' : 'Sign In' }}
        </button>
      </form>
      
      <div class="login-footer">
        <p class="text-muted text-center">
          Default credentials: admin / admin
        </p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import type { LoginCredentials } from '@/types/auth'

const router = useRouter()
const authStore = useAuthStore()

const isLoading = ref(false)
const authError = ref('')

const credentials = reactive<LoginCredentials>({
  username: '',
  password: ''
})

const errors = reactive({
  username: '',
  password: ''
})

const validateForm = () => {
  errors.username = ''
  errors.password = ''
  
  if (!credentials.username.trim()) {
    errors.username = 'Username is required'
  }
  
  if (!credentials.password) {
    errors.password = 'Password is required'
  }
  
  return !errors.username && !errors.password
}

const handleLogin = async () => {
  authError.value = ''
  
  if (!validateForm()) {
    return
  }
  
  try {
    isLoading.value = true
    
    const success = await authStore.login(credentials)
    
    if (success) {
      router.push('/')
    } else {
      authError.value = authStore.error || 'Login failed'
    }
  } catch (error: any) {
    authError.value = error.message || 'Login failed'
  } finally {
    isLoading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 1rem;
}

.login-card {
  background: white;
  border-radius: 12px;
  box-shadow: 0 10px 25px rgba(0, 0, 0, 0.1);
  padding: 2rem;
  width: 100%;
  max-width: 400px;
}

.login-header {
  text-align: center;
  margin-bottom: 2rem;
}

.login-logo {
  height: 64px;
  width: auto;
  margin-bottom: 1rem;
}

.login-header h1 {
  margin-bottom: 0.5rem;
  color: #2c3e50;
}

.login-header p {
  color: #6c757d;
  margin-bottom: 0;
}

.login-form {
  margin-bottom: 1.5rem;
}

.login-footer {
  border-top: 1px solid #e9ecef;
  padding-top: 1rem;
}

.login-footer p {
  margin: 0;
  font-size: 0.875rem;
}

@media (max-width: 480px) {
  .login-card {
    padding: 1.5rem;
  }
  
  .login-header h1 {
    font-size: 1.75rem;
  }
}
</style>