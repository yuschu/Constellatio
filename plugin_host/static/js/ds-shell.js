/* DSH 外壳交互（v2.0.5，侧栏收起 v2.0.8）
 *
 * 行为与参数取自 dsh 客户端源码，不是像素采样：
 *   侧栏   dsh-client-ui-sidebar/SidebarRoot     —— 收起 = slide + crossfade、settled 150ms 后落 36×36 图标行、
 *          gap 12、轨宽 56（dsh-client-ui-layout collapsedWidth）
 *          dsh-client-ui-layout/toggleSidebar    —— 点击在 sidebar === 0 ? 280 : 0 之间切换，不持久化
 *          dsh-client-ui-settings-general/Trigger —— 设置入口 42px 行，右侧快捷键 hint 悬停显形
 *   设置   dsh-client-ui-settings-general/Panel   —— 800×800 grid（nav 188px）、Esc/遮罩/关闭收起、
 *          关闭后焦点回到触发控件、Web 快捷键 Mod+Alt+,
 *   输入框 dsh-client-ui-conversation/Composer    —— min-height 36（hero 52）、max 336、
 *          Enter 发送 / Shift+Enter 换行 / 输入法组字期间不发送
 */
(function () {
  'use strict';

  var TEXT_MAX = 336;
  /* 侧栏收起时序：宽度过渡 --ds-transition-duration-slow = .3s；落位 COLLAPSE_SETTLE_MS = 150 */
  var RAIL_ANIM_MS = 300;
  var RAIL_SETTLE_MS = 150;
  var RAIL_WIDE_IN_MS = 200;
  /* 收起状态的作用域：DSH 把 layoutInfo.sidebar 存在 SPA 内存里，同一会话内翻页不丢；
     本站是 Django 多页，翻页即重新初始化，因此用 sessionStorage 复刻「同一会话内保持」。
     关闭标签页即清空，也不写 localStorage —— 不跨天、不跨设备。 */
  var RAIL_STORE_KEY = 'constellatio.rail-collapsed';

  function readStoredRail() {
    try { return window.sessionStorage.getItem(RAIL_STORE_KEY) === '1'; }
    catch (e) { return false; }
  }

  function writeStoredRail(collapsed) {
    try { window.sessionStorage.setItem(RAIL_STORE_KEY, collapsed ? '1' : '0'); }
    catch (e) { /* 隐私模式 / 禁用存储：退化为「刷新即展开」 */ }
  }

  // ---------- 侧栏收起（点击切换）----------
  function initRail() {
    var toggle = document.querySelector('[data-ds-rail-toggle]');
    if (!toggle) return;
    var root = document.documentElement;
    var rail = toggle.closest('.ds-rail') || toggle.closest('.as-sidebar');
    var animTimer = null;
    var settleTimer = null;
    var wideTimer = null;

    function isCollapsed() {
      return root.getAttribute('data-rail-collapsed') === 'true';
    }

    function sync(collapsed, animate) {
      window.clearTimeout(animTimer);
      window.clearTimeout(settleTimer);
      window.clearTimeout(wideTimer);

      if (animate) {
        /* 源码口径：[data-animating] 期间才开宽度过渡 */
        root.setAttribute('data-rail-animating', 'true');
        animTimer = window.setTimeout(function () {
          root.removeAttribute('data-rail-animating');
        }, RAIL_ANIM_MS);
      }

      if (collapsed) {
        /* 宽内容原地淡出 150ms（不清空、不 reflow），列宽由父级裁切，落位后才换 36×36 布局 */
        if (animate) root.setAttribute('data-rail-fading', 'true');
        root.setAttribute('data-rail-collapsed', 'true');
        root.removeAttribute('data-rail-wide-in');
        if (animate) {
          settleTimer = window.setTimeout(function () {
            root.removeAttribute('data-rail-fading');
            root.setAttribute('data-rail-settled', 'true');
          }, RAIL_SETTLE_MS);
        } else {
          root.setAttribute('data-rail-settled', 'true');
        }
      } else {
        root.removeAttribute('data-rail-collapsed');
        root.removeAttribute('data-rail-settled');
        root.removeAttribute('data-rail-fading');
        if (animate) {
          /* wide 进场：.hHd-Xa_wide { animation: wide-in .2s } */
          root.setAttribute('data-rail-wide-in', 'true');
          wideTimer = window.setTimeout(function () {
            root.removeAttribute('data-rail-wide-in');
          }, RAIL_WIDE_IN_MS);
        }
      }

      var label = collapsed ? toggle.dataset.labelOpen : toggle.dataset.labelCollapse;
      if (label) toggle.setAttribute('aria-label', label);

      /* 落状态：翻页后新页面初始化时据此复原（否则每次导航都会「自己弹回」展开） */
      writeStoredRail(collapsed);

      if (collapsed) {
        var menu = document.querySelector('[data-ds-account-menu]');
        var trigger = document.querySelector('[data-ds-account-trigger]');
        if (menu && !menu.hasAttribute('hidden')) {
          menu.setAttribute('hidden', '');
          if (trigger) trigger.setAttribute('aria-expanded', 'false');
        }
        /* 焦点若在侧栏内部（如刚关掉的菜单项），回 toggle 且不画焦点环（源码 focusWithoutRing） */
        if (rail && rail.contains(document.activeElement) && document.activeElement !== toggle) {
          toggle.classList.add('is-focus-silent');
          try { toggle.focus({ preventScroll: true }); } catch (e) { toggle.focus(); }
          window.setTimeout(function () { toggle.classList.remove('is-focus-silent'); }, 250);
        }
      }
    }

    /* DSH 的 layoutInfo.sidebar 默认 280，同一会话内由客户端内存保留；
       本站多页，改由 sessionStorage 复原（见 RAIL_STORE_KEY） */
    sync(readStoredRail(), false);

    toggle.addEventListener('click', function () {
      sync(!isCollapsed(), true);
    });

    /* 快捷键：desktop 为 primary+B，Web 口径另加 alt（源码 defaults.web:windows） */
    document.addEventListener('keydown', function (e) {
      if (!e.ctrlKey || !e.altKey || e.shiftKey) return;
      if (e.code !== 'KeyB' && e.key !== 'b' && e.key !== 'B') return;
      e.preventDefault();
      sync(!isCollapsed(), true);
    });
  }

  // ---------- 设置分区切换（通用 / 我的）----------
  function initSettingsTabs(modal) {
    var cells = modal.querySelectorAll('[data-ds-settings-tab]');
    var panels = modal.querySelectorAll('[data-ds-settings-panel]');
    if (cells.length === 0 || panels.length === 0) return;

    function select(name) {
      Array.prototype.forEach.call(cells, function (cell) {
        var on = cell.getAttribute('data-ds-settings-tab') === name;
        cell.classList.toggle('is-active', on);
        if (on) cell.setAttribute('aria-current', 'true');
        else cell.removeAttribute('aria-current');
      });
      Array.prototype.forEach.call(panels, function (panel) {
        if (panel.getAttribute('data-ds-settings-panel') === name) panel.removeAttribute('hidden');
        else panel.setAttribute('hidden', '');
      });
    }

    Array.prototype.forEach.call(cells, function (cell) {
      cell.addEventListener('click', function () {
        select(cell.getAttribute('data-ds-settings-tab'));
      });
    });
  }

  // ---------- 账号菜单（dsh-client-ui-settings-account/AccountMenu）----------
  function initAccount() {
    var root = document.querySelector('[data-ds-account]');
    if (!root) return;
    var trigger = root.querySelector('[data-ds-account-trigger]');
    var menu = root.querySelector('.ds-menu');
    if (!trigger || !menu) return;

    function isOpen() { return !menu.hasAttribute('hidden'); }

    function open() {
      menu.removeAttribute('hidden');
      trigger.setAttribute('aria-expanded', 'true');
      var first = menu.querySelector('[role=menuitem]');
      if (first) first.focus({ preventScroll: true });
    }

    function close(refocus) {
      if (!isOpen()) return;
      menu.setAttribute('hidden', '');
      trigger.setAttribute('aria-expanded', 'false');
      if (refocus) trigger.focus({ preventScroll: true });
    }

    // 菜单自身算「内部」：点菜单项不经过 document 的关闭判断
    menu.addEventListener('mousedown', function (e) { e.stopPropagation(); });

    trigger.addEventListener('click', function (e) {
      e.preventDefault();
      if (isOpen()) close(true); else open();
    });

    document.addEventListener('mousedown', function (e) {
      if (isOpen() && !root.contains(e.target)) close(false);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) {
        e.preventDefault();
        close(true);
      }
    });

    // 点任一项都收起菜单；「设置」随后由 initSettings 打开面板
    Array.prototype.forEach.call(menu.querySelectorAll('[role=menuitem]'), function (item) {
      item.addEventListener('click', function () { close(false); });
    });
  }

  // ---------- 侧栏「更多」 ----------
  // DSH 的 PanelMoreMenu 是 anchor 附近弹出的 portal 菜单（Menu portal=true）；
  // 这里用 fixed 定位做等价实现：优先向上弹，上方不够就翻到下方，并夹在视口内。
  function initMore() {
    var root = document.querySelector('[data-as-more]');
    if (!root) return;
    var trigger = root.querySelector('[data-as-more-trigger]');
    var menu = root.querySelector('.as-more__menu');
    if (!trigger || !menu) return;

    function isOpen() { return !menu.hasAttribute('hidden'); }

    function place() {
      var r = trigger.getBoundingClientRect();
      var vw = document.documentElement.clientWidth;
      var vh = document.documentElement.clientHeight;
      var gap = 4;
      var edge = 8;
      // 先按自然高度量一次，再决定向上还是向下、以及是否需要限高滚动
      menu.style.maxHeight = 'none';
      menu.style.overflowY = '';
      var w = menu.offsetWidth;
      var h = menu.offsetHeight;
      var above = r.top - gap - edge;
      var below = vh - r.bottom - gap - edge;
      var up = above >= below;
      var avail = Math.max(120, up ? above : below);
      if (h > avail) {
        menu.style.maxHeight = Math.round(avail) + 'px';
        menu.style.overflowY = 'auto';
      }
      var top = up ? r.top - gap - Math.min(h, avail) : r.bottom + gap;
      var left = Math.min(Math.max(edge, r.left), Math.max(edge, vw - w - edge));
      menu.style.left = Math.round(left) + 'px';
      menu.style.top = Math.round(top) + 'px';
    }

    function open() {
      menu.removeAttribute('hidden');
      trigger.setAttribute('aria-expanded', 'true');
      place();
      var first = menu.querySelector('[role=menuitem]');
      if (first) first.focus({ preventScroll: true });
    }

    function close(refocus) {
      if (!isOpen()) return;
      menu.setAttribute('hidden', '');
      trigger.setAttribute('aria-expanded', 'false');
      if (refocus) trigger.focus({ preventScroll: true });
    }

    menu.addEventListener('mousedown', function (e) { e.stopPropagation(); });

    trigger.addEventListener('click', function (e) {
      e.preventDefault();
      if (isOpen()) close(true); else open();
    });

    document.addEventListener('mousedown', function (e) {
      if (isOpen() && !root.contains(e.target)) close(false);
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) {
        e.preventDefault();
        close(true);
      }
    });

    Array.prototype.forEach.call(menu.querySelectorAll('[role=menuitem]'), function (item) {
      item.addEventListener('click', function () { close(false); });
    });

    // 侧栏宽窄切换 / 窗口尺寸变化后重新摆位（DSH 的 portal 菜单同样跟随 anchor）
    window.addEventListener('resize', function () { if (isOpen()) place(); });
  }

  // ---------- 设置弹层 ----------
  function initSettings() {
    var modal = document.getElementById('ds-settings');
    if (!modal) return;
    var openers = document.querySelectorAll('[data-ds-settings-open]');
    var panel = modal.querySelector('.ds-settings__panel');
    var lastTrigger = null;

    initSettingsTabs(modal);

    function isOpen() { return !modal.hasAttribute('hidden'); }

    function open(trigger) {
      lastTrigger = trigger || null;
      modal.removeAttribute('hidden');
      modal.setAttribute('aria-hidden', 'false');
      document.body.classList.add('ds-modal-open');
      // 初始焦点落在选中的分区单元，没有则落在面板（README：不绘制外轮廓）
      var current = modal.querySelector('.ds-settings__cell.is-active') || panel;
      if (current) current.focus({ preventScroll: true });
    }

    function close() {
      if (!isOpen()) return;
      modal.setAttribute('hidden', '');
      modal.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('ds-modal-open');
      // 触发控件若在已收起的账号菜单里就不可见：焦点交还侧栏账号入口
      var target = lastTrigger;
      if (target && target.closest('[hidden]')) {
        target = document.querySelector('[data-ds-account-trigger]') || null;
      }
      if (target) target.focus({ preventScroll: true });
    }

    Array.prototype.forEach.call(openers, function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        open(el);
      });
    });

    Array.prototype.forEach.call(modal.querySelectorAll('[data-ds-settings-close]'), function (el) {
      el.addEventListener('click', close);
    });

    // 只有点在遮罩本身才算「点外部」，落在面板内部不关闭
    modal.addEventListener('mousedown', function (e) {
      if (e.target === modal) close();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isOpen()) {
        e.preventDefault();
        close();
        return;
      }
      // Web 口径：Mod+Alt+, 切换设置
      if ((e.metaKey || e.ctrlKey) && e.altKey && e.key === ',') {
        e.preventDefault();
        if (isOpen()) close(); else open(null);
      }
    });
  }

  // ---------- composer ----------
  function initComposer() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-ds-card]'), function (card) {
      var input = card.querySelector('[data-ds-input]');
      var send = card.querySelector('[data-ds-send]');
      if (!input) return;

      var locked = input.dataset.locked === '1';
      var form = card.closest('form');

      function autosize() {
        input.style.height = 'auto';
        var h = Math.min(input.scrollHeight, TEXT_MAX);
        input.style.height = h + 'px';
        input.style.overflowY = input.scrollHeight > TEXT_MAX ? 'auto' : 'hidden';
      }

      function syncSend() {
        if (!send) return;
        send.disabled = locked || input.value.trim().length === 0;
      }

      input.addEventListener('input', function () { autosize(); syncSend(); });
      input.addEventListener('compositionstart', function () { input.dataset.composing = '1'; });
      input.addEventListener('compositionend', function () {
        delete input.dataset.composing;
        autosize();
        syncSend();
      });

      input.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' || e.shiftKey) return;
        // 输入法组字中回车是「上屏」，不能当发送
        if (e.isComposing || input.dataset.composing) return;
        e.preventDefault();
        if (send && !send.disabled) send.click();
      });

      autosize();
      syncSend();
    });
  }

  // ---------- 设置式二级页（复用 DSH SettingsPanel 的那一页）----------
  /* 二级页不是「换正文」，而是像 DSH 点开设置一样盖一层弹层：
     overlay + 800×800 panel（见 settings-general SettingsPanel / .ds-settings*）。
     这里只做开合与地址栏同步，且全部走文档级委托 —— 首页面板正文由
     home-panels.js 整块替换后不需要重新绑定。 */
  function initSubpages() {
    var RETURN = typeof WeakMap === 'function' ? new WeakMap() : null;
    var HOST_ID = 'ds-subpage-host';

    function searchHas(query) {
      if (!query) return false;
      var eq = query.indexOf('=');
      if (eq < 0) return false;
      var key = query.slice(0, eq);
      // 只认第一组键值：地址里可能带着别的参数（如 view=edit&id=7），
      // 不能把 "edit&id=7" 整串拿去比值，否则弹层永远匹配不上。
      var value = query.slice(eq + 1).split('&')[0];
      var params = new URLSearchParams(window.location.search);
      return params.get(key) === value;
    }

    /* 深链地址可能是绝对（link.href）也可能是相对（模板里的 sp_url），
       比较时统一按 pathname + search 归一，否则关闭时永远还原不了地址栏。 */
    function sameUrl(a, b) {
      if (!a || !b) return false;
      if (a === b) return true;
      try {
        var ua = new URL(a, window.location.href);
        var ub = new URL(b, window.location.href);
        return ua.pathname === ub.pathname && ua.search === ub.search;
      } catch (e) { return false; }
    }

    function modals() {
      return document.querySelectorAll('[data-ds-subpage]');
    }

    function focusFirst(modal) {
      var target = modal.querySelector('.ds-settings__cell.is-active') ||
        modal.querySelector('.ds-settings__panel');
      if (!target) return;
      try { target.focus({ preventScroll: true }); } catch (e) { target.focus(); }
    }

    function openModal(modal, trigger) {
      modal.removeAttribute('hidden');
      modal.setAttribute('aria-hidden', 'false');
      if (RETURN) RETURN.set(modal, trigger || null);
      document.body.classList.add('ds-modal-open');
      focusFirst(modal);
      var url = modal.getAttribute('data-ds-subpage-url');
      if (url && !sameUrl(url, window.location.href)) {
        try { window.history.pushState({ dsSubpage: modal.id }, '', url); }
        catch (e) { /* 不支持 history 的环境退化为原地打开 */ }
      }
    }

    function closeModal(modal) {
      if (modal.hasAttribute('hidden')) return;
      modal.setAttribute('hidden', '');
      modal.setAttribute('aria-hidden', 'true');
      /* 叠在设置上的那一层关掉：把底下藏着的设置面板放回来 */
      if (modal.id === HOST_ID) {
        var behind = document.getElementById('ds-settings');
        if (behind) behind.classList.remove('ds-settings--stacked');
      }
      var url = modal.getAttribute('data-ds-subpage-url');
      var base = modal.getAttribute('data-ds-subpage-base');
      if (base && url && sameUrl(url, window.location.href)) {
        try { window.history.replaceState({}, '', base); } catch (e) { /* 同上 */ }
      }
      var trigger = RETURN ? RETURN.get(modal) : null;
      if (trigger && document.contains(trigger)) {
        try { trigger.focus({ preventScroll: true }); } catch (e) { trigger.focus(); }
      }
      syncBodyClass();
    }

    function syncBodyClass() {
      var anyOpen = document.querySelector('[data-ds-subpage]:not([hidden])');
      var settingsOpen = document.getElementById('ds-settings');
      if (anyOpen || (settingsOpen && !settingsOpen.hasAttribute('hidden'))) {
        document.body.classList.add('ds-modal-open');
      } else {
        document.body.classList.remove('ds-modal-open');
      }
    }

    /* 地址栏是唯一真源：?sub=rules / ?view=new 在 → 打开，不在 → 收起。
       面板正文被换掉后由 home-panels.js 调一次 window.DSSubpage.sync()。 */
    function sync() {
      Array.prototype.forEach.call(modals(), function (modal) {
        // 自带地址页的弹层（如「已读人员」）由服务端决定开合，地址栏里没有对应参数，
        // 不参与这里的同步；关闭仍走 ✕ / 遮罩 / Escape。
        if (modal.hasAttribute('data-ds-subpage-static')) return;
        var shouldOpen = searchHas(modal.getAttribute('data-ds-subpage-query'));
        if (shouldOpen && modal.hasAttribute('hidden')) openModal(modal, null);
        else if (!shouldOpen && !modal.hasAttribute('hidden')) closeModal(modal);
      });
      // 取回来的面板（见 openPanel）也跟地址栏对齐：后退到列表地址就收起
      var host = document.getElementById(HOST_ID);
      if (host && !host.hasAttribute('hidden')) {
        var hostUrl = host.getAttribute('data-ds-subpage-url');
        if (hostUrl && (window.location.pathname + window.location.search) !== hostUrl) {
          closeModal(host);
        }
      }
      syncBodyClass();
    }

    /* ---------- 原地取内容（DSH 的设置面板就是原地盖一层，不是跳一页）----------
       列表里的「修改 / 编辑 / 查看 / 已读人员」这些深链，服务端返回的本来就是同一块
       `.ds-settings__panel`，所以点开时只把这块取回来换进弹层，页面本身不重新加载：
       侧栏不重绘、滚动不归零、没有白屏。地址栏 pushState 成深链地址（刷新依然可用），
       关闭时 replaceState 回列表。取不到面板（权限/异常）就退回整页跳转，行为与旧版一致。 */
    function hostEl() {
      var host = document.getElementById(HOST_ID);
      if (host) return host;
      var closeLabel = 'Close';
      var modalClose = document.querySelector('#ds-settings .ds-settings__close[aria-label]');
      if (modalClose) closeLabel = modalClose.getAttribute('aria-label');

      host = document.createElement('div');
      host.id = HOST_ID;
      host.className = 'ds-settings ds-settings--subpage ds-settings--single';
      host.setAttribute('role', 'dialog');
      host.setAttribute('aria-modal', 'true');
      host.setAttribute('data-ds-subpage', '');
      host.setAttribute('data-ds-subpage-static', '');
      host.setAttribute('hidden', '');
      host.setAttribute('aria-hidden', 'true');
      host.setAttribute('data-ds-close-label', closeLabel);

      var overlay = document.createElement('div');
      overlay.className = 'ds-settings__overlay';
      overlay.setAttribute('aria-hidden', 'true');
      overlay.setAttribute('data-ds-modal-close', '');
      host.appendChild(overlay);

      // 面板里的表单也原地提交：校验失败换回带错误的面板，成功/重定向才整页走
      host.addEventListener('submit', function (e) {
        var form = e.target;
        if (!form || form.tagName !== 'FORM') return;
        if (host.hasAttribute('hidden')) return;
        var method = (form.getAttribute('method') || 'get').toLowerCase();
        if (method !== 'post' || form.hasAttribute('target')) return;
        if (form.hasAttribute('data-ds-allow-native')) return;
        e.preventDefault();
        var url = form.getAttribute('action') || window.location.href;
        var body = new FormData(form);
        /* 保存成功后回哪：填进面板前的地址（设置里打开时就是当前页），
           而不是被 pushState 顶上去的深链地址。 */
        var base = host.getAttribute('data-ds-subpage-base');
        if (base) body.set('next', base);
        if (e.submitter && e.submitter.name) {
          body.append(e.submitter.name, e.submitter.value);
        }
        fetch(url, { method: 'POST', body: body, credentials: 'same-origin', redirect: 'follow' })
          .then(function (res) {
            if (res.redirected || !res.ok) {
              window.location.assign(res.url || url);
              return null;
            }
            return res.text().then(function (html) {
              var panel = panelFrom(html);
              if (panel) mountPanel(host, panel);
              else window.location.assign(url);
            });
          })
          .catch(function () { form.submit(); });
      });

      /* 面板里的站内链接也留在面板里（消息中心读一条 → 列表原地刷新；活动记录里
         换一条记录）。取回的不是面板页（比如点到了列表页）就交给 fallback 整页走。
         修饰键 / 中键 / target / 下载照浏览器原生行为，不接管。 */
      host.addEventListener('click', function (e) {
        if (e.defaultPrevented || e.button !== 0) return;
        if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
        if (host.hasAttribute('hidden')) return;
        var link = e.target && e.target.closest ? e.target.closest('a[href]') : null;
        if (!link || !host.contains(link)) return;
        if (link.hasAttribute('data-ds-modal-close') || link.hasAttribute('data-ds-close')) return;
        if (link.hasAttribute('data-ds-modal-open') || link.hasAttribute('data-ds-panel')) return;
        if (link.hasAttribute('target') || link.hasAttribute('download')) return;
        if (link.hasAttribute('data-ds-allow-native')) return;
        var href = link.getAttribute('href');
        if (!href || href.charAt(0) === '#') return;
        var target;
        try { target = new URL(link.href, window.location.href); } catch (err) { return; }
        if (target.origin !== window.location.origin) return;
        if (target.pathname === window.location.pathname && target.hash) return;
        e.preventDefault();
        openPanel(link.href, link);
      });

      document.body.appendChild(host);
      return host;
    }

    function panelFrom(html) {
      var doc = new DOMParser().parseFromString(html, 'text/html');
      if (!doc) return null;
      /* 一页里可能不止一块面板（公告中心：发布公告弹层 + 已读人员弹层）。
         取「在取回页面里正处于打开态」的那一块，否则会拿错标题/正文。 */
      var owner = doc.querySelector('[data-ds-subpage]:not([hidden])') ||
        doc.querySelector('[data-ds-subpage]');
      var panel = owner ? owner.querySelector('.ds-settings__panel')
        : doc.querySelector('.ds-settings__panel');
      if (!panel) return null;
      // 深链页右上是「返回箭头」（点了真的跳页）；进了弹层就该是关闭按钮
      var head = panel.querySelector('.ds-settings__header');
      var back = panel.querySelector('.ds-settings__back');
      if (back && back.parentNode) back.parentNode.removeChild(back);
      if (head && !head.querySelector('[data-ds-modal-close]')) {
        var label = (document.getElementById(HOST_ID) || {}).getAttribute
          ? document.getElementById(HOST_ID).getAttribute('data-ds-close-label')
          : 'Close';
        var close = document.createElement('button');
        close.type = 'button';
        close.className = 'ds-settings__close';
        close.setAttribute('data-ds-modal-close', '');
        close.setAttribute('aria-label', label || 'Close');
        close.innerHTML = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true">' +
          '<path d="M4 4l8 8M12 4l-8 8" stroke="currentColor" stroke-width="1.5" fill="none"' +
          ' stroke-linecap="round"/></svg>';
        head.appendChild(close);
      }
      return panel;
    }

    function mountPanel(host, panel) {
      var old = host.querySelector('.ds-settings__panel');
      if (old) old.parentNode.removeChild(old);
      host.appendChild(document.importNode(panel, true));
      var title = host.querySelector('.ds-settings__title');
      if (title && title.id) host.setAttribute('aria-labelledby', title.id);
      else if (title) host.setAttribute('aria-label', title.textContent);
    }

    function openPanel(url, trigger) {
      var host = hostEl();
      /* 从设置面板里再点开一层（个人资料 / 查看权限 / 修改密码）：DSH 是在设置里
         打开，不是再叠一个遮罩。这时候把 host 的遮罩做成透明，面板与设置面板同
         位置同尺寸，看着就是「内容换了一层」。 */
      var settings = document.getElementById('ds-settings');
      var stacked = !!settings && !settings.hasAttribute('hidden');
      host.classList.toggle('ds-settings--subpage--stack', stacked);
      /* 叠层时把底下那块设置面板先藏起来（遮罩留着当暗底）：二级页面板按内容收
         高度，矮面板浮在一张 800 的面板里，四周全是空白。 */
      if (settings) settings.classList.toggle('ds-settings--stacked', stacked);
      var base = host.hasAttribute('hidden')
        ? window.location.pathname + window.location.search
        : host.getAttribute('data-ds-subpage-base');
      var landed = url;
      fetch(url, { credentials: 'same-origin' })
        .then(function (res) {
          if (!res.ok) throw new Error('HTTP ' + res.status);
          /* 取回后可能被重定向（如消息「已读」跳回列表）：地址栏认落点，不认请求串 */
          landed = res.url || url;
          return res.text();
        })
        .then(function (html) {
          var panel = panelFrom(html);
          if (!panel) throw new Error('no panel');
          mountPanel(host, panel);
          host.setAttribute('data-ds-subpage-url', landed);
          host.setAttribute('data-ds-subpage-base', base);
          openModal(host, trigger || null);
        })
        .catch(function () { window.location.assign(url); });
    }

    document.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || !t.closest) return;

      // 深链二级页：原地取面板，不跳页（见 openPanel）。修饰键/中键不接管，
      // 保持「Ctrl+点开新标签」这种浏览器原生行为。
      var panelLink = t.closest('[data-ds-panel]');
      if (panelLink) {
        var href = panelLink.getAttribute('href');
        if (href && href.charAt(0) !== '#' && !panelLink.hasAttribute('target') &&
            e.button === 0 && !e.metaKey && !e.ctrlKey && !e.shiftKey && !e.altKey) {
          e.preventDefault();
          openPanel(panelLink.href, panelLink);
          return;
        }
      }

      var opener = t.closest('[data-ds-modal-open]');
      if (opener) {
        var modal = document.getElementById(opener.getAttribute('data-ds-modal-open'));
        if (modal && modal.hasAttribute('data-ds-subpage')) {
          e.preventDefault();
          openModal(modal, opener);
          return;
        }
      }
      var closer = t.closest('[data-ds-modal-close]');
      if (closer) {
        var ancestor = closer.closest('[data-ds-subpage]');
        if (ancestor) {
          e.preventDefault();
          closeModal(ancestor);
        }
      }
    });

    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      var open = document.querySelector('[data-ds-subpage]:not([hidden])');
      if (!open) return;
      e.preventDefault();
      closeModal(open);
    });

    window.addEventListener('popstate', sync);
    window.DSSubpage = { sync: sync, closeAll: function () {
      Array.prototype.forEach.call(modals(), function (m) { closeModal(m); });
      syncBodyClass();
    } };

    sync();
  }

  function boot() {
    initRail();
    initSettings();
    initSubpages();
    initAccount();
    initMore();
    initComposer();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
