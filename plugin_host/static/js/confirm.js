// 确认弹窗：把「停用 / 物理删除 / 禁用 / 冻结权限」这类破坏性操作的原生
// 浏览器确认框换成 DSH 的 Modal 确认弹窗。样式见 corporate-clean.css 第 32 节，
// 字面量取自 @deepseek-ai/dsh-web-frontend 的 Modal 模块与
// dsh-client-ui-schedule 的 confirmDialog / confirmPrompt / confirmActions。
//
// 为什么仍然走外部脚本：onclick 属于 script-src 的内联执行面，CSP 不给
// 'unsafe-inline'，确认逻辑只能放在外部文件里；弹窗文案从 #ds-confirm-labels 读，
// 保证 {% trans %} 仍然生效，脚本里不写死中文。
//
// 支持三种写法（历史原因，站内都有）：
//   1) <button type="submit" data-confirm="…">          —— 提交按钮上
//   2) <form data-confirm="…">                          —— 表单上（approval_list 的删除按钮）
//   3) 表单内任意元素带 data-confirm                     —— 兜底
// 行为判据：① 点这些按钮弹的是 DSH 弹窗而不是系统灰框；② 取消 = 不提交；
//          ③ Esc / 遮罩 / 关闭 / 取消 都能退出，确认后沿用原 submitter 真正提交。
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

  function labels() {
    var node = document.getElementById('ds-confirm-labels');
    return {
      title: (node && node.getAttribute('data-title')) || 'Confirm',
      cancel: (node && node.getAttribute('data-cancel')) || 'Cancel',
      confirm: (node && node.getAttribute('data-confirm')) || 'OK',
      close: (node && node.getAttribute('data-close')) || 'Close'
    };
  }

  var dialog = null;
  var pending = null;      // { form, submitter }
  var resubmitting = false;
  var lastFocused = null;

  function build() {
    var copy = labels();
    var root = document.createElement('div');
    root.className = 'ds-modal';
    root.id = 'ds-confirm';
    root.setAttribute('hidden', '');

    var mask = document.createElement('div');
    mask.className = 'ds-modal__mask';
    mask.setAttribute('data-ds-confirm-dismiss', '');

    var panel = document.createElement('div');
    panel.className = 'ds-modal__dialog';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-labelledby', 'ds-confirm-title');
    panel.setAttribute('tabindex', '-1');

    var content = document.createElement('div');
    content.className = 'ds-modal__content';

    var header = document.createElement('div');
    header.className = 'ds-modal__header';

    var title = document.createElement('h2');
    title.className = 'ds-modal__title';
    title.id = 'ds-confirm-title';
    title.textContent = copy.title;

    var close = document.createElement('button');
    close.className = 'ds-modal__close';
    close.type = 'button';
    close.setAttribute('aria-label', copy.close);
    close.setAttribute('data-ds-confirm-dismiss', '');
    close.textContent = '✕';

    var description = document.createElement('p');
    description.className = 'ds-modal__description';
    description.id = 'ds-confirm-message';

    var footer = document.createElement('div');
    footer.className = 'ds-modal__footer';

    var cancel = document.createElement('button');
    cancel.className = 'r-btn';
    cancel.type = 'button';
    cancel.setAttribute('data-ds-confirm-cancel', '');
    cancel.setAttribute('data-modal-autofocus', '');
    cancel.textContent = copy.cancel;

    var ok = document.createElement('button');
    ok.className = 'r-btn';
    ok.type = 'button';
    ok.setAttribute('data-ds-confirm-ok', '');
    ok.textContent = copy.confirm;

    header.appendChild(title);
    header.appendChild(close);
    content.appendChild(header);
    content.appendChild(description);
    footer.appendChild(cancel);
    footer.appendChild(ok);
    panel.appendChild(content);
    panel.appendChild(footer);
    root.appendChild(mask);
    root.appendChild(panel);

    root.addEventListener('click', function (event) {
      var node = event.target;
      if (node.hasAttribute && node.hasAttribute('data-ds-confirm-dismiss')) {
        close_dialog();
      } else if (node.hasAttribute && node.hasAttribute('data-ds-confirm-cancel')) {
        close_dialog();
      } else if (node.hasAttribute && node.hasAttribute('data-ds-confirm-ok')) {
        var job = pending;
        close_dialog();
        if (job) {
          resubmitting = true;
          if (job.form.requestSubmit) {
            job.form.requestSubmit(job.submitter || undefined);
          } else {
            job.form.submit();
          }
          resubmitting = false;
        }
      }
    });

    document.body.appendChild(root);
    return root;
  }

  function open_dialog(message, job) {
    if (!dialog) {
      dialog = build();
    }
    pending = job;
    lastFocused = document.activeElement;
    dialog.querySelector('.ds-modal__description').textContent = message;
    dialog.removeAttribute('hidden');
    var cancel = dialog.querySelector('[data-ds-confirm-cancel]');
    if (cancel) {
      cancel.focus();
    }
  }

  function close_dialog() {
    if (!dialog) {
      return;
    }
    dialog.setAttribute('hidden', '');
    pending = null;
    if (lastFocused && lastFocused.focus) {
      lastFocused.focus();
    }
    lastFocused = null;
  }

  document.addEventListener('keydown', function (event) {
    if (event.key === 'Escape' && dialog && !dialog.hasAttribute('hidden')) {
      event.preventDefault();
      close_dialog();
    }
  }, true);

  document.addEventListener('submit', function (event) {
    if (resubmitting) {
      return;
    }
    var message = messageFor(event);
    if (!message) {
      return;
    }
    event.preventDefault();      // 先拦住，等弹窗里点「确认」再真正提交
    open_dialog(message, { form: event.target, submitter: event.submitter || null });
  }, true);
})();
