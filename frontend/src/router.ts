import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    // === 統一ルート ===
    {
      path: '/',
      name: 'launchpad',
      component: () => import('./pages/LaunchPadPage.vue'),
    },
    {
      path: '/sim/:id',
      name: 'simulation',
      component: () => import('./pages/SimulationPage.vue'),
    },
    {
      path: '/sim/:id/results',
      name: 'results',
      component: () => import('./pages/ResultsPage.vue'),
    },
    {
      path: '/populations',
      name: 'populations',
      component: () => import('./pages/PopulationPage.vue'),
    },
    // === レガシーリダイレクト ===
    {
      path: '/run/:id',
      redirect: (to) => `/sim/${to.params.id}`,
    },
    {
      path: '/report/:id',
      redirect: (to) => `/sim/${to.params.id}/results`,
    },
    {
      path: '/swarm',
      redirect: '/',
    },
    {
      path: '/swarm/:id',
      redirect: (to) => `/sim/${to.params.id}`,
    },
    {
      path: '/swarm/:id/result',
      redirect: (to) => `/sim/${to.params.id}/results`,
    },
  ],
})

if (import.meta.env.DEV) {
  router.addRoute({
    path: '/__e2e__/sse',
    name: 'sse-probe',
    component: () => import('./pages/SSEProbePage.vue'),
  })
}

export default router
