/*
 * ECharts Provider 适配器（v1.6 / v1.6.2）：
 * - 把容器统一 payload 渲染到目标容器；
 * - 从主题 CSS 变量（--r-pink / --r-blue / --r-orange / --r-green / --r-ink）注册 ECharts 主题，
 *   两套主题（Corporate Clean / Risograph）自动适配；
 * - payload.link 绑定点击跳转；payload.alert 用告警色覆盖首序列；
 * - 契约：window.oaChartRender(el, payload) -> ECharts 实例（失败返回 null）。
 */
(function () {
  'use strict';

  var THEME_NAME = 'oa';
  var themeRegistered = false;

  function cssVar(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function palette() {
    return [
      cssVar('--r-pink'),
      cssVar('--r-blue'),
      cssVar('--r-orange'),
      cssVar('--r-green'),
      cssVar('--r-ink')
    ].filter(function (color) { return !!color; });
  }

  function ensureTheme() {
    if (themeRegistered || !window.echarts) { return; }
    var colors = palette();
    var ink = cssVar('--r-ink') || '#111827';
    window.echarts.registerTheme(THEME_NAME, {
      color: colors,
      backgroundColor: 'transparent',
      textStyle: { color: ink, fontFamily: cssVar('--r-font') || undefined },
      legend: { textStyle: { color: ink } },
      tooltip: {
        backgroundColor: 'rgba(255, 255, 255, 0.96)',
        borderColor: ink,
        textStyle: { color: ink }
      }
    });
    themeRegistered = true;
  }

  function applyAlert(option) {
    if (!option) { return; }
    var alertColor = cssVar('--r-danger') || cssVar('--r-orange') || '#dc2626';
    option.color = [alertColor].concat((option.color || palette()).slice(1));
    var series = option.series || [];
    series.forEach(function (item) {
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
