import { ref } from 'vue'

const toasts = ref([])
let seq = 0

export function pushToast(message, type = 'info', timeout = 3200) {
  const id = ++seq
  toasts.value.push({ id, message, type })
  if (timeout) setTimeout(() => dismissToast(id), timeout)
  return id
}

export function dismissToast(id) {
  toasts.value = toasts.value.filter((t) => t.id !== id)
}

export function useToasts() {
  return { toasts, pushToast, dismissToast }
}
