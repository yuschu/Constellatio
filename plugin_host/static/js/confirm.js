// v1.7.16：把内联 onclick 的确认框改成 data-confirm 统一绑定。
// 为什么必须改：nonce 救不了内联事件（onclick 属于 script-src 的内联执行面），
// 要保住 script-src 不给 'unsafe-inline'，就只能把确认逻辑搬到外部脚本。
//
// 支持三种写法（历史原因，站内都有）：
//   1) <button type="submit" data-confirm="…">          —— 提交按钮上
//   2) <form data-confirm="…">                          —— 表单上（approval_list 的删除按钮）
//   3) 表单内任意元素带 data-confirm                     —— 兜底
// 行为判据：① 页面上不再有 onclick；② 点这些按钮仍弹确认框，取消则不发请求。
(function () {
  'use strict';

  function attributeOf(node) {
    return node && node.getAttribute ? node.getAttribute('data-confirm') : null;
  }

  function messageFor(event) {
    var form = event.target;
    // ① 被点击的提交按钮（同一个表单可能有多个确认按钮）
    if (event.submitter && attributeOf(event.submitter)) {
      return attributeOf(event.submitter);
    }
    // ② 表单自身（approval_list 的删除表单）
    if (form && form.getAttribute && attributeOf(form)) {
      return attributeOf(form);
    }
    // ③ 表单内任意带 data-confirm 的元素
    var inner = form && form.querySelector ? form.querySelector('[data-confirm]') : null;
    return attributeOf(inner);
  }

  document.addEventListener('submit', function (event) {
    var message = messageFor(event);
    if (message && !window.confirm(message)) {
      event.preventDefault();   // 取消 = 不提交，与原来是同一个效果
    }
  }, true);
})();
