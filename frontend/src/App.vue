<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="logo">
        <div class="logo-mark">M</div>
        <div>
          <div class="logo-name">MoMo</div>
          <div class="logo-sub">自主安全评估 Agent</div>
        </div>
      </div>
      <nav>
        <router-link to="/dashboard"><span class="icon">▦</span> 总览</router-link>
        <router-link to="/graph"><span class="icon">◉</span> 推理图</router-link>
        <router-link to="/runs"><span class="icon">≋</span> 运行流</router-link>
        <router-link to="/challenges"><span class="icon">▤</span> 题目</router-link>
      </nav>
      <div class="side-foot">
        MoMo · 图搜索 + claude 驱动<br/>
        <span class="muted">TSec Benchmark 跑分框架</span>
      </div>
    </aside>
    <main class="main">
      <router-view />
    </main>
  </div>
</template>
