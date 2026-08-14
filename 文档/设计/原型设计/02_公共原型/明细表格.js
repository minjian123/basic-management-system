/* BMS 交互式原型公共组件：明细表格（主从明细一体组件）
 * 一站式生成：明细表格（行内编辑）+ 左下角明细工具栏（图标按钮）+ 右下角分页，
 * 结构与《布局设计-表格明细》一致（第 2.3/2.4/4/5 节）。
 *
 * 用法：
 *   1) 页面引用：<script src="../02_公共原型/分页.js"></script>
 *                 <script src="../02_公共原型/明细工具栏.js"></script>
 *                 <script src="../02_公共原型/明细表格.js"></script>
 *   2) 挂载（一个挂载点，组件生成 表格 + 明细工具栏 + 分页）：
 *      var dt = renderDetailTable(document.getElementById('detail'), {
 *        columns: [
 *          { key: 'name',    label: '物料名称', width: 200 },
 *          { key: 'qty',     label: '数量',     width: 80,  type: 'number', align: 'right' },
 *          { key: 'price',   label: '单价',     width: 90,  type: 'number', align: 'right' },
 *          { key: 'subtotal', label: '小计',    width: 100, type: 'computed', align: 'right',
 *            fn: function (row) { return '¥' + (row.qty * row.price).toLocaleString(); } }
 *        ],
 *        data: [ { name: '办公桌', qty: 10, price: 1800 } ],
 *        readonly: false,                       // 初始态（只读禁用行内编辑与行操作）
 *        rowTools: ['add', 'del', 'up', 'down'],// 行操作按钮集（配置型表格可传 [] 或子集）
 *        tools: ['refresh', 'fullscreen'],      // 通用工具（可选）
 *        page: { size: 10 },                    // 分页：明细超过 size 行自动分页（10 条/页）
 *        onChange: function (rows) { /* 行增删移/编辑后的回调（页面算合计等） */ }
 *      });
 *   3) 状态控制：
 *      dt.setReadonly(true/false)   // 编辑态切换：行内输入与行操作按钮联动禁用
 *      dt.getRows()                 // 取当前明细行数据（保存时过滤空行）
 *   组件内置：行选中（点击）、新增行（追加空行）、删除行（二次确认，至少保留一行）、
 *   上移/下移（选中行）、编辑态自动空行（末尾非空时追加）、分页切换。
 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function renderDetailTable(el, opts) {
    if (typeof el === 'string') { el = document.getElementById(el); }
    if (!el) return null;
    var o = opts || {};
    var cols = o.columns || [];
    var rows = (o.data || []).map(function (r) { return Object.assign({}, r); });
    var pageSize = (o.page && o.page.size) || 10;
    var page = 1;
    var state = {
      rows: rows,
      readonly: !!o.readonly,
      setReadonly: null,
      getRows: function () { return rows; }
    };

    el.className = (el.className || '') + ' p-detail-table';
    var html = '<table class="p-table" id="dt"><tr>';
    cols.forEach(function (c) {
      html += '<th' + (c.width ? ' style="width:' + c.width + 'px"' : '') + '>' + c.label + '</th>';
    });
    html += '</tr></table><div class="p-detail-bar" id="bar"></div>';
    el.innerHTML = html;
    var tbl = el.querySelector('#dt');

    function cellHtml(row, c, editable) {
      if (c.type === 'computed') {
        return '<td' + (c.align === 'right' ? ' style="text-align:right"' : '') + '><span data-c="' + c.key + '">' + (c.fn ? esc(c.fn(row)) : '') + '</span></td>';
      }
      var val = row[c.key] == null ? '' : String(row[c.key]);
      var isNum = c.type === 'number';
      var input = '<input class="p-input" data-k="' + c.key + '"' + (isNum ? ' type="number"' : '') + ' value="' + esc(val) + '"' +
        (c.align === 'right' ? ' style="width:80px;text-align:right;padding:3px 8px"' : ' style="padding:3px 8px"') +
        (editable ? '' : ' disabled') + '>';
      return '<td>' + input + '</td>';
    }

    function renderRows() {
      tbl.querySelectorAll('tr:not(:first-child)').forEach(function (tr) { tr.remove(); });
      var start = (page - 1) * pageSize, end = Math.min(start + pageSize, rows.length);
      var editable = !state.readonly;
      for (var i = start; i < end; i++) {
        (function (row, idx) {
          var tr = document.createElement('tr');
          if (idx === (page - 1) * pageSize && rows.length) { tr.className = 'sel'; }
          tr.innerHTML = cols.map(function (c) { return cellHtml(row, c, editable); }).join('');
          tr.addEventListener('click', function () {
            tbl.querySelectorAll('tr.sel').forEach(function (x) { x.classList.remove('sel'); });
            tr.classList.add('sel');
          });
          tr.querySelectorAll('input').forEach(function (inp) {
            inp.addEventListener('input', function () {
              var k = inp.getAttribute('data-k');
              row[k] = inp.type === 'number' ? (parseFloat(inp.value) || 0) : inp.value;
              cols.forEach(function (c) {
                if (c.type === 'computed') {
                  var span = tr.querySelector('[data-c="' + c.key + '"]');
                  if (span && c.fn) span.textContent = esc(c.fn(row));
                }
              });
              state.onChange && state.onChange(rows);
            });
          });
          tbl.appendChild(tr);
        })(rows[i], i);
      }
      if (!rows.length) {
        var empty = document.createElement('tr');
        empty.innerHTML = '<td colspan="' + cols.length + '" style="text-align:center;color:#8c959f;padding:20px">暂无明细，点击「＋ 新增行」添加</td>';
        tbl.appendChild(empty);
      }
    }

    function addRow() {
      var blank = {};
      cols.forEach(function (c) {
        if (c.type !== 'computed') blank[c.key] = c.type === 'number' ? 1 : '';
      });
      rows.push(blank);
      var last = Math.ceil(rows.length / pageSize);
      page = last;
      renderRows();
      state.onChange && state.onChange(rows);
    }
    function delSel() {
      var tr = tbl.querySelector('tr.sel');
      if (!tr) { toast('请先选择一行明细', 'err'); return; }
      if (rows.length <= 1) { toast('至少保留一行明细', 'err'); return; }
      var idx = Array.prototype.indexOf.call(tbl.querySelectorAll('tr'), tr) - 1;
      confirmAction('删除选中的明细行？删除后不可恢复。', function () {
        rows.splice((page - 1) * pageSize + idx, 1);
        if (page > Math.ceil(rows.length / pageSize)) page = Math.max(1, page - 1);
        renderRows();
        state.onChange && state.onChange(rows);
        toast('已删除该行', 'ok');
      });
    }
    function moveSel(dir) {
      var tr = tbl.querySelector('tr.sel');
      if (!tr) { toast('请先选择一行明细', 'err'); return; }
      var idx = Array.prototype.indexOf.call(tbl.querySelectorAll('tr'), tr) - 1;
      var target = idx + dir;
      if (target < 0 || target >= rows.length) { toast(dir < 0 ? '已是第一行' : '已是最后一行', 'err'); return; }
      var tmp = rows[idx]; rows[idx] = rows[target]; rows[target] = tmp;
      renderRows();
      state.onChange && state.onChange(rows);
    }

    var bar = renderDetailBar(el.querySelector('#bar'), {
      readonly: state.readonly,
      rowTools: o.rowTools,
      tools: o.tools,
      onAdd: function () { addRow(); },
      onDelete: function () { delSel(); },
      onMoveUp: function () { moveSel(-1); },
      onMoveDown: function () { moveSel(1); },
      onTool: o.onTool,
      page: {
        total: rows.length, page: page, size: pageSize,
        onPage: function (n) { page = n; renderRows(); },
        onSize: function (s) { pageSize = s; page = 1; renderRows(); }
      }
    });

    state.setReadonly = function (ro) {
      state.readonly = !!ro;
      bar.setReadonly(state.readonly);
      renderRows();
      // 编辑态自动空行：末尾行非空则追加一行空明细（保存时由页面过滤空行）
      if (!state.readonly && rows.length) {
        var last = rows[rows.length - 1];
        var nonEmpty = cols.some(function (c) {
          if (c.type === 'computed') return false;
          var v = last[c.key];
          return v !== '' && v != null && v !== 1;
        });
        if (nonEmpty) addRow();
      }
    };
    renderRows();
    state.onChange = o.onChange || null;
    return state;
  }
  window.renderDetailTable = renderDetailTable;
})();
