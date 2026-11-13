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

  function boot() {
    initRail();
    initSettings();
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
