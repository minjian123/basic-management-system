/* BMS 交互式原型公共组件：系统信息（表单详情页）
 * 字段与《布局设计-表单页》2.1 一致：ID / 创建时间 / 创建用户 / 修改时间 / 修改用户（纯文本只读）
 * 用法：
 *   1) 页面引用：<script src="../_shared/system-info.js"></script>
 *   2) 生成字符串（JS 模板内）：sysInfoHTML({ id, createdAt, createdBy, updatedAt, updatedBy, extra })
 *   3) 便捷挂载：mountSysInfo(document.getElementById('xxx'), { ... })
 * 修改字段只需改本文件，所有引用页面同步生效。
 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  function field(label, value) {
    var v = (value == null || value === '') ? '—' : esc(value);
    return '<div class="p-col p-field"><label>' + esc(label) + '</label><div class="sys-text">' + v + '</div></div>';
  }
  // data: { id, createdAt, createdBy, updatedAt, updatedBy, extra: [[label, value], ...] }
  function sysInfoHTML(data) {
    var d = data || {};
    var extra = (d.extra || []).slice();
    var html = '<div class="p-section">系统信息（只读）</div>';
    // 行 1：ID | 扩展字段首项（如版本号）
    var row1 = field('ID', d.id);
    if (extra.length) { row1 += field(extra[0][0], extra[0][1]); extra = extra.slice(1); }
    html += '<div class="p-row">' + row1 + '</div>';
    // 行 2：创建时间 | 修改时间（同列对齐）
    html += '<div class="p-row">' + field('创建时间', d.createdAt) + field('修改时间', d.updatedAt) + '</div>';
    // 行 3：创建用户 | 修改用户（同列对齐）+ 其余扩展字段
    var row3 = field('创建用户', d.createdBy) + field('修改用户', d.updatedBy);
    extra.forEach(function (kv) { row3 += field(kv[0], kv[1]); });
    html += '<div class="p-row">' + row3 + '</div>';
    return html;
  }
  function mountSysInfo(el, data) {
    if (el) el.innerHTML = sysInfoHTML(data);
  }
  window.sysInfoHTML = sysInfoHTML;
  window.mountSysInfo = mountSysInfo;
})();
