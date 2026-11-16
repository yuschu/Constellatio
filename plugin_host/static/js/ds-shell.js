/* DSH 外壳交互（v2.0.5，侧栏收起 v2.0.8，命令菜单 v2.2.17）
 *
 * 行为与参数取自 dsh 客户端源码，不是像素采样：
 *   侧栏   dsh-client-ui-sidebar/SidebarRoot     —— 收起 = slide + crossfade、settled 150ms 后落 36×36 图标行、
 *          gap 12、轨宽 56（dsh-client-ui-layout collapsedWidth）
 *          dsh-client-ui-layout/toggleSidebar    —— 点击在 sidebar === 0 ? 280 : 0 之间切换，不持久化
 *          dsh-client-ui-settings-general/Trigger —— 设置入口 42px 行，右侧快捷键 hint 悬停显形
 *   设置   dsh-client-ui-settings-general/Panel   —— 800×800 grid（nav 188px）、Esc/遮罩/关闭收起、
 *          关闭后焦点回到触发控件、Web 快捷键 Mod+Alt+,
 *   输入框 dsh-client-ui-conversation/Composer    —— min-height 36（hero 52）、max 336、
 *          Enter 发送 / Shift+Enter 换行 / 输入法组字期间不发送；
 *          `/` 打开命令菜单，↑↓ 选择、Enter/Tab 执行、Esc 关闭。
 *   命令   dsh-client-ui-commands                —— 首版只接有真实动作的 /file 与 /model，
 *          其余 goal/plan/feedback/compact/permission/export/btw/library 无后端，不列假命令。
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

    /* 快捷键 Ctrl+Alt+B 统一由 shortcuts.js 的参考表分发（row[data-shortcut-action=sidebar]），
       避免两处 document 监听各 toggle 一次、把侧栏原地开关两次。 */
  }

  // ---------- 设置分区切换（通用 / 模型 / 我的）----------
  function initSettingsTabs(modal) {
    var cells = modal.querySelectorAll('[data-ds-settings-tab]');
    var panels = modal.querySelectorAll('[data-ds-settings-panel]');
    if (cells.length === 0 || panels.length === 0) return null;

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
    return select;
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

    var selectTab = initSettingsTabs(modal);

    function isOpen() { return !modal.hasAttribute('hidden'); }

    function open(trigger) {
      lastTrigger = trigger || null;
      if (trigger) {
        var targetTab = trigger.getAttribute('data-ds-settings-target');
        if (targetTab && selectTab) selectTab(targetTab);
      }
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
      }
    });

    // 保存/测试模型配置后服务端带 settings=model 回跳；刷新时直接展开该分区。
    var initialTab = modal.getAttribute('data-ds-settings-open-tab');
    if (initialTab) {
      if (selectTab) selectTab(initialTab);
      open(null);
    }
  }

  // ---------- composer ----------
  function initComposer() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-ds-card]'), function (card) {
      var input = card.querySelector('[data-ds-input]');
      var send = card.querySelector('[data-ds-send]');
      if (!input) return;

      var locked = input.dataset.locked === '1';
      var chatForm = card.closest('form[data-ds-chat-form]');
      var submitting = chatForm && chatForm.dataset.sending === '1';
      var posted = false;
      var DRAFT_KEY = 'constellatio:assistant:draft';
      var fileInput = card.querySelector('[data-ds-file-input]');
      var fileList = card.querySelector('[data-ds-file-list]');
      var fileError = card.querySelector('[data-ds-file-error]');
      var attach = card.querySelector('[data-ds-attach]');
      var commandMenu = card.querySelector('[data-ds-command-menu]');
      var commandEmpty = commandMenu && commandMenu.querySelector('[data-ds-command-empty]');
      var commandRows = commandMenu
        ? Array.prototype.slice.call(commandMenu.querySelectorAll('[data-ds-command]'))
        : [];
      var commandGroups = commandMenu
        ? Array.prototype.slice.call(commandMenu.querySelectorAll('[data-ds-command-group]'))
        : [];
      var commandActive = null;
      var commandSource = null;
      var selectedFiles = [];
      var maxFiles = parseInt(
        (fileInput && fileInput.dataset.dsFileMaxCount) || '3', 10) || 3;
      var maxFileBytes = parseInt(
        (fileInput && fileInput.dataset.dsFileMaxBytes) || '1000000', 10) || 1000000;
      var allowedExtensions = fileInput
        ? (fileInput.getAttribute('accept') || '').split(',').map(function (item) {
          return item.trim().toLowerCase();
        }).filter(Boolean)
        : [];

      function readDraft() {
        try { return window.sessionStorage.getItem(DRAFT_KEY) || ''; } catch (e) { return ''; }
      }

      function writeDraft() {
        // 提交动作已经发出后，用户再敲的字属于下一条草稿；
        // 发出前敲的字会进入本次 POST，不写入草稿。
        if (locked || (submitting && !posted)) return;
        try {
          if (input.value) window.sessionStorage.setItem(DRAFT_KEY, input.value);
          else window.sessionStorage.removeItem(DRAFT_KEY);
        } catch (e) { /* 隐私模式下 sessionStorage 不可用，不影响发送 */ }
      }

      function clearDraft() {
        try { window.sessionStorage.removeItem(DRAFT_KEY); } catch (e) { /* 同上 */ }
      }

      function restoreDraft() {
        if (locked || input.value) return;
        var draft = readDraft();
        if (draft) input.value = draft;
      }

      function autosize() {
        input.style.height = 'auto';
        var h = Math.min(input.scrollHeight, TEXT_MAX);
        input.style.height = h + 'px';
        input.style.overflowY = input.scrollHeight > TEXT_MAX ? 'auto' : 'hidden';
      }

      function syncSend() {
        if (!send) return;
        var hasText = input.value.trim().length > 0;
        send.disabled = locked || submitting ||
          (!hasText && selectedFiles.length === 0);
      }

      function setFileError(message) {
        if (!fileError) return;
        fileError.textContent = message || '';
        fileError.hidden = !message;
      }

      function formatBytes(bytes) {
        if (bytes < 1024) return bytes + ' B';
        return Math.ceil(bytes / 1024) + ' KB';
      }

      function fileKey(file) {
        return [file.name, file.size, file.lastModified || 0].join('|');
      }

      function syncFileInput() {
        if (!fileInput || !window.DataTransfer) return;
        try {
          var transfer = new DataTransfer();
          selectedFiles.forEach(function (file) { transfer.items.add(file); });
          fileInput.files = transfer.files;
        } catch (e) {
          // 极旧浏览器不支持给 input.files 赋值；保留原生选择，
          // 移除 chip 时仍可从列表上看出实际会提交哪些文件。
        }
      }

      function renderSelectedFiles() {
        if (!fileList) return;
        fileList.textContent = '';
        selectedFiles.forEach(function (file) {
          var chip = document.createElement('span');
          chip.className = 'as-file-chip';
          var name = document.createElement('span');
          name.className = 'as-file-chip__name';
          name.textContent = file.name;
          chip.appendChild(name);
          var size = document.createElement('span');
          size.className = 'as-file-chip__size';
          size.textContent = formatBytes(file.size);
          chip.appendChild(size);
          var remove = document.createElement('button');
          remove.type = 'button';
          remove.className = 'as-file-chip__remove';
          remove.setAttribute('aria-label', '移除 ' + file.name);
          remove.textContent = '×';
          remove.addEventListener('click', function () {
            setSelectedFiles(selectedFiles.filter(function (item) {
              return fileKey(item) !== fileKey(file);
            }));
            setFileError('');
          });
          chip.appendChild(remove);
          fileList.appendChild(chip);
        });
        fileList.hidden = selectedFiles.length === 0;
        syncSend();
      }

      function setSelectedFiles(files) {
        selectedFiles = files;
        syncFileInput();
        renderSelectedFiles();
      }

      function handleFileSelection() {
        if (!fileInput) return;
        var incoming = Array.prototype.slice.call(fileInput.files || []);
        if (incoming.length === 0) return;
        var next = selectedFiles.slice();
        var error = '';
        incoming.forEach(function (file) {
          if (next.length >= maxFiles) {
            error = '一次最多附加 ' + maxFiles + ' 个文件';
            return;
          }
          var dot = file.name.lastIndexOf('.');
          var ext = dot >= 0 ? file.name.slice(dot).toLowerCase() : '';
          if (allowedExtensions.length && allowedExtensions.indexOf(ext) === -1) {
            error = '暂不支持 ' + file.name + '；首版只收文本类文件';
            return;
          }
          if (file.size > maxFileBytes) {
            error = file.name + ' 超过 ' + Math.ceil(maxFileBytes / 1000000) + ' MB';
            return;
          }
          var duplicate = next.some(function (item) {
            return fileKey(item) === fileKey(file);
          });
          if (!duplicate) next.push(file);
        });
        setFileError(error);
        setSelectedFiles(next);
      }

      function visibleCommandRows() {
        return commandRows.filter(function (row) { return !row.hidden; });
      }

      function commandContext() {
        if (!commandMenu) return null;
        var caret = typeof input.selectionStart === 'number'
          ? input.selectionStart : input.value.length;
        // 与 DSH 的 slash 输入机一致：命令 token 必须位于行首或空白之后，
        // 且光标在 token 末尾；光标落在 token 中间时不抢普通文本编辑。
        if (caret !== input.value.length) return null;
        var before = input.value.slice(0, caret);
        var match = /(^|\s)\/([^\s/]*)$/.exec(before);
        if (!match) return null;
        return {
          start: match.index + match[1].length,
          end: caret,
          query: match[2]
        };
      }

      function setCommandActive(row) {
        commandActive = row || null;
        commandRows.forEach(function (item) {
          var active = item === commandActive;
          item.classList.toggle('is-active', active);
          item.setAttribute('aria-selected', active ? 'true' : 'false');
        });
        if (commandActive && commandActive.scrollIntoView) {
          try {
            commandActive.scrollIntoView({ block: 'nearest' });
          } catch (e) { commandActive.scrollIntoView(false); }
        }
      }

      function refreshCommandMenu() {
        if (!commandMenu || commandMenu.hidden) return;
        var query = '';
        if (commandSource === 'slash') {
          var context = commandContext();
          if (!context) {
            closeCommandMenu(false);
            return;
          }
          query = context.query.toLowerCase();
        }
        var visible = [];
        commandRows.forEach(function (row) {
          var text = (row.textContent + ' ' +
            (row.getAttribute('data-ds-command-token') || '')).toLowerCase();
          var match = !query || text.indexOf(query) !== -1;
          row.hidden = !match;
          if (match) visible.push(row);
        });
        commandGroups.forEach(function (group) {
          group.hidden = !group.querySelector('[data-ds-command]:not([hidden])');
        });
        if (commandEmpty) commandEmpty.hidden = visible.length > 0;
        if (!visible.length) {
          setCommandActive(null);
          return;
        }
        var index = visible.indexOf(commandActive);
        setCommandActive(visible[index < 0 ? 0 : index]);
      }

      function openCommandMenu(source) {
        if (!commandMenu || locked) return;
        commandSource = source;
        commandMenu.hidden = false;
        if (attach) attach.setAttribute('aria-expanded', 'true');
        if (source === 'button') setCommandActive(null);
        refreshCommandMenu();
      }

      function closeCommandMenu(focusInput) {
        if (!commandMenu) return;
        commandMenu.hidden = true;
        commandSource = null;
        setCommandActive(null);
        if (attach) attach.setAttribute('aria-expanded', 'false');
        if (focusInput) input.focus();
      }

      function executeCommand(row) {
        if (!row) return;
        var context = commandContext();
        if (context) {
          var value = input.value;
          input.value = value.slice(0, context.start) + value.slice(context.end);
          try { input.setSelectionRange(context.start, context.start); }
          catch (e) { /* 极旧浏览器不支持 setSelectionRange */ }
        }
        closeCommandMenu(false);
        writeDraft();
        autosize();
        syncSend();

        var command = row.getAttribute('data-ds-command');
        if (command === 'file') {
          if (fileInput) fileInput.click();
        } else if (command === 'model') {
          var modelTrigger = card.querySelector('[data-ds-model-trigger]');
          if (modelTrigger) modelTrigger.click();
        }
        // 模型浮层会自己把焦点放到第一项；附件选择器关闭后焦点回输入框。
        if (command !== 'model') input.focus();
      }

      function moveCommand(delta) {
        var visible = visibleCommandRows();
        if (!visible.length) return;
        var index = visible.indexOf(commandActive);
        if (index < 0) index = 0;
        else index = (index + delta + visible.length) % visible.length;
        setCommandActive(visible[index]);
      }

      if (attach && fileInput) {
        attach.addEventListener('click', function (event) {
          event.preventDefault();
          if (attach.disabled || locked) return;
          if (!commandMenu) {
            fileInput.click();
            return;
          }
          if (!commandMenu.hidden) {
            closeCommandMenu(true);
            return;
          }
          openCommandMenu(commandContext() ? 'slash' : 'button');
          input.focus();
        });
        fileInput.addEventListener('change', handleFileSelection);
      }

      if (commandMenu) {
        // 点击行不抢走 textarea 焦点，保持 DSH combobox 的输入连贯性。
        commandMenu.addEventListener('mousedown', function (event) {
          event.preventDefault();
        });
        commandMenu.addEventListener('click', function (event) {
          var row = event.target.closest &&
            event.target.closest('[data-ds-command]');
          if (!row) return;
          event.preventDefault();
          // /model 会合成 modelTrigger.click() 打开浮层；这次原始 row click
          // 若继续冒泡到 document 的 click 关闭器，会把刚打开的浮层又关掉。
          event.stopPropagation();
          executeCommand(row);
        });
        commandMenu.addEventListener('mouseover', function (event) {
          var row = event.target.closest &&
            event.target.closest('[data-ds-command]');
          if (row && !row.hidden) setCommandActive(row);
        });
        document.addEventListener('pointerdown', function (event) {
          if (commandMenu.hidden) return;
          if (commandMenu.contains(event.target)) return;
          // 同一个 `+` 按钮要承担开/关两态；把关闭交给 click 处理器，
          // 否则 pointerdown 先关、click 又开，按钮永远关不上。
          if (attach && attach.contains(event.target)) return;
          closeCommandMenu(false);
        });
      }

      // DSH 发送态：提交那一刻先把本地回显和运行状态画进对话，
      // 真正的 POST 晚一个绘制帧再交回浏览器，用户不会对着静止页面猜。
      function paintPending(text, files) {
        var row = document.createElement('div');
        row.className = 'as-row as-row--user as-row--pending';
        var turn = document.createElement('div');
        turn.className = 'as-turn';
        var bubble = document.createElement('div');
        bubble.className = 'as-bubble';
        if (files && files.length) {
          var fileRow = document.createElement('div');
          fileRow.className = 'as-bubble__files';
          files.forEach(function (file) {
            var chip = document.createElement('span');
            chip.className = 'as-file-chip as-file-chip--static';
            var name = document.createElement('span');
            name.className = 'as-file-chip__name';
            name.textContent = file.name;
            chip.appendChild(name);
            var size = document.createElement('span');
            size.className = 'as-file-chip__size';
            size.textContent = formatBytes(file.size);
            chip.appendChild(size);
            fileRow.appendChild(chip);
          });
          bubble.appendChild(fileRow);
        }
        bubble.appendChild(document.createTextNode(text));
        turn.appendChild(bubble);
        row.appendChild(turn);

        var status = document.createElement('div');
        status.className = 'as-pending';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        var spinner = document.createElement('span');
        spinner.className = 'as-pending__spinner';
        spinner.setAttribute('aria-hidden', 'true');
        var label = document.createElement('span');
        label.className = 'as-pending__label';
        label.textContent = (chatForm && chatForm.dataset.sendingLabel) || '';
        status.appendChild(spinner);
        status.appendChild(label);

        var thread = document.querySelector('.as-scroll--thread');
        if (thread) {
          thread.appendChild(row);
          thread.appendChild(status);
          thread.scrollTop = thread.scrollHeight;
          return;
        }

        var stack = card.closest('.as-stack');
        var composer = card.closest('.as-composer') || card;
        if (stack) {
          stack.insertBefore(row, composer);
          stack.insertBefore(status, composer);
          return;
        }
        if (composer.parentNode) {
          composer.parentNode.insertBefore(status, composer.nextSibling);
        }
      }

      if (chatForm) {
        chatForm.addEventListener('submit', function (e) {
          // 同步消费提交资格：按钮禁用只是状态，不能当作准入门闩。
          if (chatForm.dataset.sending === '1') {
            e.preventDefault();
            return;
          }
          var value = input.value.trim();
          if ((!value && selectedFiles.length === 0) || locked) return;

          e.preventDefault();
          chatForm.dataset.sending = '1';
          submitting = true;
          chatForm.setAttribute('aria-busy', 'true');
          paintPending(value || '请阅读附件', selectedFiles.slice());

          // DSH 口径：提交后不锁死输入。等待期间可以继续敲下一条；
          // 同步 PRG 返回会换页，所以输入内容进 sessionStorage，落地后恢复。
          autosize();
          syncSend();

          var handedOff = false;
          function handOff() {
            if (handedOff) return;
            handedOff = true;
            HTMLFormElement.prototype.submit.call(chatForm);
            posted = true;
            clearDraft();
            // 原生 submit 已同步构造表单数据；清空放到提交之后，
            // 否则 POST 里 message 为空，服务端只会原地重渲染。
            window.setTimeout(function () {
              input.value = '';
              autosize();
              syncSend();
            }, 0);
          }
          if (window.requestAnimationFrame) {
            window.requestAnimationFrame(function () {
              window.setTimeout(handOff, 60);
            });
          }
          // 后台标签页或浏览器不跑 rAF 时的兜底，避免永远卡在 pending。
          window.setTimeout(handOff, 250);
        });

        // 从会话页后退时浏览器可能走 bfcache，页面会带着 pending 和
        // data-sending=1 回来；此时必须复位，否则 composer 永远发不出第二条。
        window.addEventListener('pageshow', function (event) {
          if (!event.persisted) return;
          if (chatForm.dataset.sending === '1') {
            delete chatForm.dataset.sending;
            chatForm.removeAttribute('aria-busy');
            submitting = false;
            posted = false;
            Array.prototype.forEach.call(
              document.querySelectorAll('.as-row--pending, .as-pending'),
              function (node) {
                if (node.parentNode) node.parentNode.removeChild(node);
              }
            );
          }
          restoreDraft();
          autosize();
          syncSend();
        });
      }

      input.addEventListener('input', function () {
        if (commandMenu) {
          if (commandContext()) {
            if (commandMenu.hidden || commandSource !== 'slash') {
              openCommandMenu('slash');
            } else {
              refreshCommandMenu();
            }
          } else if (!commandMenu.hidden) {
            closeCommandMenu(false);
          }
        }
        writeDraft();
        autosize();
        syncSend();
      });
      input.addEventListener('click', function () {
        if (!commandMenu || commandMenu.hidden) return;
        if (!commandContext()) closeCommandMenu(false);
        else refreshCommandMenu();
      });
      input.addEventListener('compositionstart', function () { input.dataset.composing = '1'; });
      input.addEventListener('compositionend', function () {
        delete input.dataset.composing;
        autosize();
        syncSend();
      });

      input.addEventListener('keydown', function (e) {
        // 输入法组字中回车是「上屏」，不能当发送或选命令
        if (e.isComposing || input.dataset.composing) return;

        if (commandMenu && !commandMenu.hidden) {
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();
            moveCommand(e.key === 'ArrowDown' ? 1 : -1);
            return;
          }
          if (e.key === 'Escape') {
            e.preventDefault();
            e.stopPropagation();
            closeCommandMenu(true);
            return;
          }
          if (e.key === 'Tab') {
            if (e.shiftKey) {
              e.preventDefault();
              closeCommandMenu(true);
              return;
            }
            if (commandActive && !commandActive.hidden) {
              e.preventDefault();
              executeCommand(commandActive);
              return;
            }
          }
          if (e.key === 'Enter' && !e.shiftKey) {
            if (commandActive && !commandActive.hidden) {
              e.preventDefault();
              executeCommand(commandActive);
              return;
            }
            // 没有可执行行时退回普通发送，不把 `/xyz` 卡在菜单里。
            closeCommandMenu(false);
          }
        }

        if (e.key !== 'Enter' || e.shiftKey) return;
        e.preventDefault();
        if (send && !send.disabled) send.click();
      });

      restoreDraft();
      autosize();
      syncSend();
    });
  }

  // ---------- composer 的只读模式 / 模型服务浮层 ----------
  function initComposerMenus() {
    var MODE_KEY = 'constellatio:assistant:mode';
    var lastTrigger = null;

    function menuFor(trigger) {
      if (!trigger || !trigger.parentNode) return null;
      if (trigger.hasAttribute('data-ds-mode-trigger')) {
        return trigger.parentNode.querySelector('[data-ds-mode-menu]');
      }
      return trigger.parentNode.querySelector('[data-ds-model-menu]');
    }

    function closeMenus(except) {
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-ds-mode-menu], [data-ds-model-menu]'),
        function (menu) {
          if (menu === except) return;
          menu.hidden = true;
          var trigger = menu.parentNode &&
            menu.parentNode.querySelector(
              '[data-ds-mode-trigger], [data-ds-model-trigger]');
          if (trigger) trigger.setAttribute('aria-expanded', 'false');
        }
      );
    }

    function labelFor(mode) {
      var option = document.querySelector(
        '[data-ds-mode-option="' + mode + '"] .as-popover__item-main');
      if (option && option.textContent.trim()) return option.textContent.trim();
      return mode === 'readwrite' ? '可写' : '只读';
    }

    function setMode(mode) {
      var normalized = mode === 'readwrite' ? 'readwrite' : 'readonly';
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-ds-mode-input]'),
        function (input) { input.value = normalized; }
      );
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-ds-mode-label]'),
        function (label) { label.textContent = labelFor(normalized); }
      );
      Array.prototype.forEach.call(
        document.querySelectorAll('[data-ds-mode-option]'),
        function (option) {
          option.setAttribute(
            'aria-checked',
            option.getAttribute('data-ds-mode-option') === normalized
              ? 'true' : 'false');
        }
      );
      try { window.sessionStorage.setItem(MODE_KEY, normalized); } catch (e) { /* 隐私模式 */ }
    }

    function readMode() {
      try {
        var value = window.sessionStorage.getItem(MODE_KEY);
        return value === 'readwrite' ? 'readwrite' : 'readonly';
      } catch (e) {
        return 'readonly';
      }
    }

    document.addEventListener('click', function (event) {
      var trigger = event.target.closest &&
        event.target.closest('[data-ds-mode-trigger], [data-ds-model-trigger]');
      if (trigger) {
        event.preventDefault();
        var menu = menuFor(trigger);
        if (!menu) return;
        var willOpen = menu.hidden;
        closeMenus();
        menu.hidden = !willOpen;
        trigger.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
        lastTrigger = trigger;
        if (willOpen) {
          var first = menu.querySelector('.as-popover__item, .as-popover__link');
          if (first) first.focus();
        }
        return;
      }

      var option = event.target.closest &&
        event.target.closest('[data-ds-mode-option]');
      if (option) {
        event.preventDefault();
        setMode(option.getAttribute('data-ds-mode-option'));
        closeMenus();
        if (lastTrigger) lastTrigger.focus();
        return;
      }

      if (event.target.closest && !event.target.closest('.as-popover-anchor')) {
        closeMenus();
      }
    });

    document.addEventListener('keydown', function (event) {
      if (event.key !== 'Escape') return;
      var open = document.querySelector(
        '[data-ds-mode-menu]:not([hidden]), [data-ds-model-menu]:not([hidden])');
      if (!open) return;
      event.preventDefault();
      closeMenus();
      if (lastTrigger) lastTrigger.focus();
    });

    setMode(readMode());
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
      } else if (base && !url && modal.hasAttribute('data-ds-subpage-static')) {
        /* 自带地址页的静态弹层（组织架构「用户资料」）没有自己的 URL，页面本身是
           `/structure/user/<id>/`；关掉它地址栏退回它底下的组织架构总览，免得地址
           说在用户页、画面却是总览。 */
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
      /* 从另一个二级页弹层里再点开（组织架构「用户资料」→「用户管理」）：先把那层
         收掉，否则两个遮罩叠一起。落点沿用那层的 base —— 关掉新面板就回到它底下
         的那一页（组织架构总览），而不是停在用户页。 */
      var open = document.querySelector('[data-ds-subpage]:not([hidden])');
      var openBase = '';
      if (open && open.id !== HOST_ID) {
        openBase = open.getAttribute('data-ds-subpage-base') || '';
        closeModal(open);
      }
      var base = openBase || (host.hasAttribute('hidden')
        ? window.location.pathname + window.location.search
        : host.getAttribute('data-ds-subpage-base'));
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
    initComposerMenus();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})();
