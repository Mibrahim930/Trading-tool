// Scroll-driven polish: navbar depth, section reveals, clickable rows, animated
// counters, and data-driven Chart.js rendering for the journal story + stat pages.

(function () {
  const topbar = document.querySelector(".topbar");
  const setScrolled = () => {
    if (!topbar) return;
    topbar.classList.toggle("scrolled", window.scrollY > 4);
  };
  setScrolled();
  window.addEventListener("scroll", setScrolled, { passive: true });

  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- Plain fade/rise reveal ----------
  const revealEls = document.querySelectorAll(".reveal");
  if (revealEls.length) {
    if (!("IntersectionObserver" in window) || reducedMotion) {
      revealEls.forEach((el) => el.classList.add("reveal-visible"));
    } else {
      // threshold: 0 (not a fraction like 0.08) because tall elements such as a
      // 100-row table would never reach an 8%-visible ratio even filling the viewport.
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              entry.target.classList.add("reveal-visible");
              observer.unobserve(entry.target);
            }
          });
        },
        { threshold: 0 }
      );
      revealEls.forEach((el) => observer.observe(el));
    }
  }

  // ---------- Apple-style scale/fade reveal for full-height story sections ----------
  const scaleEls = document.querySelectorAll(".reveal-scale");
  if (scaleEls.length) {
    if (!("IntersectionObserver" in window) || reducedMotion) {
      scaleEls.forEach((el) => el.classList.add("reveal-scale-visible"));
    } else {
      const scaleObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            entry.target.classList.toggle("reveal-scale-visible", entry.isIntersecting);
          });
        },
        { threshold: 0.35 }
      );
      scaleEls.forEach((el) => scaleObserver.observe(el));
    }
  }

  // ---------- Scroll-linked zoom for journal stat cards ----------
  // Mirrors the CSS `story-zoom` keyframes for browsers without scroll timelines:
  // 0 = card centered in the viewport (full size), 1 = fully off-screen.
  const zoomEls = document.querySelectorAll(".story-zoom");
  const hasScrollTimeline = window.CSS && CSS.supports && CSS.supports("animation-timeline: view()");
  if (zoomEls.length && !reducedMotion && !hasScrollTimeline) {
    let ticking = false;
    const update = () => {
      ticking = false;
      const vh = window.innerHeight;
      zoomEls.forEach((el) => {
        const r = el.getBoundingClientRect();
        const center = r.top + r.height / 2;
        const span = vh / 2 + r.height / 2;
        // Flat plateau near the middle matches the 40%-60% hold in the keyframes.
        const raw = Math.min(1, Math.abs(center - vh / 2) / span);
        const d = Math.max(0, (raw - 0.2) / 0.8);
        const eased = d * d;
        el.style.scale = String(1 - 0.16 * eased);
        el.style.opacity = String(1 - 0.82 * eased);
      });
    };
    const request = () => {
      if (!ticking) { ticking = true; requestAnimationFrame(update); }
    };
    window.addEventListener("scroll", request, { passive: true });
    window.addEventListener("resize", request);
    update();
  } else if (zoomEls.length && reducedMotion) {
    zoomEls.forEach((el) => { el.style.scale = "1"; el.style.opacity = "1"; });
  }

  // ---------- Clickable table rows (dashboard / search -> news detail) ----------
  document.querySelectorAll("tr.clickable-row[data-href]").forEach((row) => {
    const go = () => { window.location.href = row.dataset.href; };
    row.addEventListener("click", go);
    row.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); go(); }
    });
  });

  // ---------- Animated number counters ----------
  const counters = document.querySelectorAll("[data-count]");
  if (counters.length) {
    const animateCounter = (el) => {
      const target = parseFloat(el.dataset.count);
      const decimals = parseInt(el.dataset.decimals || "0", 10);
      const prefix = el.dataset.prefix || "";
      const suffix = el.dataset.suffix || "";
      const format = (value) => {
        const negative = value < 0;
        const abs = Math.abs(value).toFixed(decimals);
        return (negative ? "-" : "") + prefix + abs + suffix;
      };
      if (reducedMotion || !isFinite(target)) {
        el.textContent = format(target);
        return;
      }
      const duration = 900;
      const start = performance.now();
      const from = 0;
      const step = (now) => {
        // rAF's timestamp can precede performance.now() from the scheduling call,
        // so clamp at 0 too or the first frame overshoots negative.
        const t = Math.min(1, Math.max(0, (now - start) / duration));
        const eased = 1 - Math.pow(1 - t, 3);
        const value = from + (target - from) * eased;
        el.textContent = format(value);
        if (t < 1) requestAnimationFrame(step);
      };
      requestAnimationFrame(step);
    };

    if (!("IntersectionObserver" in window)) {
      counters.forEach(animateCounter);
    } else {
      const counterObserver = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              animateCounter(entry.target);
              counterObserver.unobserve(entry.target);
            }
          });
        },
        { threshold: 0.6 }
      );
      counters.forEach((el) => counterObserver.observe(el));
    }
  }

  // ---------- Chart color helpers ----------
  const root = getComputedStyle(document.documentElement);
  const cssVar = (name) => root.getPropertyValue(name).trim();
  const COLORS = {
    accent: cssVar("--accent") || "#0a84ff",
    bull: cssVar("--bull") || "#32d74b",
    bear: cssVar("--bear") || "#ff453a",
    low: cssVar("--low") || "#86898f",
  };
  const gridColor = "rgba(255,255,255,0.06)";
  const textColor = COLORS.low;

  function bootstrapChartDefaults() {
    if (typeof Chart === "undefined") return false;
    Chart.defaults.color = textColor;
    Chart.defaults.borderColor = gridColor;
    Chart.defaults.font.family = "Inter, -apple-system, sans-serif";
    Chart.defaults.font.size = 11;
    return true;
  }

  function buildChartConfig(chart, { minimal }) {
    const ds = chart.datasets[0];
    let backgroundColor;
    let borderColor;
    if (ds.colorByValue) {
      backgroundColor = ds.data.map((v) => (v >= 0 ? COLORS.bull : COLORS.bear));
      borderColor = backgroundColor;
    } else if (ds.colors) {
      backgroundColor = ds.colors.map((c) => COLORS[c] || c);
      borderColor = backgroundColor;
    } else {
      const c = COLORS[ds.color] || ds.color || COLORS.accent;
      backgroundColor = chart.type === "line" ? hexToRgba(c, 0.12) : c;
      borderColor = c;
    }

    const dataset = {
      data: ds.data,
      backgroundColor,
      borderColor,
      borderWidth: chart.type === "line" ? 2 : 0,
      borderRadius: chart.type === "bar" ? 3 : 0,
      pointRadius: 0,
      fill: !!ds.fill,
      tension: 0.3,
    };

    return {
      type: chart.type,
      data: { labels: chart.labels, datasets: [dataset] },
      options: {
        maintainAspectRatio: !minimal,
        // Mini charts render the moment they scroll into view, so a short draw-in
        // reads as part of the scroll choreography rather than a page-load flash.
        animation: minimal ? { duration: 1100, easing: "easeOutQuart" } : undefined,
        plugins: { legend: { display: false } },
        scales: chart.type === "doughnut" ? {} : {
          x: { display: !minimal, grid: { display: false }, ticks: { maxTicksLimit: 8 } },
          y: { display: !minimal, grid: { color: gridColor } },
        },
        interaction: { intersect: false },
      },
    };
  }

  function hexToRgba(hex, alpha) {
    const h = hex.replace("#", "");
    const bigint = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
    const r = (bigint >> 16) & 255, g = (bigint >> 8) & 255, b = bigint & 255;
    return `rgba(${r},${g},${b},${alpha})`;
  }

  // ---------- Stat detail page: render each configured chart ----------
  if (window.__statDetail && window.__statDetail.charts) {
    const render = () => {
      if (!bootstrapChartDefaults()) return;
      window.__statDetail.charts.forEach((chart) => {
        const canvas = document.getElementById("chart-" + chart.id);
        if (!canvas) return;
        new Chart(canvas, buildChartConfig(chart, { minimal: false }));
      });
    };
    render();
  }

  // ---------- Journal story page: mini sparkline charts per stat section ----------
  if (window.__journalStats) {
    const s = window.__journalStats;
    const miniCharts = {
      "balance-curve": {
        type: "line",
        labels: s.equity_curve.map((_, i) => i),
        datasets: [{ data: s.equity_curve.map((p) => p.equity), color: "accent", fill: true }],
      },
      "pnl-equity": {
        type: "line",
        labels: s.equity_curve.map((_, i) => i),
        datasets: [{ data: s.equity_curve.map((p) => p.equity), color: "accent", fill: true }],
      },
      "winrate-bars": {
        type: "bar",
        labels: ["Wins", "Losses"],
        datasets: [{ data: [s.wins, s.losses], colors: ["bull", "bear"] }],
      },
      "trades-symbol": {
        type: "bar",
        labels: Object.keys(s.by_symbol || {}),
        datasets: [{ data: Object.values(s.by_symbol || {}).map((v) => v.pnl), colorByValue: true }],
      },
      "days-daily": {
        type: "bar",
        labels: s.daily_pnl.map((d) => d.date),
        datasets: [{ data: s.daily_pnl.map((d) => d.pnl), colorByValue: true }],
      },
      "avgtrade-bars": {
        type: "bar",
        labels: ["Avg Win", "Avg Loss"],
        datasets: [{ data: [s.avg_win, s.avg_loss], colorByValue: true }],
      },
      "streak-bars": {
        type: "bar",
        labels: s.streak_series.map((_, i) => i),
        datasets: [{ data: s.streak_series.map((p) => p.streak), colorByValue: true }],
      },
    };

    const renderedMini = new Set();
    const canvases = document.querySelectorAll("canvas.mini-chart[data-chart-key]");
    const renderMini = (canvas) => {
      const key = canvas.dataset.chartKey;
      if (renderedMini.has(key) || !miniCharts[key]) return;
      if (!bootstrapChartDefaults()) return;
      renderedMini.add(key);
      new Chart(canvas, buildChartConfig(miniCharts[key], { minimal: true }));
    };

    if (canvases.length) {
      if (!("IntersectionObserver" in window)) {
        canvases.forEach(renderMini);
      } else {
        const miniObserver = new IntersectionObserver(
          (entries) => {
            entries.forEach((entry) => {
              if (entry.isIntersecting) {
                renderMini(entry.target);
                miniObserver.unobserve(entry.target);
              }
            });
          },
          { threshold: 0.2 }
        );
        canvases.forEach((c) => miniObserver.observe(c));
      }
    }

    // Full overview charts at the bottom of the story
    const equityCanvas = document.getElementById("equityChart");
    const dailyCanvas = document.getElementById("dailyPnlChart");
    if (equityCanvas || dailyCanvas) {
      const renderOverview = () => {
        if (!bootstrapChartDefaults()) return;
        if (equityCanvas) {
          new Chart(equityCanvas, buildChartConfig({
            type: "line",
            labels: s.equity_curve.map((p) => new Date(p.time * 1000).toLocaleDateString()),
            datasets: [{ data: s.equity_curve.map((p) => p.equity), color: "accent", fill: true }],
          }, { minimal: false }));
        }
        if (dailyCanvas) {
          new Chart(dailyCanvas, buildChartConfig({
            type: "bar",
            labels: s.daily_pnl.map((d) => d.date),
            datasets: [{ data: s.daily_pnl.map((d) => d.pnl), colorByValue: true }],
          }, { minimal: false }));
        }
      };
      renderOverview();
    }
  }
})();
