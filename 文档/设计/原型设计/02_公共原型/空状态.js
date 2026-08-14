/* BMS 交互式原型公共组件：空状态（列表/搜索/业务空态）
 * 结构与《布局设计-异常与空状态》一致：居中插画（SVG）+ 文案 + 可选引导按钮。
 * 用法：
 *   1) 页面引用：<script src="../00_公共原型/empty.js"></script>
 *   2) 挂载：renderEmpty(el, { type: 'list'|'search'|'todo'|'msg'|'error', action: '去创建'|'重置'|null, onAction() })
 * 修改组件只需改本文件，所有引用页面同步生效。
 */
(function () {
  function esc(s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }
  var TEXTS = {
    list: { icon: 'circle',  text: '暂无数据' },
    search: { icon: 'search', text: '未找到相关内容' },
    todo: { icon: 'check',   text: '暂无待办，享受这一刻' },
    msg: { icon: 'bell',     text: '暂无消息' },
    error: { icon: 'warn',   text: '加载失败，请稍后重试' }
  };
  function iconSVG(type) {
    var c = TEXTS[type] || TEXTS.list;
    if (c.icon === 'circle') return '<circle cx="32" cy="32" r="20" fill="none" stroke="#d0d7de" stroke-width="3"/><circle cx="32" cy="32" r="9" fill="#d0d7de"/>';
    if (c.icon === 'search') return '<circle cx="30" cy="30" r="14" fill="none" stroke="#d0d7de" stroke-width="3"/><line x1="40" y1="40" x2="52" y2="52" stroke="#d0d7de" stroke-width="4" stroke-linecap="round"/>';
    if (c.icon === 'check') return '<circle cx="32" cy="32" r="20" fill="none" stroke="#2da44e" stroke-width="3"/><polyline points="24,32 30,38 41,26" fill="none" stroke="#2da44e" stroke-width="3" stroke-linecap="round"/>';
    if (c.icon === 'bell') return '<path d="M32 14v4M22 36a11 11 0 0 1 20 0M18 36h28" fill="none" stroke="#d0d7de" stroke-width="3" stroke-linecap="round"/>';
    return '<circle cx="32" cy="32" r="20" fill="none" stroke="#d4a72c" stroke-width="3"/><line x1="32" y1="22" x2="32" y2="32" stroke="#d4a72c" stroke-width="3" stroke-linecap="round"/><circle cx="32" cy="41" r="2.5" fill="#d4a72c"/>';
  }
  function renderEmpty(el, opts) {
    if (!el) return;
    var o = opts || {};
    var type = o.type || 'list';
    var t = TEXTS[type] || TEXTS.list;
    var html = '<div class="p-empty">';
    html += '<div class="p-empty-icon"><svg width="64" height="64" viewBox="0 0 64 64">' + iconSVG(type) + '</svg></div>';
    html += '<div>' + esc(o.text || t.text) + '</div>';
    if (o.action) {
      html += '<div style="margin-top:10px"><button class="p-btn primary" id="' + (el.id || 'empty') + '-action">' + esc(o.action) + '</button></div>';
    }
    html += '</div>';
    el.innerHTML = html;
    if (o.action) {
      el.querySelector('button').addEventListener('click', function () { o.onAction && o.onAction(); });
    }
  }
  window.renderEmpty = renderEmpty;
})();
