<!-- src/components/control/ControlLockoutGate.vue -->
<template>
  <div class="security-gate">
    <div class="card security-card">
      <div class="card-header"><h3>Control Access Required</h3></div>
      <div class="card-body">
        <div class="security-info">
          <p>Manual control access requires additional authentication based on your security level:</p>
          <div class="security-level">
            <strong>Current Security Level:</strong>
            <span class="level-badge" :class="`level-${authLevel}`">{{ formatLevel(authLevel) }}</span>
          </div>
        </div>
        <div class="auth-methods">
          <div v-if="authLevel === 'password'" class="auth-method">
            <label for="ctl-auth-credential">Confirm Password</label>
            <input id="ctl-auth-credential" v-model="localCredential" type="password"
              class="form-control" placeholder="Enter your password" @keyup.enter="$emit('authenticate')" />
          </div>
          <div v-else-if="authLevel === 'totp'" class="auth-method">
            <label for="ctl-auth-credential">Password</label>
            <input id="ctl-auth-credential" v-model="localCredential" type="password"
              class="form-control" placeholder="Enter your password" @keyup.enter="$emit('authenticate')" />
            <label for="ctl-auth-totp">Enter TOTP Code</label>
            <input id="ctl-auth-totp" v-model="localTotp" type="text"
              class="form-control totp-input" placeholder="000000" maxlength="6" @keyup.enter="$emit('authenticate')" />
          </div>
          <div v-else-if="authLevel === 'google'" class="auth-method">
            <button class="btn btn-google" @click="$emit('google-auth')">Authenticate with Google</button>
          </div>
          <div v-else-if="authLevel === 'cloudflare'" class="auth-method">
            <p>Authentication is handled by Cloudflare Access.</p>
            <button class="btn btn-primary" @click="$emit('cloudflare-verify')">Verify Access</button>
          </div>
        </div>
        <div v-if="authLevel !== 'cloudflare'" class="auth-actions">
          <button class="btn btn-primary" :disabled="authenticating || !canAuthenticate" @click="$emit('authenticate')">
            {{ authenticating ? 'Verifying...' : 'Unlock Control' }}
          </button>
        </div>
        <div v-if="authError" class="alert alert-danger">{{ authError }}</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { AuthLevel } from '@/composables/useControlSession'

const props = defineProps<{
  authLevel: AuthLevel
  authenticating: boolean
  authError: string
  credential: string
  totpCode: string
  canAuthenticate: boolean
}>()

const emit = defineEmits<{
  (e: 'authenticate'): void
  (e: 'google-auth'): void
  (e: 'cloudflare-verify'): void
  (e: 'update:credential', v: string): void
  (e: 'update:totpCode', v: string): void
}>()

const localCredential = computed({
  get: () => props.credential,
  set: (v) => emit('update:credential', v),
})
const localTotp = computed({
  get: () => props.totpCode,
  set: (v) => emit('update:totpCode', v),
})

function formatLevel(level: AuthLevel) {
  switch (level) {
    case 'password': return 'Password'
    case 'totp': return 'Password + TOTP'
    case 'google': return 'Google OAuth'
    case 'cloudflare': return 'Cloudflare Access'
    default: return 'Unknown'
  }
}
</script>
