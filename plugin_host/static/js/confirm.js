// v1.7.16：把内联 onclick 的确认框改成 data-confirm 统一绑定。
// 为什么必须改：nonce 救不了内联事件（onclick 属于 script-src 的内联执行面），
// 要保住 script-src 不给 'unsafe-inline'，就只能把确认逻辑搬到外部脚本。
//
// 行为判据：① 页面上不再有 onclick；② 点这些按钮仍弹确认框，取消则不发请求。
(function () {
  'use strict';

  function targetOf(event) {
    // 优先用被点击的提交按钮（同一个表单可能有多个 data-confirm 按钮）
    if (event.submitter && event.submitter.hasAttribute &&
        event.submitter.hasAttribute('data-confirm')) {
      return event.submitter;
    }
    return event.target ? event.target.querySelector('[data-confirm]') : null;
  }

  document.addEventListener('submit', function (event) {
    var trigger = targetOf(event);
    if (!trigger) { return; }
    var message = trigger.getAttribute('data-confirm') || '';
    if (message && !window.confirm(message)) {
      event.preventDefault();   // 取消 = 不提交，与原来是同一个效果
    }
  }, true);
})();
