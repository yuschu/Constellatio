/* v2.2.16 · 快捷键层（照 DSH `dsh-client-ui-shortcuts` 的参考对话框 + 行内编辑）
 *
 * DSH 0.2.2 的做法不是「设置里另开一张编辑表」：设置 General 只有一行
 * ShortcutsRow，点「查看」开这张参考卡；参考卡每行点击进入内联编辑器，
 * 提供录制 / 移除 / 恢复默认 / 冲突与保留键校验 / 恢复全部默认，
 * 修改结果写 localStorage（DSH Web 文档 `dsh.keybindings.v1`）。
 * 这里按同一交互移植，存储键改为 `constellatio.keybindings.v1`，只写当前
 * `web:windows` profile，保留其他 profile 与未知条目。
 *
 * 默认表（DSH 0.2.2 Web Windows 字面量）：
 *   Ctrl+Alt+N    新建会话（session.new）
 *   Ctrl+Alt+B    收起 / 展开侧栏（sidebar.left.toggle，仅首页有侧栏折叠）
 *   Ctrl+Alt+,    打开设置（settings.open）
 *   Ctrl+/        快捷键参考（shortcuts.open）
 *   Ctrl+Alt+1..9 侧栏菜单第 1..9 项直达（本站扩展，行由服务端按权限与插件启停过滤）
 *   Esc           关闭当前弹层（固定，不参与覆盖）
 *
 * 输入框的 Enter / Shift+Enter 是 DSH fixed 动作，本卡只读展示，不提供编辑。
 * 录制用物理按键的 event.key 生成组合；带 Ctrl / Alt / Meta 的组合在输入框里也触发，
 * 单键不注册，避免吃掉打字。长按重复（event.repeat）一律忽略。
 */
(function () {
  var dialog = document.getElementById('ds-shortcuts');
  if (!dialog) { return; }

  var STORAGE_KEY = 'constellatio.keybindings.v1';
  var PLATFORM = detectPlatform();
  var PROFILE = 'web:' + PLATFORM;

  var panel = dialog.querySelector('.ds-shortcuts__panel');
  var search = dialog.querySelector('[data-ds-shortcuts-search]');
  var clearBtn = dialog.querySelector('[data-ds-shortcuts-clear]');
  var rows = Array.prototype.slice.call(
    dialog.querySelectorAll('[data-ds-shortcut-row]'));
  var empty = dialog.querySelector('[data-ds-shortcuts-empty]');
  var statusEl = dialog.querySelector('[data-ds-shortcuts-status]');
  var resetBtn = dialog.querySelector('[data-ds-shortcuts-reset]');
  var footerMain = dialog.querySelector('[data-ds-shortcuts-footer-main]');
  var footerConfirm = dialog.querySelector('[data-ds-shortcuts-footer-confirm]');
  var footerActions = dialog.querySelector('[data-ds-shortcuts-footer-actions]');
  var cancelResetBtn = dialog.querySelector('[data-ds-shortcuts-cancel-reset]');
  var confirmResetBtn = dialog.querySelector('[data-ds-shortcuts-confirm-reset]');
  var editorTemplate = dialog.querySelector('[data-ds-shortcuts-editor-template]');
  var messageBox = dialog.querySelector('[data-ds-shortcuts-i18n]');
  var lastTrigger = null;

  var store = readStore();
  var overrides = readProfile(store);
  var rowById = {};
  var globalById = {};
  var editing = null;
  var recording = null;
  var statusTimer = null;
  var statusActive = false;
  var confirmingReset = false;

  function detectPlatform() {
    var ua = navigator.userAgent || '';
    if (/Mac/i.test(ua)) { return 'macos'; }
    if (/Win/i.test(ua)) { return 'windows'; }
    return 'linux';
  }

  function own(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function t(name) {
    if (!messageBox) { return ''; }
    return messageBox.getAttribute('data-msg-' + name) || '';
  }

  /* ---------- 持久化 ---------- */

  function emptyStore() {
    return { schemaVersion: 1, profiles: {} };
  }

  function readStore() {
    try {
      var raw = window.localStorage.getItem(STORAGE_KEY);
      if (!raw) { return emptyStore(); }
      var parsed = JSON.parse(raw);
      if (!parsed || parsed.schemaVersion !== 1 ||
          !parsed.profiles || typeof parsed.profiles !== 'object' ||
          Array.isArray(parsed.profiles)) {
        return emptyStore();
      }
      return parsed;
    } catch (error) {
      return emptyStore();
    }
  }

  function readProfile(source) {
    var profile = source && source.profiles ? source.profiles[PROFILE] : null;
    if (!profile || typeof profile !== 'object' || Array.isArray(profile)) {
      return {};
    }
    var out = {};
    Object.keys(profile).forEach(function (id) {
      var value = profile[id];
      if (value === null || typeof value === 'string') { out[id] = value; }
    });
    return out;
  }

  function writeStore() {
    try {
      if (!store.profiles || typeof store.profiles !== 'object') {
        store = emptyStore();
      }
      if (Object.keys(overrides).length) {
        store.profiles[PROFILE] = overrides;
      } else {
        delete store.profiles[PROFILE];
      }
      if (!Object.keys(store.profiles).length) {
        window.localStorage.removeItem(STORAGE_KEY);
        return true;
      }
      store.schemaVersion = 1;
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(store));
      return true;
    } catch (error) {
      return false;
    }
  }

  function reloadFromStore() {
    store = readStore();
    overrides = readProfile(store);
  }

  /* ---------- 行与生效键位 ---------- */

  function labelOf(row) {
    var label = row.querySelector('.ds-shortcuts__label');
    return label ? label.textContent.trim() : '';
  }

  function editable(row) {
    return !!row.getAttribute('data-shortcut-id') &&
      !row.hasAttribute('data-shortcut-fixed');
  }

  function defaultKeys(row) {
    return row.getAttribute('data-keys') || '';
  }

  function hasOverride(id) {
    return own(overrides, id);
  }

  function keysOfRow(row) {
    var id = row.getAttribute('data-shortcut-id');
    if (id && hasOverride(id)) { return overrides[id]; }
    return defaultKeys(row);
  }

  function keysOfId(id) {
    if (rowById[id]) { return keysOfRow(rowById[id]); }
    if (hasOverride(id)) { return overrides[id]; }
    if (globalById[id]) {
      return globalById[id].getAttribute('data-global-keys') || '';
    }
    return '';
  }

  function labelOfId(id) {
    if (rowById[id]) { return labelOf(rowById[id]); }
    if (globalById[id]) { return globalById[id].getAttribute('data-label') || id; }
    return id;
  }

  /* ---------- 组合键显示 / ARIA ---------- */

  function splitKeys(keys) {
    if (!keys) { return []; }
    return keys.split('+');
  }

  function ariaKeys(keys) {
    return splitKeys(keys).map(function (part) {
      return part === 'Ctrl' ? 'Control' : part;
    }).join('+');
  }

  function renderKeys(box, keys, keyClass) {
    if (!box) { return; }
    box.textContent = '';
    if (!keys) {
      box.classList.add('is-unbound');
      box.textContent = t('unbound');
      return;
    }
    box.classList.remove('is-unbound');
    splitKeys(keys).forEach(function (part) {
      var key = document.createElement('kbd');
      key.className = keyClass || 'ds-shortcuts__key';
      key.textContent = part;
      box.appendChild(key);
    });
  }

  function updateOutside() {
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-ds-shortcut-aria]'), function (el) {
        var id = el.getAttribute('data-ds-shortcut-aria');
        var keys = keysOfId(id);
        if (keys) {
          el.setAttribute('aria-keyshortcuts', ariaKeys(keys));
        } else {
          el.removeAttribute('aria-keyshortcuts');
        }
      });
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-ds-shortcut-text]'), function (el) {
        var id = el.getAttribute('data-ds-shortcut-text');
        el.textContent = keysOfId(id) || '';
      });
    Array.prototype.forEach.call(
      document.querySelectorAll('[data-ds-shortcut-keys]'), function (el) {
        var id = el.getAttribute('data-ds-shortcut-keys');
        var box = el.querySelector('[data-ds-shortcut-keycaps]') || el;
        renderKeys(box, keysOfId(id),
          box.classList.contains('ds-settings__keycaps') ? 'ds-kbd' : null);
      });
  }

  function idleText() {
    var count = Object.keys(overrides).length;
    if (count > 0) {
      return t('modified').replace('{count}', String(count));
    }
    return t('idle');
  }

  function refreshFooter() {
    if (resetBtn) { resetBtn.disabled = Object.keys(overrides).length === 0; }
    if (!statusActive && statusEl) { statusEl.textContent = idleText(); }
  }

  function setStatus(text) {
    if (!statusEl || !text) { return; }
    window.clearTimeout(statusTimer);
    statusActive = true;
    statusEl.textContent = text;
    statusTimer = window.setTimeout(function () {
      statusActive = false;
      statusEl.textContent = idleText();
    }, 3000);
  }

  function refreshRow(row) {
    if (!editable(row)) { return; }
    var binding = row.querySelector('.ds-shortcuts__binding');
    if (binding && !row.classList.contains('ds-shortcuts__row--editing')) {
      renderKeys(binding, keysOfRow(row));
    }
    var edit = row.querySelector('.ds-shortcuts__edit');
    if (edit) {
      var label = labelOf(row);
      edit.setAttribute('aria-label',
        t('edit-aria').replace('{command}', label));
    }
  }

  function refreshAll() {
    rows.forEach(refreshRow);
    updateOutside();
    refreshFooter();
  }

  /* ---------- 编辑入口 ---------- */

  function installEdit(row) {
    if (!editable(row)) { return; }
    var binding = row.querySelector('.ds-shortcuts__binding');
    if (!binding || row.querySelector('.ds-shortcuts__edit')) { return; }

    var value = document.createElement('span');
    value.className = 'ds-shortcuts__value';
    binding.parentNode.insertBefore(value, binding);

    var edit = document.createElement('button');
    edit.type = 'button';
    edit.className = 'ds-shortcuts__edit';
    edit.setAttribute('aria-haspopup', 'true');
    edit.innerHTML =
      '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">' +
      '<path d="M3 13l1-3 7-7 3 3-7 7-3 1z" stroke="currentColor" ' +
      'stroke-width="1.2" fill="none" stroke-linecap="round"/></svg>';
    edit.addEventListener('click', function (event) {
      event.preventDefault();
      event.stopPropagation();
      openEditor(row);
    });

    value.appendChild(edit);
    value.appendChild(binding);
    row.classList.add('ds-shortcuts__row--editable');
    row.addEventListener('click', function (event) {
      if (editing && editing.row === row) { return; }
      if (event.target.closest('button, a, input, textarea')) { return; }
      openEditor(row);
    });
    refreshRow(row);
  }

  function clearEditorMessage(editor) {
    var message = editor.querySelector('[data-editor-message]');
    var record = editor.querySelector('[data-editor-record]');
    if (message) { message.hidden = true; message.textContent = ''; }
    if (record) { record.removeAttribute('aria-invalid'); }
  }

  function showEditorError(editor, text) {
    var message = editor.querySelector('[data-editor-message]');
    var record = editor.querySelector('[data-editor-record]');
    if (message) { message.hidden = false; message.textContent = text; }
    if (record) { record.setAttribute('aria-invalid', 'true'); }
  }

  function openEditor(row) {
    if (!editable(row) || !editorTemplate) { return; }
    if (editing) {
      if (editing.row === row) { return; }
      closeEditor(false);
    } else {
      stopRecording();
    }
    var binding = row.querySelector('.ds-shortcuts__binding');
    if (!binding) { return; }

    var editor = editorTemplate.content.firstElementChild.cloneNode(true);
    if (!editor) { return; }
    var label = labelOf(row);
    editor.setAttribute('aria-label',
      t('edit-aria').replace('{command}', label));

    var reset = editor.querySelector('[data-editor-reset]');
    var clear = editor.querySelector('[data-editor-clear]');
    var record = editor.querySelector('[data-editor-record]');
    if (clear && !keysOfRow(row)) { clear.hidden = true; }

    reset.addEventListener('click', function (event) {
      event.preventDefault();
      stopRecording();
      resetRow(row);
    });
    clear.addEventListener('click', function (event) {
      event.preventDefault();
      stopRecording();
      clearRow(row);
    });
    record.addEventListener('click', function (event) {
      event.preventDefault();
      startRecording(row, editor, record);
    });
    record.addEventListener('blur', function () {
      if (recording && recording.row === row && !recording.committing) {
        stopRecording();
      }
    });

    var value = binding.parentNode;
    value.appendChild(editor);
    binding.hidden = true;
    row.classList.add('ds-shortcuts__row--editing');

    editing = {
      row: row,
      editor: editor,
      binding: binding,
      record: record,
      edit: row.querySelector('.ds-shortcuts__edit')
    };
    record.focus({ preventScroll: true });
  }

  function closeEditor(focus) {
    if (!editing) { return; }
    stopRecording();
    var state = editing;
    editing = null;
    if (state.editor.parentNode) { state.editor.parentNode.removeChild(state.editor); }
    state.binding.hidden = false;
    state.row.classList.remove('ds-shortcuts__row--editing');
    refreshRow(state.row);
    if (focus && state.edit && document.contains(state.edit)) {
      state.edit.focus({ preventScroll: true });
    }
  }

  /* ---------- 绑定校验（DSH bindingIssue + isWebBindingAllowed 的 Web 口径） ---------- */

  var RESERVED = [
    'Escape', 'Tab', 'Space', 'Backspace', 'Delete',
    'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight',
    'Home', 'End', 'PageUp', 'PageDown', 'Insert'
  ];

  function isLetter(key) {
    return key.length === 1 && key >= 'A' && key <= 'Z';
  }

  function isDigit(key) {
    return key.length === 1 && key >= '0' && key <= '9';
  }

  function isSupportedKey(key) {
    return key.length === 1 || /^F([1-9]|1[0-9]|2[0-4])$/.test(key) ||
      key === 'Enter';
  }

  function bindingIssue(row, keys) {
    var parts = splitKeys(keys);
    var key = parts.pop();
    var modifiers = parts;
    if (!key) { return { code: 'unsupported-key' }; }
    if (!modifiers.length) { return { code: 'modifier-required' }; }
    if (modifiers.indexOf('Meta') !== -1) { return { code: 'reserved' }; }
    if (!isSupportedKey(key)) { return { code: 'unsupported-key' }; }
    if (RESERVED.indexOf(key) !== -1) { return { code: 'reserved' }; }
    if (key === 'Enter' && modifiers.indexOf('Alt') === -1) {
      return { code: 'reserved' };
    }
    if (modifiers.indexOf('Ctrl') !== -1 &&
        ['C', 'V', 'X', 'Z', 'Y', 'Q', 'H'].indexOf(key) !== -1) {
      return { code: 'reserved' };
    }
    if (key === 'A' && modifiers.indexOf('Ctrl') !== -1 &&
        modifiers.indexOf('Shift') === -1) {
      return { code: 'reserved' };
    }
    if (modifiers.indexOf('Alt') !== -1 &&
        ['F2', 'F4'].indexOf(key) !== -1) {
      return { code: 'reserved' };
    }
    if (!webBindingAllowed(modifiers, key)) {
      return { code: 'unsupported-browser' };
    }
    var other = conflictingCommand(row, keys);
    if (other) { return { code: 'conflict', command: other }; }
    return null;
  }

  function webBindingAllowed(modifiers, key) {
    if (modifiers.length >= 3) { return true; }
    if (modifiers.length === 1 && modifiers[0] === 'Ctrl' &&
        [',', '\\', '`', '/'].indexOf(key) !== -1) {
      return true;
    }
    if (modifiers.length === 2 && modifiers.indexOf('Ctrl') !== -1 &&
        (modifiers.indexOf('Alt') !== -1 || modifiers.indexOf('Shift') !== -1)) {
      return true;
    }
    if (modifiers.length === 2 && modifiers[0] === 'Ctrl' &&
        modifiers[1] === 'Shift' && [',', '.'].indexOf(key) !== -1) {
      return true;
    }
    return false;
  }

  function allCommandIds() {
    var ids = Object.keys(rowById);
    Object.keys(globalById).forEach(function (id) {
      if (ids.indexOf(id) === -1) { ids.push(id); }
    });
    return ids;
  }

  function conflictingCommand(row, keys) {
    var self = row.getAttribute('data-shortcut-id');
    var ids = allCommandIds();
    for (var i = 0; i < ids.length; i += 1) {
      if (ids[i] === self) { continue; }
      if (keysOfId(ids[i]) === keys) { return labelOfId(ids[i]); }
    }
    return '';
  }

  function issueText(issue) {
    if (issue.code === 'conflict') {
      return t('conflict').replace('{command}', issue.command);
    }
    if (issue.code === 'modifier-required') { return t('modifier'); }
    if (issue.code === 'unsupported-browser') { return t('unsupported-browser'); }
    if (issue.code === 'unsupported-key') { return t('unsupported-key'); }
    return t('reserved');
  }

  /* ---------- 录制 ---------- */

  function isModifierKey(key) {
    return key === 'Control' || key === 'Alt' || key === 'Shift' ||
      key === 'Meta' || key === 'AltGraph';
  }

  function onRecordKeyDown(event) {
    if (!recording) { return; }
    if (event.key === 'Escape' && !event.ctrlKey && !event.altKey &&
        !event.shiftKey && !event.metaKey) {
      event.preventDefault();
      event.stopPropagation();
      stopRecording();
      return;
    }
    if (event.repeat || event.isComposing || event.keyCode === 229) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    if (event.key === 'Tab' && !event.ctrlKey && !event.altKey &&
        !event.metaKey && !event.shiftKey) {
      return;
    }
    if (!event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      event.stopPropagation();
      recording.button.textContent =
        recording.button.getAttribute('data-record-label') || '';
      showEditorError(recording.editor, t('modifier'));
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    if (isModifierKey(event.key)) {
      recording.button.textContent =
        recording.button.getAttribute('data-record-label') || '';
      return;
    }
    recording.pending = combo(event);
    recording.button.textContent = recording.pending;
    recording.button.removeAttribute('aria-invalid');
    clearEditorMessage(recording.editor);
  }

  function onRecordKeyUp(event) {
    if (!recording || !recording.pending) { return; }
    if (isModifierKey(event.key)) { return; }
    event.preventDefault();
    event.stopPropagation();
    var keys = recording.pending;
    var state = recording;
    recording.pending = null;
    state.committing = true;
    commitBinding(state.row, state.editor, keys);
    if (recording) { recording.committing = false; }
  }

  function startRecording(row, editor, button) {
    stopRecording();
    if (!button.getAttribute('data-record-label')) {
      button.setAttribute('data-record-label', button.textContent);
    }
    button.textContent = button.getAttribute('data-record-label') || '';
    button.removeAttribute('aria-invalid');
    clearEditorMessage(editor);
    recording = {
      row: row,
      editor: editor,
      button: button,
      pending: null,
      committing: false
    };
    window.addEventListener('keydown', onRecordKeyDown, true);
    window.addEventListener('keyup', onRecordKeyUp, true);
    button.classList.add('is-recording');
  }

  function stopRecording() {
    if (!recording) { return; }
    window.removeEventListener('keydown', onRecordKeyDown, true);
    window.removeEventListener('keyup', onRecordKeyUp, true);
    if (recording.button) {
      recording.button.classList.remove('is-recording');
      recording.button.textContent =
        recording.button.getAttribute('data-record-label') || '';
    }
    recording = null;
  }

  /* ---------- 提交 / 重置 ---------- */

  function saveOverride(id, value, remove) {
    var previous = overrides[id];
    var had = own(overrides, id);
    if (remove) {
      delete overrides[id];
    } else {
      overrides[id] = value;
    }
    if (writeStore()) { return true; }
    if (had) {
      overrides[id] = previous;
    } else {
      delete overrides[id];
    }
    return false;
  }

  function commitBinding(row, editor, keys) {
    var issue = bindingIssue(row, keys);
    if (issue) {
      showEditorError(editor, issueText(issue));
      stopRecording();
      var record = editor.querySelector('[data-editor-record]');
      if (record) { record.focus({ preventScroll: true }); }
      return;
    }
    var id = row.getAttribute('data-shortcut-id');
    if (!saveOverride(id, keys, false)) {
      showEditorError(editor, t('write-failed'));
      stopRecording();
      return;
    }
    stopRecording();
    closeEditor(true);
    refreshAll();
    setStatus(t('saved'));
  }

  function resetRow(row) {
    var id = row.getAttribute('data-shortcut-id');
    if (!hasOverride(id)) {
      closeEditor(true);
      return;
    }
    if (!saveOverride(id, null, true)) {
      var editor = editing ? editing.editor : null;
      if (editor) { showEditorError(editor, t('write-failed')); }
      return;
    }
    closeEditor(true);
    refreshAll();
    setStatus(t('reset'));
  }

  function clearRow(row) {
    var id = row.getAttribute('data-shortcut-id');
    var had = hasOverride(id);
    var previous = overrides[id];
    if (had && previous === null) {
      closeEditor(true);
      return;
    }
    if (!saveOverride(id, null, false)) {
      var editor = editing ? editing.editor : null;
      if (editor) { showEditorError(editor, t('write-failed')); }
      return;
    }
    closeEditor(true);
    refreshAll();
    setStatus(t('cleared'));
  }

  function showResetConfirm() {
    if (confirmingReset) { return; }
    closeEditor(false);
    stopRecording();
    confirmingReset = true;
    if (footerMain) { footerMain.hidden = true; }
    if (footerActions) { footerActions.hidden = true; }
    if (footerConfirm) { footerConfirm.hidden = false; }
    if (confirmResetBtn) { confirmResetBtn.focus({ preventScroll: true }); }
  }

  function hideResetConfirm() {
    confirmingReset = false;
    if (footerMain) { footerMain.hidden = false; }
    if (footerActions) { footerActions.hidden = false; }
    if (footerConfirm) { footerConfirm.hidden = true; }
    if (resetBtn) { resetBtn.focus({ preventScroll: true }); }
  }

  function resetAll() {
    var previous = overrides;
    overrides = {};
    if (!writeStore()) {
      overrides = previous;
      hideResetConfirm();
      setStatus(t('reset-failed'));
      return;
    }
    hideResetConfirm();
    refreshAll();
    setStatus(t('reset-all-saved'));
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
      var keys = editable(row) ? keysOfRow(row) : defaultKeys(row);
      var hay = ((label ? label.textContent : '') + ' ' + keys).toLowerCase();
      var hit = !q || subsequence(q, hay);
      row.hidden = !hit;
      if (hit) { shown += 1; }
    });
    if (empty) { empty.hidden = shown > 0; }
    if (clearBtn) { clearBtn.hidden = !q; }
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

  /* ---------- 开合 ---------- */

  function isOpen() { return !dialog.hasAttribute('hidden'); }

  function modalBehind() {
    var settings = document.querySelector('.ds-settings:not([hidden])');
    return !!settings;
  }

  function open(trigger) {
    if (isOpen()) { return; }
    lastTrigger = trigger || document.activeElement;
    reloadFromStore();
    window.clearTimeout(statusTimer);
    statusActive = false;
    refreshAll();
    dialog.removeAttribute('hidden');
    dialog.setAttribute('aria-hidden', 'false');
    document.body.classList.add('ds-modal-open');
    if (panel) { panel.focus({ preventScroll: true }); }
    if (search) {
      search.value = '';
      applySearch();
      search.focus({ preventScroll: true });
    }
  }

  function close() {
    if (!isOpen()) { return; }
    closeEditor(false);
    stopRecording();
    hideResetConfirm();
    dialog.setAttribute('hidden', '');
    dialog.setAttribute('aria-hidden', 'true');
    if (!modalBehind()) {
      document.body.classList.remove('ds-modal-open');
    }
    var back = lastTrigger && document.contains(lastTrigger)
      ? lastTrigger : document.querySelector('[data-ds-account-trigger]');
    if (back && back.focus) { back.focus({ preventScroll: true }); }
  }

  function toggle(trigger) {
    if (isOpen()) { close(); } else { open(trigger); }
  }

  /* ---------- 按键分发 ---------- */

  function combo(event) {
    var parts = [];
    if (event.ctrlKey) { parts.push('Ctrl'); }
    if (event.altKey) { parts.push('Alt'); }
    if (event.shiftKey) { parts.push('Shift'); }
    if (event.metaKey) { parts.push('Meta'); }
    var key = event.key;
    if (!key) { return ''; }
    if (isLetter(key.toUpperCase())) { key = key.toUpperCase(); }
    if (key === ' ') { key = 'Space'; }
    parts.push(key);
    return parts.join('+');
  }

  function runAction(row) {
    var action = row.getAttribute('data-shortcut-action');
    var url = row.getAttribute('data-shortcut-url');
    if (action === 'settings') {
      var settings = document.getElementById('ds-settings');
      if (settings && !settings.hasAttribute('hidden')) {
        close();
        return true;
      }
      var opener = document.querySelector('[data-ds-settings-open]');
      if (opener) { close(); opener.click(); return true; }
      return false;
    }
    if (action === 'shortcuts') {
      toggle(null);
      return true;
    }
    if (action === 'sidebar') {
      if (document.body.classList.contains('ds-modal-open')) { return false; }
      var railToggle = document.querySelector('[data-ds-rail-toggle]');
      if (railToggle) { railToggle.click(); return true; }
      return false;
    }
    if (url) {
      if (document.body.classList.contains('ds-modal-open')) { return false; }
      window.location.assign(url);
      return true;
    }
    return false;
  }

  function findRow(keys) {
    for (var i = 0; i < rows.length; i += 1) {
      var row = rows[i];
      if (!editable(row)) { continue; }
      if (keysOfRow(row) === keys) { return row; }
    }
    return null;
  }

  document.addEventListener('keydown', function (event) {
    if (event.defaultPrevented || event.repeat) { return; }
    if (event.isComposing || event.keyCode === 229) { return; }
    if (recording) { return; }

    if (event.key === 'Escape') {
      if (editing) {
        event.preventDefault();
        event.stopPropagation();
        closeEditor(true);
        return;
      }
      if (isOpen()) {
        event.preventDefault();
        event.stopPropagation();
        close();
        return;
      }
    }

    var keys = combo(event);
    if (!keys) { return; }
    if (!event.ctrlKey && !event.altKey && !event.metaKey) { return; }

    var row = findRow(keys);
    if (!row) { return; }
    if (runAction(row)) {
      event.preventDefault();
      event.stopPropagation();
    }
  }, true);

  /* ---------- 初始化 ---------- */

  rows.forEach(function (row) {
    var id = row.getAttribute('data-shortcut-id');
    if (id) { rowById[id] = row; }
    installEdit(row);
    refreshRow(row);
  });
  Array.prototype.forEach.call(
    dialog.querySelectorAll('[data-shortcut-global-id]'), function (el) {
      globalById[el.getAttribute('data-shortcut-global-id')] = el;
    });

  Array.prototype.forEach.call(
    document.querySelectorAll('[data-ds-shortcuts-open]'), function (el) {
      el.addEventListener('click', function (event) {
        event.preventDefault();
        open(el);
      });
    });
  Array.prototype.forEach.call(
    dialog.querySelectorAll('[data-ds-shortcuts-close]'), function (el) {
      el.addEventListener('click', close);
    });

  if (search) { search.addEventListener('input', applySearch); }
  if (clearBtn) {
    clearBtn.addEventListener('click', function () {
      if (search) { search.value = ''; applySearch(); search.focus(); }
    });
  }
  if (resetBtn) { resetBtn.addEventListener('click', showResetConfirm); }
  if (cancelResetBtn) { cancelResetBtn.addEventListener('click', hideResetConfirm); }
  if (confirmResetBtn) { confirmResetBtn.addEventListener('click', resetAll); }

  window.addEventListener('storage', function (event) {
    if (event.key !== STORAGE_KEY) { return; }
    reloadFromStore();
    if (editing) { closeEditor(false); }
    refreshAll();
    applySearch();
  });

  refreshAll();
  applySearch();
})();
