<template>
  <router-view />
  <div class="toasts">
    <div v-for="t in toasts" :key="t.id" class="toast" :class="t.type" @click="dismissToast(t.id)">
      {{ t.message }}
    </div>
  </div>
</template>

<script setup>
import { useToasts } from '@/composables/useToast'
const { toasts, dismissToast } = useToasts()
</script>

<style scoped>
.toasts {
  position: fixed;
  right: 16px;
  bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 1000;
}
.toast {
  background: #1f2328;
  color: #fff;
  padding: 9px 14px;
  border-radius: 8px;
  font-size: 13px;
  max-width: 360px;
  box-shadow: 0 6px 24px rgba(0, 0, 0, 0.18);
  cursor: pointer;
}
.toast.error { background: #b91c1c; }
.toast.success { background: #047857; }
</style>
