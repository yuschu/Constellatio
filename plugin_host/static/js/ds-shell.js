/* DSH 外壳交互（v2.0.5）
 *
 * 行为与参数取自 dsh 客户端源码，不是像素采样：
 *   侧栏   dsh-client-ui-sidebar/SidebarRoot     —— collapsed 36×36 图标行、gap 12、rail 宽 64
 *          dsh-client-ui-settings-general/Trigger —— 设置入口 42px 行，右侧快捷键 hint 悬停显形
 *   设置   dsh-client-ui-settings-general/Panel   —— 800×800 grid（nav 188px）、Esc/遮罩/关闭收起、
 *          关闭后焦点回到触发控件、Web 快捷键 Mod+Alt+,
 *   输入框 dsh-client-ui-conversation/Composer    —— min-height 36（hero 52）、max 336、
 *          Enter 发送 / Shift+Enter 换行 / 输入法组字期间不发送
 */
(function () {
  'use strict';

  var LS_RAIL = 'dsRailCollapsed';
  var TEXT_MAX = 336;

  // ---------- 侧栏折叠 ----------
  function initRail() {
    var toggle = document.querySelector('[data-ds-rail-toggle]');
    if (!toggle) return;
    var root = document.documentElement;

    function apply(collapsed) {
      if (collapsed) root.setAttribute('data-rail-collapsed', 'true');
      else root.removeAttribute('data-rail-collapsed');
      toggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
      var label = collapsed ? toggle.dataset.labelOpen : toggle.dataset.labelCollapse;
      if (label) toggle.setAttribute('aria-label', label);
    }

    var stored = null;
    try { stored = localStorage.getItem(LS_RAIL); } catch (e) { /* 隐私模式 */ }
    apply(stored === '1');

    toggle.addEventListener('click', function () {
      var next = root.getAttribute('data-rail-collapsed') !== 'true';
      apply(next);
      try { localStorage.setItem(LS_RAIL, next ? '1' : '0'); } catch (e) { /* 忽略 */ }
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
    initComposer();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
