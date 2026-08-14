/* BMS 交互式原型公共组件：表格明细工具栏（主从模块明细底部栏）
 * 结构与《布局设计-表格明细》第 4 节 / 2.4 节一致：
 *   - 左侧图标按钮组（新增行/删除行/上移行/下移行 + 通用工具：自动列宽/自定义列/刷新/全屏）
 *   - 右侧分页区（p-pager，右对齐）
 *   - 行操作（新增/删除/上移/下移）仅编辑态可用；删除行由页面二次确认
 * 用法：
 *   1) 页面引用：<script src="../02_公共原型/分页.js"></script>
 *                 <script src="../02_公共原型/明细工具栏.js"></script>
 *   2) 挂载：var bar = renderDetailBar(el, {
 *        readonly: true,
 *        onAdd(), onDelete(), onMoveUp(), onMoveDown(),   // 行操作回调
 *        tools: ['autoWidth','columns','refresh','fullscreen'],  // 通用工具按需
 *        onTool(name),
 *        page: { total, page, size, onPage(n), onSize(s) }      // 可选：分页（依赖分页.js）
 *      });
 *   3) 编辑态切换：bar.setReadonly(false) / bar.setReadonly(true)
 * 修改组件只需改本文件，所有引用页面同步生效。
 */
(function () {
  var ICONS = { add: '＋', del: '🗑', up: '↑', down: '↓', autoWidth: '⟷', columns: '☰', refresh: '⟳', fullscreen: '⛶' };
  var TITLES = { add: '新增行', del: '删除行', up: '上移行', down: '下移行', autoWidth: '自动列宽', columns: '自定义列', refresh: '刷新', fullscreen: '全屏' };

  function renderDetailBar(el, opts) {
    if (typeof el === 'string') { el = document.getElementById(el); }
    if (!el) return null;
    var o = opts || {};
    var state = { readonly: !!o.readonly };
    var tools = o.tools || ['autoWidth', 'columns', 'refresh', 'fullscreen'];
    var rowTools = ['add', 'del', 'up', 'down'];
    el.className = (el.className || '') + ' p-detail-bar';
    var html = '<div class="p-detail-tools">';
    rowTools.forEach(function (t) {
      html += '<button class="p-btn sm icon" data-t="' + t + '" title="' + TITLES[t] + '（仅编辑态可用）">' + ICONS[t] + '</button>';
    });
    if (tools.length) { html += '<span class="d-sep"></span>'; }
    tools.forEach(function (t) {
      html += '<button class="p-btn sm icon" data-t="' + t + '" title="' + TITLES[t] + '">' + ICONS[t] + '</button>';
    });
    html += '</div><div class="p-pager" id="' + (el.id || 'detail') + '-pager"></div>';
    el.innerHTML = html;
    var toolsEl = el.querySelector('.p-detail-tools');
    toolsEl.querySelectorAll('button[data-t]').forEach(function (b) {
      b.addEventListener('click', function () {
        var t = b.getAttribute('data-t');
        if (t === 'add') { o.onAdd && o.onAdd(); }
        else if (t === 'del') { o.onDelete && o.onDelete(); }
        else if (t === 'up') { o.onMoveUp && o.onMoveUp(); }
        else if (t === 'down') { o.onMoveDown && o.onMoveDown(); }
        else { o.onTool && o.onTool(t); }
      });
    });
    state.setReadonly = function (ro) {
      state.readonly = !!ro;
      toolsEl.querySelectorAll('button[data-t="add"],button[data-t="del"],button[data-t="up"],button[data-t="down"]')
        .forEach(function (b) { b.disabled = state.readonly; });
    };
    state.setReadonly(state.readonly);
    var pagerEl = el.querySelector('.p-pager');
    if (o.page) {
      if (window.renderPager) { renderPager(pagerEl, o.page); }
      else { pagerEl.textContent = '共 ' + (o.page.total || 0) + ' 条'; }
    } else {
      pagerEl.style.display = 'none';
    }
    el.__detailBar = state;
    return state;
  }
  window.renderDetailBar = renderDetailBar;
})();
