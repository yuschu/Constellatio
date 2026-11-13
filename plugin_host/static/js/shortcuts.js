/* v2.2.0 · 快捷键层（照 DSH `dsh-client-ui-shortcuts` 的参考对话框 + 固定绑定）
 *
 * 约定（全部对应用户在弹层里能看到的行）：
 *   Ctrl+/        打开 / 关闭快捷键参考（DSH 的 Mod+Slash）
 *   Ctrl+Alt+,    打开设置弹层（DSH Web 的 Mod+Alt+Comma——把 Ctrl+, 留给浏览器）
 *   Ctrl+Alt+1..9 侧栏菜单第 1..9 项直达（行由服务端按权限与插件启停过滤）
 *   Esc           关闭当前弹层
 *
 * 与输入框的关系：带 Ctrl / Alt 的组合在输入框里也照样触发（DSH 的应用绑定优先于
 * 编辑器输入），其余单键组合不注册，避免吃掉打字。长按重复（event.repeat）一律吞掉。
 */
(function () {
  var dialog = document.getElementById('ds-shortcuts');
  if (!dialog) { return; }

  var panel = dialog.querySelector('.ds-shortcuts__panel');
  var search = dialog.querySelector('[data-ds-shortcuts-search]');
  var clearBtn = dialog.querySelector('[data-ds-shortcuts-clear]');
  var rows = Array.prototype.slice.call(
    dialog.querySelectorAll('[data-ds-shortcut-row]'));
  var empty = dialog.querySelector('[data-ds-shortcuts-empty]');
  var lastTrigger = null;

  function isOpen() { return !dialog.hasAttribute('hidden'); }

  function open(trigger) {
    if (isOpen()) { return; }
    lastTrigger = trigger || document.activeElement;
    dialog.removeAttribute('hidden');
    dialog.setAttribute('aria-hidden', 'false');
    document.body.classList.add('ds-modal-open');
    if (panel) { panel.focus({ preventScroll: true }); }
    if (search) { search.value = ''; applySearch(); search.focus({ preventScroll: true }); }
  }

  function close() {
    if (!isOpen()) { return; }
    dialog.setAttribute('hidden', '');
    dialog.setAttribute('aria-hidden', 'true');
    document.body.classList.remove('ds-modal-open');
    var back = lastTrigger && document.contains(lastTrigger)
      ? lastTrigger : document.querySelector('[data-ds-account-trigger]');
    if (back && back.focus) { back.focus({ preventScroll: true }); }
  }

  function toggle(trigger) {
    if (isOpen()) { close(); } else { open(trigger); }
  }

  /* ---------- 搜索：标签 / 按键的有序子序列匹配（DSH 同规则） ---------- */

  function subsequence(query, text) {
    var qi = 0;
    for (var i = 0; i < text.length && qi < query.length; i += 1) {
      if (text.charAt(i) === query.charAt(qi)) { qi += 1; }
    }
    return qi === query.length;
  }

  function applySearch() {
    var q = (search && search.value || '').trim().toLowerCase();
    var shown = 0;
    rows.forEach(function (row) {
      var label = row.querySelector('.ds-shortcuts__label');
      var hay = ((label ? label.textContent : '') + ' ' +
                 (row.getAttribute('data-keys') || '')).toLowerCase();
      var hit = !q || subsequence(q, hay);
      row.hidden = !hit;
      if (hit) { shown += 1; }
    });
    if (empty) { empty.hidden = shown > 0; }
    if (clearBtn) { clearBtn.hidden = !q; }
    /* 分组标题跟着行一起隐藏，避免只剩空标题 */
    Array.prototype.forEach.call(dialog.querySelectorAll('.ds-shortcuts__group'),
      function (group) {
        var list = group.nextElementSibling;
        var any = false;
        if (list) {
          Array.prototype.forEach.call(list.children, function (row) {
            if (!row.hidden) { any = true; }
          });
        }
        group.hidden = !any;
      });
  }

  if (search) {
    search.addEventListener('input', applySearch);
  }
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      if (search) { search.value = ''; applySearch(); search.focus(); }
    });
  }

  /* ---------- 开合 ---------- */

  Array.prototype.forEach.call(
    document.querySelectorAll('[data-ds-shortcuts-open]'), function (el) {
      el.addEventListener('click', function () { open(el); });
    });
  Array.prototype.forEach.call(
    dialog.querySelectorAll('[data-ds-shortcuts-close]'), function (el) {
      el.addEventListener('click', close);
    });

  /* ---------- 按键：组合规范化 + 分发 ---------- */

  function combo(event) {
    var parts = [];
    if (event.ctrlKey) { parts.push('Ctrl'); }
    if (event.altKey) { parts.push('Alt'); }
    if (event.shiftKey) { parts.push('Shift'); }
    if (event.metaKey) { parts.push('Meta'); }
    var key = event.key;
    if (!key) { return ''; }
    if (key.length === 1 && key.toUpperCase() >= 'A' && key.toUpperCase() <= 'Z') {
      key = key.toUpperCase();
    }
    if (key === ' ') { key = 'Space'; }
    parts.push(key);
    return parts.join('+');
  }

  function runAction(row) {
    var action = row.getAttribute('data-shortcut-action');
    var url = row.getAttribute('data-shortcut-url');
    if (action === 'settings') {
      var opener = document.querySelector('[data-ds-settings-open]');
      if (opener) { close(); opener.click(); }
      return true;
    }
    if (action === 'shortcuts') {
      toggle(null);
      return true;
    }
    if (url) {
      window.location.assign(url);
      return true;
    }
    return false;
  }

  document.addEventListener('keydown', function (event) {
    if (event.defaultPrevented || event.repeat) { return; }
    if (event.isComposing || event.keyCode === 229) { return; }

    var keys = combo(event);
    if (!keys) { return; }

    if (keys === 'Ctrl+/') {
      event.preventDefault();
      /* 参考弹层在最前：吞掉事件，别让底下的设置 / 二级页一起响应 */
      event.stopPropagation();
      toggle(null);
      return;
    }

    if (event.key === 'Escape' && isOpen()) {
      event.preventDefault();
      event.stopPropagation();
      close();
      return;
    }

    /* 只认带修饰键的组合：单键留给输入与浏览器 */
    if (!event.ctrlKey && !event.altKey) { return; }

    for (var i = 0; i < rows.length; i += 1) {
      if (rows[i].getAttribute('data-keys') === keys) {
        if (runAction(rows[i])) {
          event.preventDefault();
          /* 同一组合外壳里也注册了（ds-shell 自己处理 Mod+Alt+,）：这里吞掉事件，
             否则「打开设置」会被随后的一次切换立刻关回去 */
          event.stopPropagation();
        }
        return;
      }
    }
  }, true);
})();
