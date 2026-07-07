(function () {
  function reindexList(container, itemSelector, namePrefix) {
    container.querySelectorAll(itemSelector).forEach(function (item, index) {
      item.querySelectorAll('[name]').forEach(function (el) {
        el.name = el.name.replace(/\[\d+\]/, '[' + index + ']');
      });
      var label = item.querySelector('[data-item-label]');
      if (label) {
        var labelPrefix = container.getAttribute('data-label-prefix') || 'Kart';
        label.textContent = labelPrefix + ' ' + (index + 1);
      }
      item.querySelectorAll('[data-member-index]').forEach(function (el) {
        el.setAttribute('data-member-index', String(index));
      });
      item.querySelectorAll('[data-step-index]').forEach(function (el) {
        el.setAttribute('data-step-index', String(index));
      });
    });
  }

  document.querySelectorAll('[data-sort-up]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item = btn.closest('[data-sortable-item]');
      var prev = item && item.previousElementSibling;
      if (item && prev) {
        item.parentNode.insertBefore(item, prev);
        var container = item.parentNode;
        var prefix = container.getAttribute('data-sortable-prefix');
        if (prefix) {
          reindexList(container, '[data-sortable-item]', prefix);
        }
      }
    });
  });

  document.querySelectorAll('[data-sort-down]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item = btn.closest('[data-sortable-item]');
      var next = item && item.nextElementSibling;
      if (item && next) {
        item.parentNode.insertBefore(next, item);
        var container = item.parentNode;
        var prefix = container.getAttribute('data-sortable-prefix');
        if (prefix) {
          reindexList(container, '[data-sortable-item]', prefix);
        }
      }
    });
  });

  document.querySelectorAll('[data-add-service]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var container = document.getElementById('services-list');
      var items = container.querySelectorAll('[data-sortable-item]');
      var index = items.length;
      var tpl = document.getElementById('service-item-template');
      if (!tpl || !container) return;
      var clone = tpl.content.cloneNode(true);
      clone.querySelectorAll('[name]').forEach(function (el) {
        el.name = el.name.replace('__INDEX__', String(index));
      });
      container.appendChild(clone);
    });
  });

  document.querySelectorAll('[data-remove-item]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var item = btn.closest('[data-sortable-item]');
      var container = item && item.parentNode;
      if (!item || !container) {
        return;
      }
      var minItems = container.hasAttribute('data-allow-empty') ? 0 : 1;
      if (container.querySelectorAll('[data-sortable-item]').length > minItems) {
        item.remove();
        var prefix = container.getAttribute('data-sortable-prefix');
        if (prefix) {
          reindexList(container, '[data-sortable-item]', prefix);
        }
      }
    });
  });

  document.querySelectorAll('[data-add-team]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var container = document.getElementById('team-list');
      var index = container.querySelectorAll('[data-sortable-item]').length;
      var tpl = document.getElementById('team-item-template');
      if (!tpl || !container) return;
      var clone = tpl.content.cloneNode(true);
      clone.querySelectorAll('[name]').forEach(function (el) {
        el.name = el.name.replace(/__INDEX__/g, String(index));
      });
      clone.querySelectorAll('[data-member-index]').forEach(function (el) {
        el.setAttribute('data-member-index', String(index));
      });
      container.appendChild(clone);
    });
  });

  document.querySelectorAll('[data-add-process]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      var container = document.getElementById('process-list');
      var index = container.querySelectorAll('[data-sortable-item]').length;
      var tpl = document.getElementById('process-item-template');
      if (!tpl || !container) return;
      var clone = tpl.content.cloneNode(true);
      clone.querySelectorAll('[name]').forEach(function (el) {
        el.name = el.name.replace(/__INDEX__/g, String(index));
      });
      clone.querySelectorAll('[data-step-index]').forEach(function (el) {
        el.setAttribute('data-step-index', String(index));
      });
      container.appendChild(clone);
    });
  });

  document.querySelectorAll('[data-delete-process-step]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!confirm('Bu süreç adımını silmek istediğinize emin misiniz?')) {
        return;
      }
      var index = btn.getAttribute('data-step-index');
      var item = btn.closest('[data-sortable-item]');
      var titleInput = item ? item.querySelector('input[name*="[title]"]') : null;
      var stepTitle = titleInput ? titleInput.value : '';
      var csrfEl = document.querySelector('#content-form input[name="csrf_token"]');
      var csrf = csrfEl ? csrfEl.value : '';
      var form = document.createElement('form');
      form.method = 'post';
      form.action = '/admin/actions.php';
      [
        { name: 'csrf_token', value: csrf },
        { name: 'action', value: 'delete_process_step' },
        { name: 'step_index', value: index },
        { name: 'step_title', value: stepTitle },
      ].forEach(function (field) {
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = field.name;
        input.value = field.value;
        form.appendChild(input);
      });
      document.body.appendChild(form);
      form.submit();
    });
  });

  document.querySelectorAll('[data-delete-team-member]').forEach(function (btn) {
    btn.addEventListener('click', function () {
      if (!confirm('Bu ekip üyesini silmek istediğinize emin misiniz?')) {
        return;
      }
      var index = btn.getAttribute('data-member-index');
      var item = btn.closest('[data-sortable-item]');
      var nameInput = item ? item.querySelector('input[name*="[name]"]') : null;
      var memberName = nameInput ? nameInput.value : '';
      var csrfEl = document.querySelector('#content-form input[name="csrf_token"]');
      var csrf = csrfEl ? csrfEl.value : '';
      var form = document.createElement('form');
      form.method = 'post';
      form.action = '/admin/actions.php';
      [
        { name: 'csrf_token', value: csrf },
        { name: 'action', value: 'delete_team_member' },
        { name: 'member_index', value: index },
        { name: 'member_name', value: memberName },
      ].forEach(function (field) {
        var input = document.createElement('input');
        input.type = 'hidden';
        input.name = field.name;
        input.value = field.value;
        form.appendChild(input);
      });
      document.body.appendChild(form);
      form.submit();
    });
  });

  var nav = document.querySelector('.admin-nav');
  if (nav) {
    var links = nav.querySelectorAll('a[href^="#"]');
    links.forEach(function (link) {
      link.addEventListener('click', function () {
        links.forEach(function (l) { l.classList.remove('is-active'); });
        link.classList.add('is-active');
      });
    });
    if (location.hash) {
      var active = nav.querySelector('a[href="' + location.hash + '"]');
      if (active) active.classList.add('is-active');
    }
  }
})();
