// 看板统计范围（今日 / 本周 / 本月）原地切换（v2.1.9）。
//
// 起因：范围链接此前写死成 `/?range=<key>`，于是
//   ① 在业务页 /dashboard/ 点「本周」→ 跳到首页对话面板，看板整个没了；
//   ② 在首页「看板」面板（/?panel=dashboard）里点又会丢掉 panel 参数。
// 后端已改成按当前页生成链接（见 plugin_host/views.py 的 _range_base），
// 这里再补一层：点范围不整页刷新，取回同一页、换掉 `.lc-ov-page` 这一块，
// 再把地址栏换成新 URL。DSH 的看板切换本来就是原地换数据，不闪整页。
//
// 取回的不是看板页（登录过期跳到登录页、或布局变了没有 .lc-ov-page）就整页走，
// 不给用户留一个「点了没反应」的界面。
(function () {
  'use strict';

  var pending = false;

  function activeButton() {
    return document.querySelector('.lc-ov-range .lc-gran-on');
  }

  function swap(html, url, push) {
    var doc = new DOMParser().parseFromString(html, 'text/html');
    var next = doc.querySelector('.lc-ov-page');
    var current = document.querySelector('.lc-ov-page');
    if (!next || !current) {
      window.location.assign(url);
      return false;
    }
    current.replaceWith(document.importNode(next, true));
    document.title = doc.title || document.title;
    if (push && window.history && window.history.pushState) {
      window.history.pushState(null, '', url);
    }
    // 被点的那颗按钮在换完之后变成了 .lc-gran-on 的 span，
    // 把焦点交还给它，键盘用户不会突然掉到页面顶部。
    var on = activeButton();
    if (on && on.focus) {
      on.focus({ preventScroll: true });
    }
    return true;
  }

  function load(url, push) {
    pending = true;
    fetch(url, { credentials: 'same-origin', headers: { 'X-Requested-With': 'fetch' } })
      .then(function (response) {
        if (!response.ok) {
          throw new Error('status ' + response.status);
        }
        return response.text();
      })
      .then(function (html) {
        if (!swap(html, url, push !== false)) {
          return;
        }
        pending = false;
      })
      .catch(function () {
        window.location.assign(url);
      });
  }

  document.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0) {
      return;
    }
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    var target = event.target;
    var link = target && target.closest ? target.closest('.lc-ov-range a') : null;
    if (!link) {
      return;
    }
    var href = link.getAttribute('href');
    if (!href) {
      return;
    }
    event.preventDefault();
    if (pending) {
      return;
    }
    load(new URL(link.href, window.location.href).toString(), true);
  });

  // 浏览器的前进 / 后退：地址栏已经变了，页面还得自己跟上，
  // 否则会出现「URL 是 range=today、画面还是本月」的错位。
  window.addEventListener('popstate', function () {
    load(window.location.href, false);
  });
})();
