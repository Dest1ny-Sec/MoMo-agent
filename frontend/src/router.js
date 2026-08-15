import { createRouter, createWebHashHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/dashboard' },
  { path: '/dashboard', name: 'dashboard', component: () => import('./views/DashboardView.vue') },
  { path: '/graph', name: 'graph', component: () => import('./views/GraphView.vue') },
  { path: '/runs', name: 'runs', component: () => import('./views/RunsView.vue') },
  { path: '/challenges', name: 'challenges', component: () => import('./views/ChallengesView.vue') },
]

export default createRouter({
  history: createWebHashHistory(),
  routes,
})
