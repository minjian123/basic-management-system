/* BMS 交互式原型公共组件：分页区（列表页/表格明细）
 * 结构与《布局设计-表格明细》2.4 一致：总数 / 页码 / 跳页 / 每页条数 / 页码，默认 20 条/页。
 * 用法：
 *   1) 页面引用：<script src="../02_公共原型/分页.js"></script>
 *   2) 挂载：renderPager(el, { total, page, size, onPage(n), onSize(s) })
 * 挂载元素自动附加 p-pager 类（flex 右对齐），与《布局设计-列表页》分页位置一致。
 * 修改组件只需改本文件，所有引用页面同步生效。
 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function pages(total, size) {
    return Math.max(1, Math.ceil(total / size));
  }
  function numButtons(page, last) {
    var nums = [];
    var start = Math.max(1, page - 2), end = Math.min(last, page + 2);
    if (start > 1) nums.push(1);
    for (var i = start; i <= end; i++) nums.push(i);
    if (end < last) nums.push(last);
    return nums;
  }
  function renderPager(el, opts) {
    if (typeof el === 'string') { el = document.getElementById(el); }
    if (!el) return;
    var o = opts || {};
    var total = o.total == null ? 0 : o.total;
    var size = o.size || 20;
    var page = o.page || 1;
    var last = pages(total, size);
    var onPage = o.onPage || function () {};
    var onSize = o.onSize || function (s) { onPage(1); };
    var html = '<span class="pp-total">共 ' + total + ' 条</span>';
    html += '<button class="pp-num" ' + (page <= 1 ? 'disabled' : '') + ' data-p="' + (page - 1) + '">‹</button>';
    numButtons(page, last).forEach(function (n) {
      html += '<button class="pp-num' + (n === page ? ' active' : '') + '" data-p="' + n + '">' + n + '</button>';
    });
    html += '<button class="pp-num" ' + (page >= last ? 'disabled' : '') + ' data-p="' + (page + 1) + '">›</button>';
    html += '<select class="pp-size" title="每页条数">';
    [10, 20, 50, 100].forEach(function (s) {
      html += '<option value="' + s + '"' + (s === size ? ' selected' : '') + '>' + s + ' 条/页</option>';
    });
    html += '</select>';
    html += '<span>跳至 <input class="pp-goto" type="number" min="1" max="' + last + '" value="' + page + '"> 页</span>';
    html += '<button class="p-btn sm" id="' + (el.id || '') + '-goto">跳转</button>';
    // 挂载元素附加 p-pager 类：flex 容器右对齐（原型样式.css）
    el.className = (el.className || '') + ' p-pager';
    el.innerHTML = html;
    el.querySelectorAll('.pp-num').forEach(function (b) {
      b.addEventListener('click', function () { if (!b.disabled) onPage(parseInt(b.getAttribute('data-p'), 10)); });
    });
    el.querySelector('.pp-size').addEventListener('change', function (e) { onSize(parseInt(e.target.value, 10)); });
    el.querySelector('button').addEventListener('click', function () {
      var v = parseInt(el.querySelector('.pp-goto').value, 10);
      if (v >= 1 && v <= last) onPage(v);
    });
  }
  window.renderPager = renderPager;
})();
