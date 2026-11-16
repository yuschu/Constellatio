/* 首帧还原侧栏状态（避免冷导航先画 280 再跳到 56 / 抽屉）。
 *
 * ds-shell.js 是 defer 脚本，最早也要等 HTML 解析完才执行，可能晚于首帧绘制；
 * 这里在 <head> 里同步读同一个键（sessionStorage['constellatio.rail-collapsed']），
 * 先把属性落到 <html> 上，收起态的样式在第一次绘制前就是对的，后续交互仍由 ds-shell 接管。
 *
 * 窄屏口径对齐 DSH AppFrame：viewport < 1024 自动收窄（narrowExpanded 初始 false），
 * viewport < 768 进入抽屉模式，不继承桌面的展开偏好。
 */
(function () {
  'use strict';
  var root = document.documentElement;
  var width = document.documentElement.clientWidth || window.innerWidth;
  var narrow = width < 1024;
  var drawer = width < 768;

  if (drawer) root.setAttribute('data-sidebar-drawer', 'true');

  try {
    if (narrow || window.sessionStorage.getItem('constellatio.rail-collapsed') === '1') {
      root.setAttribute('data-rail-collapsed', 'true');
      root.setAttribute('data-rail-settled', 'true');
    }
  } catch (e) {
    /* 隐私模式 / 禁用存储：窄屏仍按收起态渲染；宽屏按展开态渲染，不改其余属性 */
    if (narrow) {
      root.setAttribute('data-rail-collapsed', 'true');
      root.setAttribute('data-rail-settled', 'true');
    }
  }
})();
