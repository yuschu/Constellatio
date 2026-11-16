/* 会话列表右击菜单：对齐 DSH 0.2.2 ui-workspace 的 session context menu。
 *
 * 入口：会话行 contextmenu、行内「更多」按钮。菜单项按 DSH 顺序：
 * 置顶/取消置顶 → 重命名 → 复制 Session ID → 归档/取消归档。
 * DSH 的「分叉会话」需要会话级分支协议，本项目没有对应后端，不画假菜单项。
 *
 * 服务端动作走 /plugins/assistant/conversations/<id>/action/，返回 JSON；
 * 成功后就地改行/排序，不跳页。列表顺序沿用服务端口径：置顶优先，再按
 * `updated_at` 倒序；改名/置顶/归档不刷新 `updated_at`，不会把旧会话顶到最前。
 */
(function () {
  'use strict';

  var menu = document.getElementById('as-session-menu');
  if (!menu) {
    return;
  }

  var tree = document.querySelector('.as-tree');
  var activeList = document.querySelector('[data-as-session-list]');
  var archivedList = document.querySelector('[data-as-archived-list]');
  var archivedBlock = document.querySelector('[data-as-archived-block]');
  var archivedToggle = document.querySelector('[data-as-archived-toggle]');
  var archivedCount = document.querySelector('[data-as-archived-count]');
  var i18n = document.querySelector('[data-as-session-i18n]');
  var toast = document.querySelector('[data-as-session-toast]');
  var renameRoot = document.querySelector('[data-as-rename]');
  var renamePanel = renameRoot && renameRoot.querySelector('.as-rename__panel');
  var renameInput = renameRoot && renameRoot.querySelector('[data-as-rename-input]');
  var renameError = renameRoot && renameRoot.querySelector('[data-as-rename-error]');
  var renameConfirm = renameRoot && renameRoot.querySelector('[data-as-rename-confirm]');
  var renameCancelButtons = renameRoot
    ? renameRoot.querySelectorAll('[data-as-rename-cancel]') : [];

  var currentRow = null;
  var currentOpener = null;
  var renameRow = null;
  var renameOpener = null;
  var renaming = false;
  var composing = false;
  var toastTimer = null;

  function msg(name, fallback) {
    return (i18n && i18n.getAttribute('data-msg-' + name)) || fallback || '';
  }

  function label(name, fallback) {
    return (i18n && i18n.getAttribute('data-label-' + name)) || fallback || '';
  }

  function csrfToken() {
    var input = document.querySelector('input[name=csrfmiddlewaretoken]');
    return input ? input.value : '';
  }

  function isMenuOpen() {
    return !menu.hasAttribute('hidden');
  }

  function rowLink(row) {
    return row ? row.querySelector('.as-session-link') : null;
  }

  function rowTrigger(row) {
    return row ? row.querySelector('[data-as-session-more]') : null;
  }

  function menuItems() {
    return Array.prototype.filter.call(
      menu.querySelectorAll('[role=menuitem]'),
      function (item) { return !item.hidden; });
  }

  function showToast(text) {
    if (!toast) {
      return;
    }
    if (toastTimer) {
      window.clearTimeout(toastTimer);
    }
    toast.textContent = text;
    toast.removeAttribute('hidden');
    toastTimer = window.setTimeout(function () {
      toast.setAttribute('hidden', '');
      toastTimer = null;
    }, 2400);
  }

  function requestAction(row, action, extra) {
    var body = new URLSearchParams();
    body.set('action', action);
    if (extra) {
      Object.keys(extra).forEach(function (key) {
        body.set(key, extra[key]);
      });
    }
    return fetch(row.getAttribute('data-session-action-url'), {
      method: 'POST',
      credentials: 'same-origin',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8',
        'X-CSRFToken': csrfToken()
      },
      body: body.toString()
    }).then(function (response) {
      return response.text().then(function (text) {
        var data = null;
        try {
          data = JSON.parse(text);
        } catch (error) {
          data = null;
        }
        if (!response.ok || !data || !data.ok) {
          throw new Error((data && data.error) || msg('action-failed', '操作失败，请重试'));
        }
        return data;
      });
    });
  }

  function placeMenu(x, y) {
    var edge = 8;
    // .ds-menu 外层只是定位壳，实际条目在 .ds-menu__list 里；外层 offsetHeight
    // 只有材质边的 8px，直接量会把贴底弹出的菜单算出视口。
    var surface = menu.querySelector('.ds-menu__list');
    var width = menu.offsetWidth;
    var height = (surface ? surface.offsetHeight : menu.offsetHeight) + 8;
    var viewportWidth = document.documentElement.clientWidth;
    var viewportHeight = document.documentElement.clientHeight;
    var left = x;
    var top = y;

    if (left + width > viewportWidth - edge) {
      left = x - width;
    }
    if (top + height > viewportHeight - edge) {
      top = y - height;
    }
    left = Math.max(edge, Math.min(left, viewportWidth - width - edge));
    top = Math.max(edge, Math.min(top, viewportHeight - height - edge));
    menu.style.left = Math.round(left) + 'px';
    menu.style.top = Math.round(top) + 'px';
  }

  function openMenu(row, x, y, opener) {
    if (currentRow && currentRow !== row) {
      closeMenu(false);
    }
    currentRow = row;
    currentOpener = opener || rowTrigger(row) || rowLink(row);
    var archived = row.getAttribute('data-session-archived') === '1';
    var pinned = row.getAttribute('data-session-pinned') === '1';

    var pinItem = menu.querySelector('[data-session-menu-action=pin]');
    var pinLabel = pinItem.querySelector('[data-session-menu-label]');
    pinItem.hidden = archived;
    pinLabel.textContent = pinned
      ? pinItem.getAttribute('data-i18n-unpin')
      : pinItem.getAttribute('data-i18n-pin');

    var archiveItem = menu.querySelector('[data-session-menu-action=archive]');
    var archiveLabel = archiveItem.querySelector('[data-session-menu-label]');
    archiveLabel.textContent = archived
      ? archiveItem.getAttribute('data-i18n-unarchive')
      : archiveItem.getAttribute('data-i18n-archive');

    row.classList.add('is-menu-open');
    if (currentOpener && currentOpener.hasAttribute('aria-haspopup')) {
      currentOpener.setAttribute('aria-expanded', 'true');
    }

    menu.style.visibility = 'hidden';
    menu.removeAttribute('hidden');
    placeMenu(x, y);
    menu.style.visibility = '';

    var items = menuItems();
    if (items.length) {
      items[0].focus({ preventScroll: true });
    }
  }

  function closeMenu(refocus) {
    if (!isMenuOpen()) {
      return;
    }
    menu.setAttribute('hidden', '');
    menu.style.left = '';
    menu.style.top = '';
    if (currentRow) {
      currentRow.classList.remove('is-menu-open');
    }
    if (currentOpener && currentOpener.hasAttribute('aria-haspopup')) {
      currentOpener.setAttribute('aria-expanded', 'false');
    }
    if (refocus && currentOpener && currentOpener.isConnected) {
      currentOpener.focus({ preventScroll: true });
    }
    currentRow = null;
    currentOpener = null;
  }

  function ensureActiveList() {
    if (activeList) {
      return activeList;
    }
    activeList = document.createElement('ul');
    activeList.className = 'as-session-list';
    activeList.setAttribute('data-as-session-list', '');
    if (tree) {
      tree.insertBefore(activeList, archivedBlock || tree.firstChild);
    }
    return activeList;
  }

  function sortList(list) {
    if (!list) {
      return;
    }
    var rows = Array.prototype.slice.call(
      list.querySelectorAll('[data-session-row]'));
    rows.sort(function (left, right) {
      var leftPinned = left.getAttribute('data-session-pinned') === '1' ? 1 : 0;
      var rightPinned = right.getAttribute('data-session-pinned') === '1' ? 1 : 0;
      if (leftPinned !== rightPinned) {
        return rightPinned - leftPinned;
      }
      var leftTime = Number(left.getAttribute('data-session-updated')) || 0;
      var rightTime = Number(right.getAttribute('data-session-updated')) || 0;
      return rightTime - leftTime;
    });
    rows.forEach(function (row) { list.appendChild(row); });
  }

  function syncEmptyHint() {
    if (!tree) {
      return;
    }
    var hasRows = !!(activeList && activeList.children.length);
    var hint = tree.querySelector('.as-tree__hint');
    if (!hint && !hasRows) {
      hint = document.createElement('p');
      hint.className = 'as-tree__hint';
      hint.textContent = msg('empty', '还没有会话');
      tree.insertBefore(hint, archivedBlock || null);
    }
    if (hint) {
      hint.hidden = hasRows;
    }
  }

  function updateArchivedUI() {
    var count = archivedList
      ? archivedList.querySelectorAll('[data-session-row]').length : 0;
    if (archivedCount) {
      archivedCount.textContent = String(count);
    }
    if (archivedToggle) {
      archivedToggle.hidden = count === 0;
      if (count === 0) {
        archivedToggle.setAttribute('aria-expanded', 'false');
      }
    }
    if (archivedBlock) {
      archivedBlock.hidden = count === 0;
    }
    if (archivedList && count === 0) {
      archivedList.hidden = true;
    }
  }

  function pinIcon() {
    var span = document.createElement('span');
    span.className = 'as-session-pin';
    span.setAttribute('role', 'img');
    span.setAttribute('aria-label', label('pinned', '已置顶'));
    span.innerHTML = '<svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true">'
      + '<path d="M9.2 2.1l4.7 4.7-1.5 1.5-1.1-.3-2.2 2.2.4 1.8-1 1-2.4-2.4-2.6 2.6-.8-.8 2.6-2.6-2.4-2.4 1-1 1.8.4 2.2-2.2-.3-1.1 1.5-1.5z"'
      + ' fill="none" stroke="currentColor" stroke-width="1.2"/></svg>';
    return span;
  }

  function setPinnedVisual(row, pinned) {
    var link = rowLink(row);
    if (!link) {
      return;
    }
    var existing = link.querySelector('.as-session-pin');
    if (pinned && !existing) {
      link.insertBefore(pinIcon(), link.firstChild);
    } else if (!pinned && existing) {
      existing.parentNode.removeChild(existing);
    }
  }

  function setArchivedLink(row, archived) {
    var link = rowLink(row);
    if (!link) {
      return;
    }
    if (archived) {
      link.removeAttribute('href');
      link.setAttribute('aria-disabled', 'true');
      link.setAttribute('tabindex', '-1');
    } else {
      link.setAttribute('href', '/?conversation=' + row.getAttribute('data-session-id'));
      link.removeAttribute('aria-disabled');
      link.removeAttribute('tabindex');
    }
  }

  function focusRowAction(row) {
    var trigger = rowTrigger(row);
    if (trigger && trigger.isConnected && trigger.offsetParent !== null) {
      trigger.focus({ preventScroll: true });
    }
  }

  function doPin(row) {
    var pinning = row.getAttribute('data-session-pinned') !== '1';
    requestAction(row, pinning ? 'pin' : 'unpin').then(function () {
      row.setAttribute('data-session-pinned', pinning ? '1' : '0');
      setPinnedVisual(row, pinning);
      sortList(activeList);
      showToast(pinning ? msg('pinned', '会话已置顶') : msg('unpinned', '会话已取消置顶'));
      focusRowAction(row);
    }).catch(function (error) {
      showToast(error.message || msg('action-failed', '操作失败，请重试'));
      focusRowAction(row);
    });
  }

  function doArchive(row) {
    var archiving = row.getAttribute('data-session-archived') !== '1';
    requestAction(row, archiving ? 'archive' : 'unarchive').then(function () {
      row.setAttribute('data-session-archived', archiving ? '1' : '0');
      row.classList.toggle('is-archived', archiving);
      setArchivedLink(row, archiving);
      if (archiving) {
        row.setAttribute('data-session-pinned', '0');
        setPinnedVisual(row, false);
        archivedList.appendChild(row);
        sortList(archivedList);
        syncEmptyHint();
        updateArchivedUI();
        if (row.classList.contains('is-active')) {
          window.location.assign('/');
          return;
        }
        if (archivedToggle && !archivedToggle.hidden) {
          archivedToggle.focus({ preventScroll: true });
        }
        showToast(msg('archived', '会话已归档'));
      } else {
        var list = ensureActiveList();
        list.appendChild(row);
        sortList(list);
        syncEmptyHint();
        updateArchivedUI();
        showToast(msg('unarchived', '会话已取消归档'));
        focusRowAction(row);
      }
    }).catch(function (error) {
      showToast(error.message || msg('action-failed', '操作失败，请重试'));
      focusRowAction(row);
    });
  }

  function copySessionId(row) {
    var id = row.getAttribute('data-session-id') || '';
    function done() {
      showToast(msg('copied', 'Session ID 已复制'));
      focusRowAction(row);
    }
    function failed() {
      showToast(msg('copy-failed', '复制失败，请手动复制 Session ID'));
      focusRowAction(row);
    }
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(id).then(done).catch(function () {
        legacyCopy(id) ? done() : failed();
      });
      return;
    }
    legacyCopy(id) ? done() : failed();
  }

  function legacyCopy(text) {
    var area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.top = '-1000px';
    document.body.appendChild(area);
    area.select();
    var ok = false;
    try {
      ok = document.execCommand('copy');
    } catch (error) {
      ok = false;
    }
    document.body.removeChild(area);
    return ok;
  }

  function updateRenameState() {
    var value = renameInput.value.trim();
    renameConfirm.disabled = renaming || value === '';
  }

  function openRename(row) {
    renameRow = row;
    renameOpener = rowTrigger(row) || rowLink(row);
    renameInput.disabled = false;
    renameCancelButtons.forEach(function (button) {
      button.disabled = false;
    });
    renameInput.value = row.getAttribute('data-session-title') || '';
    renameError.textContent = '';
    renameError.setAttribute('hidden', '');
    renameRoot.removeAttribute('hidden');
    document.body.classList.add('ds-modal-open');
    renaming = false;
    updateRenameState();
    renameInput.focus();
    renameInput.select();
  }

  function closeRename(refocus) {
    if (renaming || renameRoot.hasAttribute('hidden')) {
      return;
    }
    renameRoot.setAttribute('hidden', '');
    document.body.classList.remove('ds-modal-open');
    if (refocus && renameOpener && renameOpener.isConnected) {
      renameOpener.focus({ preventScroll: true });
    }
    renameRow = null;
    renameOpener = null;
  }

  function confirmRename() {
    if (renaming || !renameRow) {
      return;
    }
    var title = renameInput.value.trim();
    if (!title) {
      return;
    }
    renaming = true;
    renameInput.disabled = true;
    renameConfirm.disabled = true;
    renameCancelButtons.forEach(function (button) {
      button.disabled = true;
    });
    renamePanel.setAttribute('aria-busy', 'true');

    requestAction(renameRow, 'rename', { title: title }).then(function (data) {
      var row = renameRow;
      var titleNode = row && row.querySelector('.as-session-title');
      if (titleNode) {
        titleNode.textContent = data.title;
      }
      if (row) {
        row.setAttribute('data-session-title', data.title);
      }
      renaming = false;
      renameCancelButtons.forEach(function (button) {
        button.disabled = false;
      });
      renameInput.disabled = true;
      renamePanel.removeAttribute('aria-busy');
      closeRename(true);
    }).catch(function (error) {
      renaming = false;
      renameCancelButtons.forEach(function (button) {
        button.disabled = false;
      });
      renameInput.disabled = false;
      renamePanel.removeAttribute('aria-busy');
      renameError.textContent = error.message || msg('action-failed', '操作失败，请重试');
      renameError.removeAttribute('hidden');
      updateRenameState();
      renameInput.focus();
    });
  }

  function toggleArchived() {
    if (!archivedList || !archivedToggle) {
      return;
    }
    var expanded = archivedToggle.getAttribute('aria-expanded') === 'true';
    archivedToggle.setAttribute('aria-expanded', expanded ? 'false' : 'true');
    archivedList.hidden = expanded;
  }

  Array.prototype.forEach.call(
    document.querySelectorAll('[data-session-row]'),
    function (row) {
      row.addEventListener('contextmenu', function (event) {
        event.preventDefault();
        openMenu(row, event.clientX, event.clientY, rowTrigger(row) || rowLink(row));
      });
      var more = rowTrigger(row);
      if (more) {
        more.addEventListener('click', function (event) {
          event.preventDefault();
          event.stopPropagation();
          if (isMenuOpen() && currentRow === row) {
            closeMenu(true);
            return;
          }
          var rect = more.getBoundingClientRect();
          openMenu(row, rect.left, rect.bottom + 4, more);
        });
      }
      var link = rowLink(row);
      if (link && row.getAttribute('data-session-archived') === '1') {
        link.addEventListener('click', function (event) {
          event.preventDefault();
        });
      }
    });

  menu.addEventListener('mousedown', function (event) {
    event.stopPropagation();
  });

  menu.addEventListener('click', function (event) {
    var item = event.target.closest('[role=menuitem]');
    if (!item || !currentRow) {
      return;
    }
    var action = item.getAttribute('data-session-menu-action');
    var row = currentRow;
    if (action === 'rename') {
      closeMenu(false);
      openRename(row);
      return;
    }
    closeMenu(true);
    if (action === 'pin') {
      doPin(row);
    } else if (action === 'archive') {
      doArchive(row);
    } else if (action === 'copy') {
      copySessionId(row);
    }
  });

  menu.addEventListener('keydown', function (event) {
    var items = menuItems();
    var index = items.indexOf(document.activeElement);
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      items[(index + 1) % items.length].focus();
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      items[(index - 1 + items.length) % items.length].focus();
    } else if (event.key === 'Home') {
      event.preventDefault();
      items[0].focus();
    } else if (event.key === 'End') {
      event.preventDefault();
      items[items.length - 1].focus();
    } else if (event.key === 'Tab') {
      event.preventDefault();
      closeMenu(true);
    } else if (event.key === 'Escape') {
      event.preventDefault();
      closeMenu(true);
    }
  });

  document.addEventListener('mousedown', function (event) {
    if (isMenuOpen() && !menu.contains(event.target)) {
      closeMenu(false);
    }
  });

  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') {
      return;
    }
    // 捕获阶段先处理浮层，并截断事件：ds-shell 的抽屉 Esc 监听在冒泡阶段，
    // 否则窄屏抽屉里按 Esc 会同时关掉菜单和抽屉。
    if (isMenuOpen()) {
      event.preventDefault();
      closeMenu(true);
      event.stopPropagation();
      return;
    }
    if (renameRoot && !renameRoot.hasAttribute('hidden')) {
      event.preventDefault();
      closeRename(true);
      event.stopPropagation();
    }
  }, true);

  window.addEventListener('resize', function () { closeMenu(false); });
  window.addEventListener('scroll', function () { closeMenu(false); }, true);
  window.addEventListener('blur', function () { closeMenu(false); });

  document.addEventListener('contextmenu', function (event) {
    if (isMenuOpen() && !event.target.closest('[data-session-row]')) {
      closeMenu(false);
    }
  });

  if (renameRoot) {
    Array.prototype.forEach.call(renameCancelButtons, function (button) {
      button.addEventListener('click', function () { closeRename(true); });
    });
    var overlay = renameRoot.querySelector('[data-as-rename-overlay]');
    if (overlay) {
      overlay.addEventListener('click', function () { closeRename(true); });
    }
    renameInput.addEventListener('input', function () {
      renameError.textContent = '';
      renameError.setAttribute('hidden', '');
      updateRenameState();
    });
    renameInput.addEventListener('compositionstart', function () { composing = true; });
    renameInput.addEventListener('compositionend', function () { composing = false; });
    renameInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' && !composing) {
        event.preventDefault();
        confirmRename();
      }
    });
    renameConfirm.addEventListener('click', confirmRename);
    renamePanel.addEventListener('keydown', function (event) {
      if (event.key !== 'Tab') {
        return;
      }
      var focusable = Array.prototype.filter.call(
        renamePanel.querySelectorAll('button, input'),
        function (item) { return !item.disabled && item.offsetParent !== null; });
      if (!focusable.length) {
        return;
      }
      var index = focusable.indexOf(document.activeElement);
      event.preventDefault();
      if (event.shiftKey) {
        focusable[(index - 1 + focusable.length) % focusable.length].focus();
      } else {
        focusable[(index + 1) % focusable.length].focus();
      }
    });
  }

  if (archivedToggle) {
    archivedToggle.addEventListener('click', toggleArchived);
  }

  updateArchivedUI();
})();
