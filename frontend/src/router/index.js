import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'home', component: () => import('@/views/HomeView.vue') },
  // document path is passed as ?path=relative/file.html
  { path: '/edit', name: 'editor', component: () => import('@/views/EditorView.vue') },
  { path: '/graph', name: 'graph', component: () => import('@/views/GraphView.vue') }
]

export default createRouter({
  history: createWebHistory(),
  routes
})
