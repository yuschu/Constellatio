/* 首帧还原侧栏收起态（避免冷导航先画 280 再跳到 56）。
 *
 * ds-shell.js 是 defer 脚本，最早也要等 HTML 解析完才执行，可能晚于首帧绘制；
 * 这里在 <head> 里同步读同一个键（sessionStorage['constellatio.rail-collapsed']），
 * 先把属性落到 <html> 上，收起态的样式在第一次绘制前就是对的，后续交互仍由 ds-shell 接管。
 */
(function () {
  'use strict';
  try {
    if (window.sessionStorage.getItem('constellatio.rail-collapsed') === '1') {
      var root = document.documentElement;
      root.setAttribute('data-rail-collapsed', 'true');
      root.setAttribute('data-rail-settled', 'true');
    }
  } catch (e) {
    /* 隐私模式 / 禁用存储：按展开态渲染，不改任何属性 */
  }
})();
