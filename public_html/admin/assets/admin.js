(function () {
  function reindexList(container, itemSelector, namePrefix) {
    container.querySelectorAll(itemSelector).forEach(function (item, index) {
      item.querySelectorAll('[name]').forEach(function (el) {
        el.name = el.name.replace(/\[\d+\]/, '[' + index + ']');
      });
      var label = item.querySelector('[data-item-label]');
      if (label) {
        label.textContent = 'Kart ' + (index + 1);
      }
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
      if (item && container && container.querySelectorAll('[data-sortable-item]').length > 1) {
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
      clone.querySelectorAll('[name="member_index"]').forEach(function (el) {
        el.value = String(index);
      });
      container.appendChild(clone);
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
