import { defineStore } from 'pinia'

export interface Toast {
  id: number
  message: string
  type?: 'success' | 'error' | 'info' | 'warning'
  timeout?: number
}

export const useToastStore = defineStore('toast', {
  state: () => ({
    toasts: [] as Toast[],
    nextId: 1,
  }),
  actions: {
    show(message: string, type: Toast['type']='info', timeout=3000) {
      const id = this.nextId++
      this.toasts.push({ id, message, type, timeout })
      if (timeout && timeout > 0) {
        setTimeout(() => this.dismiss(id), timeout)
      }
      return id
    },
    dismiss(id: number) {
      this.toasts = this.toasts.filter(t => t.id !== id)
    },
    clear() {
      this.toasts = []
    }
  }
})
