<script setup lang="ts">
</script>

<template>
  <div id="app-root">
    <header class="app-header">
      <div class="header-content">
        <router-link to="/" class="brand">
          <div class="brand-dot"></div>
          <div class="brand-text">
            <h1 class="app-title">Agent AI</h1>
            <p class="app-subtitle">Swarm Intelligence Simulation Platform</p>
          </div>
        </router-link>
        <nav class="header-nav">
          <router-link to="/" class="nav-link" active-class="active">
            シミュレーション
          </router-link>
        </nav>
      </div>
    </header>
    <main class="app-main">
      <router-view v-slot="{ Component, route }">
        <component :is="Component" :key="route.fullPath" />
      </router-view>
    </main>
  </div>
</template>

<style scoped>
.app-header {
  background: var(--bg-secondary);
  border-bottom: 1px solid var(--border);
  padding-inline: var(--page-padding);
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-content {
  max-width: var(--page-max-width);
  margin: 0 auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 60px;
  gap: 1rem;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  text-decoration: none;
  color: var(--text-primary);
  min-width: 0;
}

.brand-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--accent);
  flex-shrink: 0;
}

.app-title {
  font-size: 1.1rem;
  font-weight: 700;
  letter-spacing: -0.03em;
  line-height: 1.2;
}

.app-subtitle {
  font-family: var(--font-mono);
  font-size: 0.65rem;
  color: var(--text-muted);
  letter-spacing: 0.05em;
  text-transform: uppercase;
}

.header-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  justify-content: flex-end;
}

.nav-link {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding: 0.4rem 0.8rem;
  border-radius: var(--radius-sm);
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-secondary);
  text-decoration: none;
  transition: all 0.2s;
}

.nav-link:hover {
  color: var(--text-primary);
  background: rgba(255, 255, 255, 0.04);
}

.nav-link.active {
  color: var(--accent);
  background: var(--accent-subtle);
}

.app-main {
  max-width: var(--page-max-width);
  margin: 0 auto;
  padding: clamp(1rem, 1.4vw + 0.5rem, 1.5rem) var(--page-padding) 3rem;
}

@media (max-width: 900px) {
  .app-title {
    font-size: 1rem;
  }

  .app-subtitle {
    font-size: 0.6rem;
  }
}

@media (max-width: 640px) {
  .app-header {
    position: static;
  }

  .header-content {
    min-height: auto;
    flex-direction: column;
    align-items: flex-start;
    padding-block: 0.85rem;
    gap: 0.75rem;
  }

  .brand {
    width: 100%;
  }

  .brand-text {
    min-width: 0;
  }

  .app-subtitle {
    white-space: normal;
    line-height: 1.4;
  }

  .header-nav {
    width: 100%;
    justify-content: flex-start;
  }

  .nav-link {
    width: 100%;
    justify-content: center;
  }

  .app-main {
    padding-top: 1rem;
    padding-bottom: 2rem;
  }
}
</style>
