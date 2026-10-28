'use strict';
let language = 'en';
const $ = id => document.getElementById(id);
const labels = (en, ar) => language === 'ar' ? ar : en;
async function api(path, method = 'GET', body, officer = false) {
  const headers = {'Content-Type': 'application/json', 'X-Rafeeq-Client': '1'};
  if (officer) headers['X-Officer-Token'] = $('officer-token').value;
  const response = await fetch(path, {method, headers, credentials:'same-origin', body: body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : labels('Check the form inputs.', 'تحقق من بيانات النموذج.'));
  return data;
}
function message(text, role, trace) {
  const article = document.createElement('article'); article.className = `message ${role}`;
  const bubble = document.createElement('div'); bubble.className = 'bubble'; bubble.dir = 'auto'; bubble.textContent = text;
  article.append(bubble);
  if (trace) { const meta = document.createElement('div'); meta.className = 'trace'; meta.textContent = trace; bubble.append(meta); }
  $('messages').append(article); $('messages').scrollTop = $('messages').scrollHeight;
}
function renderActions(actions, target = 'actions', officer = false) {
  $(target).replaceChildren();
  if (!actions.length) { const p = document.createElement('p'); p.className='muted'; p.textContent=labels('No pending actions.', 'لا توجد إجراءات معلّقة.'); $(target).append(p); }
  for (const action of actions) {
    const card = document.createElement('div'); card.className='action-card';
    const title = document.createElement('strong'); title.textContent=`${action.tool} · ${action.status}`;
    const details = document.createElement('pre'); details.dir='ltr'; details.textContent=JSON.stringify({action:action.args, result:action.result}, null, 2);
    card.append(title, details);
    if (action.status === (officer ? 'awaiting_officer' : 'pending')) {
      for (const approve of [true, false]) {
        const button = document.createElement('button'); button.type='button';
        button.textContent=approve ? labels('Confirm', 'تأكيد') : labels('Reject', 'رفض');
        button.onclick=async () => {
          button.disabled=true;
          try {
            const result = await api(`/api/${officer ? 'officer/' : ''}actions/${encodeURIComponent(action.id)}/decision`, 'POST', {approve}, officer);
            message(JSON.stringify(result, null, 2), 'assistant');
            if (officer) renderActions(await api('/api/officer/actions','GET',undefined,true),'officer-actions',true);
            renderActions(await api('/api/actions'));
          } catch(error) { message(error.message,'assistant'); } finally { button.disabled=false; }
        };
        card.append(button);
      }
    }
    $(target).append(card);
  }
}
$('language').onclick=() => {
  language=language === 'en' ? 'ar' : 'en';
  document.documentElement.lang=language; document.documentElement.dir=language === 'ar' ? 'rtl' : 'ltr';
  document.querySelectorAll('[data-en]').forEach(el => {el.textContent=el.dataset[language];});
  $('language').textContent=language === 'ar' ? 'English' : 'العربية';
};
$('verify').onsubmit=async event => {
  event.preventDefault();
  const data=Object.fromEntries(new FormData(event.target));
  try {await api('/api/verify','POST',data); $('verification-status').textContent=labels('Verified for 15 minutes.', 'تم التحقق لمدة ١٥ دقيقة.');}
  catch(error) {$('verification-status').textContent=error.message;}
  finally {event.target.elements.last4.value='';event.target.elements.mobile.value='';}
};
$('chat').onsubmit=async event => {
  event.preventDefault(); const text=$('message').value.trim(); if (!text || $('send').disabled) return;
  message(text,'user'); $('message').value=''; $('send').disabled=true; $('messages').setAttribute('aria-busy','true');
  try {const data=await api('/api/chat','POST',{message:text}); message(data.reply,'assistant',`${data.stopped} · ${data.tools.join(' → ')} · ${data.usage.model_steps} steps · trace ${data.trace_id}`);renderActions(data.actions);}
  catch(error) {message(error.message,'assistant');}
  finally {$('send').disabled=false;$('messages').setAttribute('aria-busy','false');$('message').focus();}
};
$('message').onkeydown=event => {if(event.key==='Enter' && !event.shiftKey){event.preventDefault();$('chat').requestSubmit();}};
document.querySelectorAll('[data-question]').forEach(button => button.onclick=()=>{$('message').value=language==='ar'?button.dataset.arQuestion:button.dataset.question;$('message').focus();});
$('reset').onclick=async()=>{try{await api('/api/session','DELETE');location.reload();}catch(error){message(error.message,'assistant');}};
$('load-officer').onclick=async()=>{try{renderActions(await api('/api/officer/actions','GET',undefined,true),'officer-actions',true);}catch(error){message(error.message,'assistant');}};
async function init(){try{await api('/api/session','POST');const health=await api('/healthz');$('connection').textContent=health.ai_configured?labels('AI configured','الذكاء الاصطناعي مهيأ'):labels('API key needed','.env يتطلب مفتاح API');renderActions(await api('/api/actions'));}catch(error){$('connection').textContent=error.message;}}
init();
