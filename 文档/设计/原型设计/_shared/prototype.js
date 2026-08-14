/* BMS 交互式原型公共脚本 */
(function () {
  // 嵌入主框架时（URL 带 embed=1）隐藏顶部原型条（面包屑导航栏）
  if (location.search.indexOf('embed=1') >= 0) {
    var bar = document.querySelector('.proto-bar');
    if (bar) bar.style.display = 'none';
  }
  // Toast
  window.toast = function (msg, type) {
    var el = document.querySelector('.p-toast');
    if (!el) { el = document.createElement('div'); el.className = 'p-toast'; document.body.appendChild(el); }
    el.textContent = msg;
    el.className = 'p-toast show' + (type ? ' ' + type : '');
    clearTimeout(el._t);
    el._t = setTimeout(function () { el.className = 'p-toast'; }, 1800);
  };

  // 弹窗（对话框）
  // openModal(id, title)：title 可选，按《布局设计-弹窗》"标题=动作+对象"动态设置（如「编辑角色」）
  window.openModal = function (id, title) {
    var m = document.getElementById(id);
    if (!m) return;
    if (title) {
      var head = m.querySelector('.pm-head');
      if (head) {
        var x = head.querySelector('.x');
        head.innerHTML = '<span>' + title + '</span>';
        if (x) head.appendChild(x);
      }
    }
    m.classList.add('show');
  };
  window.closeModal = function (id) { var m = document.getElementById(id); if (m) m.classList.remove('show'); };

  // 抽屉（表单编辑优先，《布局设计-弹窗》§1.1）
  window.openDrawer = function (id, title) {
    var d = document.getElementById(id);
    if (!d) return;
    if (title) {
      var head = d.querySelector('.pd-head');
      if (head) {
        var x = head.querySelector('.x');
        head.innerHTML = '<span>' + title + '</span>';
        if (x) head.appendChild(x);
      }
    }
    d.classList.add('show');
  };
  window.closeDrawer = function (id) { var d = document.getElementById(id); if (d) d.classList.remove('show'); };

  // 遮罩点击关闭：仅非锁定弹窗（确认类 .p-mask-lock 必须显式点按钮）
  document.addEventListener('click', function (e) {
    if (e.target.classList && e.target.classList.contains('p-mask') && !e.target.classList.contains('p-mask-lock')) {
      e.target.classList.remove('show');
    }
  });

  // Tab 切换：data-tabs="容器id" data-tab="tab名"，内容块 id="容器id-tab名"
  document.addEventListener('click', function (e) {
    var t = e.target.closest && e.target.closest('[data-tab]');
    if (!t) return;
    var holder = t.getAttribute('data-tabs');
    if (!holder) return;
    var name = t.getAttribute('data-tab');
    document.querySelectorAll('[' + 'data-tabs="' + holder + '"]').forEach(function (x) { x.classList.remove('active'); });
    t.classList.add('active');
    var box = document.getElementById(holder);
    if (box) box.querySelectorAll('[data-pane]').forEach(function (p) { p.style.display = p.getAttribute('data-pane') === name ? '' : 'none'; });
  });

  // 视图切换：data-view-show="id"（显示并隐藏 data-view-group 分组内的兄弟）
  document.addEventListener('click', function (e) {
    var v = e.target.closest && e.target.closest('[data-view-show]');
    if (!v) return;
    var id = v.getAttribute('data-view-show');
    var group = v.getAttribute('data-view-group');
    if (group) {
      document.querySelectorAll('[data-view-group="' + group + '"]').forEach(function (x) {
        x.style.display = x.id === id ? '' : 'none';
      });
    } else {
      var el = document.getElementById(id);
      if (el) { el.style.display = ''; }
    }
  });

  // 通用确认弹窗（危险操作：锁定遮罩/Esc，必须显式点按钮）
  window.confirmAction = function (msg, fn) {
    var m = document.getElementById('__confirm');
    if (!m) {
      m = document.createElement('div');
      m.className = 'p-mask p-mask-lock';
      m.id = '__confirm';
      m.innerHTML = '<div class="p-modal w420"><div class="pm-head">确认操作</div>' +
        '<div class="pm-body" id="__confirm-msg"></div>' +
        '<div class="pm-foot"><button class="p-btn" onclick="closeModal(\'__confirm\')">取消</button><button class="p-btn danger" id="__confirm-ok">确定</button></div></div>';
      document.body.appendChild(m);
    }
    document.getElementById('__confirm-msg').textContent = msg;
    document.getElementById('__confirm-ok').onclick = function () { closeModal('__confirm'); fn && fn(); };
    m.classList.add('show');
  };

  // Esc 关闭：跳过锁定弹窗（确认类）
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') {
      document.querySelectorAll('.p-mask.show').forEach(function (m) {
        if (!m.classList.contains('p-mask-lock')) m.classList.remove('show');
      });
    }
  });
})();
