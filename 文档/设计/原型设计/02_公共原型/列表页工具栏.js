/* BMS 交互式原型公共组件：列表页工具栏（工具栏 + 筛选区 + 分页一体化）
 * 结构与《布局设计-列表页》一致：
 *   - 工具栏一行：主按钮（primary）+ 普通按钮组 + 右侧提示（extra）
 *   - 筛选区一行：关键字输入框 + 查询/重置
 *   - 分页区（表格下方，p-pager 右对齐，依赖分页.js）
 * 用法：
 *   1) 页面引用：<script src="../02_公共原型/分页.js"></script>
 *                 <script src="../02_公共原型/列表页工具栏.js"></script>
 *   2) 挂载（top 在表格上方，bottom 在表格下方）：
 *      var list = renderListToolbar({
 *        top: document.getElementById('list-top'),
 *        bottom: document.getElementById('list-bottom'),   // 可选：分页挂载点
 *        primary: { label: '新增用户', onClick: function () {} },
 *        buttons: [
 *          { label: '刷新', onClick: function () {} },
 *          { label: '关闭', onClick: function () {} },
 *          { label: '导出', onClick: function () {}, danger: true },
 *          { label: '删除', onClick: function () {}, danger: true, cls: 'batch-btn', disabled: true }
 *        ],
 *        extra: '<span class="proto-hint">…</span>',
 *        filter: { placeholder: '关键字：名称/编码',
 *                  extraHtml: '<select class="p-select">…</select>',   // 可选：附加筛选控件（onchange 由页面处理）
 *                  onSearch: function (kw) {}, onReset: function () {} },
 *        page: { total: 128, page: 1, size: 20, onPage: function (n) {}, onSize: function (s) {} }
 *      });
 * 说明：top 挂载点 id 作为本实例控件 id 前缀，同页可多次调用（如多 Tab 各自挂载）；
 *      buttons 项可选 cls（附加 class，如 batch-btn 由页面勾选逻辑管理禁用态）与 disabled（初始禁用）。
 * 修改组件只需改本文件，所有引用页面同步生效。
 */
(function () {
  function renderListToolbar(opts) {
    var o = opts || {};
    var top = o.top;
    if (typeof top === 'string') { top = document.getElementById(top); }
    if (!top) return null;
    var p = top.id || 'lt';

    var html = '<div class="p-toolbar">';
    if (o.primary) {
      html += '<button class="p-btn primary" id="' + p + '-primary">' + o.primary.label + '</button>';
    }
    (o.buttons || []).forEach(function (b, i) {
      html += '<button class="p-btn' + (b.danger ? ' danger' : '') + (b.cls ? ' ' + b.cls : '') + '" id="' + p + '-btn-' + i + '"' + (b.disabled ? ' disabled' : '') + '>' + b.label + '</button>';
    });
    if (o.extra) { html += '<span style="margin-left:auto">' + o.extra + '</span>'; }
    html += '</div>';

    if (o.filter) {
      html += '<div class="p-filter">';
      html += '<input class="p-input keyword" id="' + p + '-kw" placeholder="' + (o.filter.placeholder || '关键字') + '">';
      if (o.filter.extraHtml) { html += o.filter.extraHtml; }
      html += '<button class="p-btn sm primary" id="' + p + '-search">查询</button>';
      html += '<button class="p-btn sm" id="' + p + '-reset">重置</button>';
      html += '</div>';
    }
    top.innerHTML = html;
    if (o.primary) {
      document.getElementById(p + '-primary').addEventListener('click', function () { o.primary.onClick && o.primary.onClick(); });
    }
    (o.buttons || []).forEach(function (b, i) {
      document.getElementById(p + '-btn-' + i).addEventListener('click', function () { b.onClick && b.onClick(); });
    });
    if (o.filter) {
      var kw = document.getElementById(p + '-kw');
      var doSearch = function () { o.filter.onSearch && o.filter.onSearch(kw.value.trim()); };
      document.getElementById(p + '-search').addEventListener('click', doSearch);
      kw.addEventListener('keydown', function (e) { if (e.key === 'Enter') doSearch(); });
      document.getElementById(p + '-reset').addEventListener('click', function () { kw.value = ''; o.filter.onReset && o.filter.onReset(); });
    }
    if (o.page) {
      var bottom = o.bottom;
      if (typeof bottom === 'string') { bottom = document.getElementById(bottom); }
      if (bottom) {
        if (window.renderPager) { renderPager(bottom, o.page); }
        else { bottom.textContent = '共 ' + (o.page.total || 0) + ' 条'; }
      }
    }
    return { el: top, kw: o.filter ? document.getElementById(p + '-kw') : null };
  }
  window.renderListToolbar = renderListToolbar;
})();
