'use strict';
const $ = id => document.getElementById(id);
let language = 'en';
try { language = localStorage.getItem('rafeeq-language') === 'ar' ? 'ar' : 'en'; } catch {}
let actions = [], officerActions = [], health = null, verified = false, verificationTimer = null;
const preview = location.protocol === 'file:' || new URLSearchParams(location.search).get('preview') === '1';
const labels = (en, ar) => language === 'ar' ? ar : en;
const toolNames = {
  book_inspection: ['Inspection booking', 'حجز فحص'],
  reschedule_inspection: ['Reschedule inspection', 'تغيير موعد الفحص'],
  request_refund: ['Refund request', 'طلب استرداد'],
};
const stateNames = {
  pending: ['Needs your confirmation', 'بانتظار تأكيدك'],
  awaiting_officer: ['Finance review', 'مراجعة الموظف المالي'],
  completed: ['Completed', 'مكتمل'], rejected: ['Declined', 'مرفوض'],
  expired: ['Expired', 'منتهي الصلاحية'], cancelled: ['Cancelled', 'ملغى'],
};
function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function icon(name, className = '') {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('class', 'icon ' + className); svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
  use.setAttribute('href', '#i-' + name); svg.append(use); return svg;
}
async function api(path, method = 'GET', body, officer = false) {
  if (preview) throw new Error(labels('Start the Rafeeq service to use this feature.', 'شغّل خدمة رفيق لاستخدام هذه الميزة.'));
  const headers = {'Content-Type': 'application/json', 'X-Rafeeq-Client': '1'};
  if (officer) headers['X-Officer-Token'] = $('officer-token').value;
  const response = await fetch(path, {method, headers, credentials: 'same-origin',
    signal: AbortSignal.timeout(path === '/api/chat' ? 75000 : 15000),
    body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail :
    labels('Check your details and try again.', 'تحقق من بياناتك وحاول مجددًا.'));
  return data;
}
function connection(state, text) {
  $('connection').dataset.state = state; $('connection').textContent = text;
}
function updateConnection() {
  if (preview) return connection('error', labels('Interface preview', 'معاينة الواجهة'));
  if (!health) return;
  connection(health.ai_configured ? 'ready' : 'error',
    health.ai_configured ? labels('Ready to help', 'جاهز لمساعدتك') : labels('AI setup needed', 'يلزم إعداد الخدمة'));
}
function verificationState(ok, text = '') {
  verified = ok;
  $('verify-badge').classList.toggle('verified', ok);
  $('verify-badge').textContent = ok ? labels('Verified', 'تم التحقق') : labels('Not verified', 'غير متحقق');
  $('verification-status').textContent = text;
  $('verification-status').dataset.state = ok ? 'success' : 'error';
}
function setLanguage(value) {
  language = value;
  document.documentElement.lang = language; document.documentElement.dir = language === 'ar' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-en]').forEach(node => { node.textContent = node.dataset[language]; });
  document.querySelectorAll('[data-placeholder-en]').forEach(node => { node.placeholder = node.dataset[language === 'ar' ? 'placeholderAr' : 'placeholderEn']; });
  $('language').querySelector('span').textContent = language === 'ar' ? 'English' : 'العربية';
  $('verify-badge').textContent = verified ? labels('Verified', 'تم التحقق') : labels('Not verified', 'غير متحقق');
  if ($('verification-status').textContent) $('verification-status').textContent = verified ?
    labels('Verified for this application. Access expires after 15 minutes.', 'تم التحقق لهذا الطلب. ينتهي الوصول بعد ١٥ دقيقة.') : '';
  renderActions(actions); renderActions(officerActions, 'officer-actions', true); updateConnection();
  if (preview) showPreviewNotice();
  try { localStorage.setItem('rafeeq-language', language); } catch {}
}
function message(text, role, data) {
  $('chat-welcome')?.remove();
  const article = element('article', 'message ' + role);
  if (role === 'assistant') article.append(element('span', 'message-avatar', 'ر'));
  const bubble = element('div', 'bubble', text); bubble.dir = 'auto';
  if (data) {
    const details = element('details', 'trace');
    details.append(element('summary', '', labels('View sources & activity', 'عرض المصادر والنشاط')));
    details.append(element('p', '', data.tools?.join(' → ') || labels('No tools used', 'لم تُستخدم أدوات')));
    details.append(element('p', '', (data.usage?.model_steps ?? 0) + ' steps · ' + data.stopped + ' · ' + data.trace_id));
    bubble.append(details);
  }
  article.append(bubble); $('messages').append(article); scrollMessages();
}
function scrollMessages() { $('messages').scrollTop = $('messages').scrollHeight; }
function typing(show) {
  $('typing')?.remove();
  if (!show) return;
  const node = element('div', 'typing'); node.id = 'typing';
  node.setAttribute('aria-label', labels('Rafeeq is responding', 'رفيق يجهّز الرد'));
  for (let i = 0; i < 3; i++) node.append(element('span'));
  $('messages').append(node); scrollMessages();
}
function formatSlot(value) {
  if (!value) return '';
  const date = new Date(value.replace(' ', 'T'));
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat(language === 'ar' ? 'ar-SA-u-ca-gregory' : 'en-GB',
    {day:'numeric',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit'}).format(date);
}
function renderActions(items, target = 'actions', officer = false) {
  const root = $(target); root.replaceChildren();
  if (!officer) $('action-count').textContent = String(items.filter(a => a.status === 'pending').length);
  if (!items.length) {
    const empty = element('div', 'empty-actions');
    const check = element('span', 'empty-check'); check.append(icon('check'));
    empty.append(check, element('strong', '', labels('Nothing to review yet', 'لا توجد إجراءات للمراجعة')),
      element('p', '', labels('Bookings and refund requests appear here for your confirmation.', 'ستظهر الحجوزات وطلبات الاسترداد هنا لتأكيدها.')));
    root.append(empty); return;
  }
  for (const action of items) {
    const expired = action.status === 'pending' && action.expires && action.expires * 1000 < Date.now();
    const status = expired ? 'expired' : action.status;
    const name = toolNames[action.tool] || [action.tool, action.tool];
    const state = stateNames[status] || [status, status];
    const card = element('div', 'action-card');
    const heading = element('div', 'action-card-header');
    heading.append(element('h3', '', labels(...name)), element('span', 'action-state', labels(...state)));
    card.append(heading);
    const fields = element('div', 'action-fields');
    const row = (label, value) => {
      if (value === undefined || value === null || value === '') return;
      const item = element('div', 'action-field');
      item.append(element('span', '', label), element('strong', '', String(value))); fields.append(item);
    };
    row(labels('Application', 'الطلب'), action.args?.permit_id);
    row(labels('Appointment', 'الموعد'), formatSlot(action.result?.slot || action.args?.slot));
    row(labels('Amount', 'المبلغ'), action.result?.amount_sar === undefined ? null :
      new Intl.NumberFormat(language === 'ar' ? 'ar-SA' : 'en-GB').format(action.result.amount_sar) + labels(' SAR', ' ريال'));
    row(labels('District', 'الحي'), action.result?.district);
    card.append(fields);
    if (status === 'awaiting_officer') card.append(element('p', 'action-note',
      labels('Your request is confirmed. A finance officer must review it before approval.', 'تم تأكيد طلبك. يلزم مراجعته من الموظف المالي قبل الموافقة.')));
    if (status === (officer ? 'awaiting_officer' : 'pending')) {
      const buttons = element('div', 'action-buttons');
      for (const approve of [true, false]) {
        const button = element('button', approve ? 'confirm' : '', approve ? labels('Confirm', 'تأكيد') : labels('Decline', 'رفض'));
        button.type = 'button';
        button.onclick = async () => {
          buttons.querySelectorAll('button').forEach(b => { b.disabled = true; });
          try {
            const result = await api('/api/' + (officer ? 'officer/' : '') + 'actions/' + encodeURIComponent(action.id) + '/decision', 'POST', {approve}, officer);
            const state = stateNames[result.status] || [result.status, result.status];
            message(labels(...name) + ': ' + labels(...state) + '.', 'assistant');
            actions = await api('/api/actions'); renderActions(actions);
            if (officer) { officerActions = await api('/api/officer/actions','GET',undefined,true); renderActions(officerActions,'officer-actions',true); }
          } catch (error) { message(error.message, 'assistant'); buttons.querySelectorAll('button').forEach(b => { b.disabled = false; }); }
        };
        buttons.append(button);
      }
      card.append(buttons);
    }
    root.append(card);
  }
}
function showPreviewNotice() {
  $('preview-notice').hidden = false;
  $('preview-notice').textContent = labels(
    'You’re viewing the interface preview. Start the Rafeeq service to chat, verify applications, and confirm actions.',
    'أنت تشاهد معاينة الواجهة. شغّل خدمة رفيق للمحادثة والتحقق من الطلبات وتأكيد الإجراءات.');
}
$('language').onclick = () => setLanguage(language === 'en' ? 'ar' : 'en');
$('verify').onsubmit = async event => {
  event.preventDefault();
  const form = event.target, button = form.querySelector('button[type=submit]');
  button.disabled = true;
  try {
    await api('/api/verify', 'POST', Object.fromEntries(new FormData(form)));
    verificationState(true, labels('Verified for this application. Access expires after 15 minutes.', 'تم التحقق لهذا الطلب. ينتهي الوصول بعد ١٥ دقيقة.'));
    clearTimeout(verificationTimer);
    verificationTimer = setTimeout(() => verificationState(false, labels('Verification expired. Please verify again.', 'انتهت صلاحية التحقق. يرجى التحقق مجددًا.')), 900000);
  } catch (error) { verificationState(false, error.message); }
  finally { form.elements.last4.value = ''; form.elements.mobile.value = ''; button.disabled = false; }
};
$('chat').onsubmit = async event => {
  event.preventDefault();
  const text = $('message').value.trim();
  if (!text || $('send').disabled) return;
  message(text,'user'); $('message').value = ''; $('send').disabled = true; $('messages').setAttribute('aria-busy', 'true'); typing(true);
  try {
    const data = await api('/api/chat', 'POST', {message: text});
    typing(false); message(data.reply, 'assistant', data); actions = data.actions; renderActions(actions);
  } catch (error) {
    typing(false);
    message(error.name === 'TimeoutError' ? labels('This is taking longer than expected. Please try again.', 'استغرق الطلب وقتًا أطول من المتوقع. يرجى المحاولة مجددًا.') : error.message, 'assistant');
  } finally { typing(false); $('send').disabled = preview; $('messages').setAttribute('aria-busy', 'false'); $('message').focus(); }
};
$('message').onkeydown = event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); $('chat').requestSubmit(); } };
document.querySelectorAll('[data-question]').forEach(button => {
  button.onclick = () => {
    $('message').value = language === 'ar' ? button.dataset.arQuestion : button.dataset.question;
    $('chat-panel').scrollIntoView({behavior: 'smooth', block: 'center'}); $('message').focus({preventScroll:true});
  };
});
document.querySelectorAll('[data-permit]').forEach(button => {
  button.onclick = () => {
    const form = $('verify');
    form.elements.permit_id.value = button.dataset.permit;
    form.elements.last4.value = button.dataset.last4;
    form.elements.mobile.value = button.dataset.mobile;
    form.querySelector('button[type=submit]').focus();
  };
});
document.querySelectorAll('.nav-link').forEach(link => {
  link.onclick = () => {
    document.querySelectorAll('.nav-link').forEach(node => node.classList.remove('active'));
    link.classList.add('active');
  };
});
async function reset() {
  if (preview) { location.reload(); return; }
  try { await api('/api/session', 'DELETE'); location.reload(); } catch (error) { message(error.message, 'assistant'); }
}
$('reset').onclick = reset; $('new-chat').onclick = reset;
$('load-officer').onclick = async () => {
  const button = $('load-officer'); button.disabled = true;
  try { officerActions = await api('/api/officer/actions','GET',undefined,true); renderActions(officerActions,'officer-actions',true); }
  catch (error) { message(error.message,'assistant'); }
  finally { button.disabled = false; }
};
async function init() {
  setLanguage(language);
  if (preview) { showPreviewNotice(); updateConnection(); $('send').disabled = true; return; }
  try {
    await api('/api/session','POST'); health = await api('/healthz'); updateConnection();
    actions = await api('/api/actions'); renderActions(actions);
  } catch {
    connection('error', labels('Service unavailable', 'الخدمة غير متاحة'));
    $('preview-notice').hidden = false;
    $('preview-notice').textContent = labels('We couldn’t connect to Rafeeq. Make sure the service is running, then refresh this page.', 'تعذر الاتصال برفيق. تأكد من تشغيل الخدمة ثم حدّث الصفحة.');
  }
}
init();
