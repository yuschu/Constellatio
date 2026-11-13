/* 首页面板切换（v2.1.0）
 *
 * 行为取自 DSH dsh-client-ui-sidebar/SidebarRoot 的 panel 行：
 *   PanelRow 点一下 → selectPanel(id) → 主区换成该 panel 的内容，侧栏原地不动、
 *   该行落 .panelActive（背景 = interactive-bg-hover，文字仍是 label-primary）。
 *   DSH 的 panel 切换本身不带过场动画（web-frontend CSS 里没有对应 keyframes，
 *   只有侧栏收起的 wide-in / rail-in），所以这里也不做淡入淡出，直接换。
 *
 * 本站是多页 Django：主区内容由 `/?panel=…` 服务端渲染，点击时 fetch 整页、
 * 只取 [data-panel-body] 那一块替换，再 pushState —— 于是地址栏、刷新、
 * 深链、无 JS 都与「整页导航」等价。fetch 失败就退回普通跳转，绝不白屏。
 */
(function () {
  'use strict';

  var body = document.querySelector('[data-panel-body]');
  if (!body) { return; }

  /** 把新片段里的 <script> 重新执行一遍（innerHTML 不会执行脚本）。 */
  function runScripts(root) {
    var scripts = root.querySelectorAll('script');
    Array.prototype.forEach.call(scripts, function (old) {
      var script = document.createElement('script');
      Array.prototype.forEach.call(old.attributes, function (attr) {
        script.setAttribute(attr.name, attr.value);
      });
      script.text = old.text;
      old.parentNode.replaceChild(script, old);
    });
  }

  /** 主题样式表按面板态挂/摘：对话态不加载主题表，避免影响首页自身观感。 */
  function syncThemeCss(doc) {
    var incoming = doc.querySelector('link[data-panel-theme]');
    var current = document.querySelector('link[data-panel-theme]');
    if (incoming && !current) {
      var link = document.createElement('link');
      link.rel = 'stylesheet';
      link.href = incoming.getAttribute('href');
      link.setAttribute('data-panel-theme', '');
      document.head.appendChild(link);
    } else if (!incoming && current) {
      current.parentNode.removeChild(current);
    }
  }

  function setSidebarActive(key) {
    var rows = document.querySelectorAll('[data-home-panel]');
    Array.prototype.forEach.call(rows, function (row) {
      var on = row.getAttribute('data-home-panel') === key;
      row.classList.toggle('is-active', on);
      if (on) { row.setAttribute('aria-current', 'page'); }
      else { row.removeAttribute('aria-current'); }
    });
  }

  function render(doc, url) {
    var incoming = doc.querySelector('[data-panel-body]');
    var main = body.parentNode;
    body.className = incoming.className;
    body.innerHTML = incoming.innerHTML;
    body.setAttribute('data-active-panel', incoming.getAttribute('data-active-panel') || 'chat');
    runScripts(body);
    syncThemeCss(doc);
    main.classList.toggle('as-main--panel', body.getAttribute('data-active-panel') !== 'chat');
    setSidebarActive(body.getAttribute('data-active-panel'));
    document.title = doc.title;
    var scroll = body.querySelector('[data-panel-scroll]');
    if (scroll) { scroll.scrollTop = 0; }
    if (url && url !== window.location.href) {
      window.history.pushState({ panel: body.getAttribute('data-active-panel') }, '', url);
    }
  }

  function load(url) {
    return fetch(url, {
      credentials: 'same-origin',
      headers: { 'X-Requested-With': 'fetch' }
    }).then(function (res) {
      if (!res.ok) { throw new Error('HTTP ' + res.status); }
      return res.text();
    }).then(function (html) {
      var doc = new DOMParser().parseFromString(html, 'text/html');
      if (!doc.querySelector('[data-panel-body]')) { throw new Error('no panel'); }
      render(doc, url);
    }).catch(function () {
      window.location.href = url;
    });
  }

  document.addEventListener('click', function (event) {
    if (event.defaultPrevented || event.button !== 0) { return; }
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) { return; }
    var link = event.target.closest('[data-home-panel]');
    if (link) {
      var key = link.getAttribute('data-home-panel');
      if (key === body.getAttribute('data-active-panel')) {
        event.preventDefault();
        return;
      }
      event.preventDefault();
      load(link.getAttribute('href'));
      return;
    }
    /* 二级页进出（v2.1.2）：面板里的「考勤规则」与二级页的 crumb 返回都带
       data-panel-link —— 同样是换 [data-panel-body] + pushState，
       于是面板内导航不进整页、侧栏不动、浏览器返回键可回上一级。 */
    var subLink = event.target.closest('[data-panel-link]');
    if (!subLink) { return; }
    event.preventDefault();
    load(subLink.getAttribute('href'));
  });

  window.addEventListener('popstate', function () {
    load(window.location.pathname + window.location.search);
  });
})();
