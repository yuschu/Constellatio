/*
 * ECharts Provider 适配器（v1.6 / v1.6.2 / v2.0）
 * - 把容器统一 payload 渲染到目标容器；
 * - v2.0：调色板与文字色改为消费 DSH 语义变量（--ds-state-* / --ds-label-*），
 *   不再用 --r-pink（DSH 下它是"品牌近黑"，会导致序列全黑）；
 * - 主题（Corporate Clean / Risograph 统一为 DSH）自动适配，深浅由
 *   <html data-color-mode> 决定，页面重新加载后按新 mode 重新注册；
 * - payload.link 绑定点击跳转；payload.alert 用告警色覆盖首序列；
 * - 契约：window.oaChartRender(el, payload) -> ECharts 实例（失败返回 null）。
 */
(function () {
  'use strict';

  var THEME_NAME = 'oa';
  var themeRegistered = false;

  function cssVar(name, fallback) {
    var value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return value || fallback || '';
  }

  function palette() {
    return [
      cssVar('--ds-state-business', '#4176e6'),
      cssVar('--ds-state-success', '#22c55e'),
      cssVar('--ds-state-warn', '#f59e0b'),
      cssVar('--ds-state-done', '#7c3aed'),
      cssVar('--ds-state-error', '#ec1313'),
      cssVar('--ds-label-tertiary', '#81858c'),
    ].filter(function (color) { return !!color; });
  }

  function ensureTheme() {
    if (themeRegistered || !window.echarts) { return; }

    var ink = cssVar('--ds-label-primary', '#0f1115');
    var secondary = cssVar('--ds-label-secondary', ink);
    var tertiary = cssVar('--ds-label-tertiary', ink);
    var surface = cssVar('--ds-bg-layer-2', '#ffffff');
    var hairline = cssVar('--ds-border-l2', '#0000001a');
    var font = cssVar('--ds-font', undefined);

    var axis = {
      axisLine: { lineStyle: { color: hairline } },
      axisTick: { lineStyle: { color: hairline } },
      axisLabel: { color: tertiary, fontFamily: font },
      splitLine: { lineStyle: { color: hairline } },
      splitArea: { show: false },
    };

    window.echarts.registerTheme(THEME_NAME, {
      color: palette(),
      backgroundColor: 'transparent',
      textStyle: { color: ink, fontFamily: font },
      legend: {
        textStyle: { color: secondary, fontFamily: font },
        pageTextStyle: { color: tertiary },
        inactiveColor: tertiary,
      },
      tooltip: {
        backgroundColor: surface,
        borderColor: hairline,
        borderWidth: 0.5,
        textStyle: { color: ink, fontFamily: font },
      },
      categoryAxis: axis,
      valueAxis: axis,
      timeAxis: axis,
      logAxis: axis,
    });
    themeRegistered = true;
  }

  /* 把主题覆盖不到的组件细节补齐（gauge 的进度环与中心数字）。 */
  function applyInk(option) {
    var ink = cssVar('--ds-label-primary', '#0f1115');
    var track = cssVar('--ds-bg-layer-3', '#f5f6f7');
    var accent = cssVar('--ds-state-business', '#4176e6');

    (option.series || []).forEach(function (item) {
      if (!item || item.type !== 'gauge') { return; }
      item.detail = item.detail || {};
      item.detail.color = ink;
      item.axisLine = item.axisLine || {};
      item.axisLine.lineStyle = item.axisLine.lineStyle || {};
      item.axisLine.lineStyle.color = [[1, track]];
      item.progress = item.progress || {};
      item.progress.itemStyle = item.progress.itemStyle || {};
      item.progress.itemStyle.color = accent;
    });
  }

  function applyAlert(option) {
    if (!option) { return; }
    var alertColor = cssVar('--ds-state-error', '#ec1313');
    option.color = [alertColor].concat((option.color || palette()).slice(1));
    (option.series || []).forEach(function (item) {
      if (item && item.type !== 'pie' && item.type !== 'gauge') {
        item.itemStyle = item.itemStyle || {};
        item.itemStyle.color = alertColor;
      }
    });
  }

  function dispose(el) {
    var previous = el && el.__oaChart;
    if (previous && typeof previous.dispose === 'function') {
      previous.dispose();
    }
    if (el) {
      el.__oaChart = null;
    }
  }

  window.oaChartRender = function (el, payload) {
    if (!el || !window.echarts || !payload || !payload.option) {
      return null;
    }
    dispose(el);
    ensureTheme();

    var option = payload.option;
    if (payload.alert) {
      applyAlert(option);
    }
    applyInk(option);

    var chart = window.echarts.init(
      el, themeRegistered ? THEME_NAME : null, { renderer: 'canvas' });
    chart.setOption(option);
    el.__oaChart = chart;

    if (payload.link) {
      chart.on('click', function () {
        window.location.href = payload.link;
      });
    }

    if (window.ResizeObserver) {
      if (!el.__oaChartObserver) {
        el.__oaChartObserver = new ResizeObserver(function () {
          if (el.__oaChart) {
            el.__oaChart.resize();
          }
        });
        el.__oaChartObserver.observe(el);
      }
    } else {
      window.addEventListener('resize', function () {
        if (el.__oaChart) {
          el.__oaChart.resize();
        }
      });
    }
    return chart;
  };
})();
