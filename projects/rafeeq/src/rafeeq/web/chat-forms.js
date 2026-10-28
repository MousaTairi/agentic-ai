/* Secure inline workflow cards: identity fields are sent only to local endpoints, never the AI. */
function normalizeDigits(text) {
  return String(text).replace(/[٠-٩۰-۹]/g, char => String('٠١٢٣٤٥٦٧٨٩'.includes(char) ? '٠١٢٣٤٥٦٧٨٩'.indexOf(char) : '۰۱۲۳۴۵۶۷۸۹'.indexOf(char)));
}
function referenceValue(value) { return normalizeDigits(value).trim().toUpperCase().replace(/[‑–]/g, '-'); }
const documentLabels = {
  title_deed:['Title deed','صك الملكية'],engineering_drawings:['Stamped engineering drawings','مخططات هندسية معتمدة'],
  site_plan:['Site plan','مخطط الموقع'],contractor_contract:['Contractor contract','عقد المقاول'],
  works_description:['Description of works','وصف الأعمال'],photos:['Current photos','صور الوضع الحالي'],
  structural_report:['Structural report','تقرير إنشائي'],commercial_registration:['Commercial registration','السجل التجاري'],
  lease_or_title:['Lease or title deed','عقد الإيجار أو الملكية'],sign_design:['Sign design','تصميم اللوحة'],
  electrical_certificate:['Electrical safety certificate','شهادة السلامة الكهربائية'],
  vehicle_registration:['Vehicle registration','تسجيل المركبة'],worker_health_certificates:['Worker health certificates','الشهادات الصحية للعاملين'],
  passed_health_inspection:['Passed health inspection','اجتياز الفحص الصحي'],
  safety_plan:['Safety plan','خطة السلامة'],civil_defense_review:['Civil Defense review where required','مراجعة الدفاع المدني عند اللزوم'],
};
function bindNormalization(input, reference = false) {
  input.addEventListener('input', () => { input.value = reference ? referenceValue(input.value) : normalizeDigits(input.value).replace(/[\s-]/g, ''); });
}
function renderChatRequest(request) {
  const kind = request.type;
  if (kind === 'inspection_slots') {
    const card = element('form','workflow-card');card.dataset.kind=kind;
    card.append(element('h3','',labels('Choose your inspection slot','اختر موعد الفحص')));
    card.append(element('p','workflow-note',request.permit_id+' · '+request.district+' · '+labels('Riyadh local time; simulation dates','بتوقيت الرياض؛ مواعيد المحاكاة')));
    const select=element('select');select.name='slot';select.required=true;
    for(const slot of request.slots){const option=element('option','',formatSlot(slot));option.value=slot;select.append(option);}
    const selectLabel=element('label','',labels('Available appointment','الموعد المتاح'));selectLabel.append(select);card.append(selectLabel);
    const button=element('button','primary',labels('Prepare booking','تجهيز الحجز'));button.type='submit';
    const status=element('p','workflow-status');card.append(button,status);
    card.onsubmit=async event=>{
      event.preventDefault();button.disabled=true;
      try{
        await api('/api/inspection-proposal','POST',{permit_id:request.permit_id,slot:select.value.replace(' ','T')});
        actions=await api('/api/actions');renderActions(actions);
        card.dataset.complete='true';card.replaceChildren(element('p','workflow-success',labels('Review your booking below and confirm.','راجع الحجز أدناه ثم أكّد.')));
        const inline=element('div','inline-actions');$('messages').append(inline);
        renderActions(actions.filter(action=>action.status==='pending'),inline);scrollMessages();
      }catch(error){status.textContent=error.message;button.disabled=false;}
    };
    $('messages').append(card);scrollMessages();return;
  }
  const existing = document.querySelector('.workflow-card[data-kind="' + kind + '"]:not([data-complete])');
  if (existing) { existing.scrollIntoView({block:'center',behavior:'smooth'}); return; }
  $('chat-welcome')?.remove();
  const card = element('form','workflow-card'); card.dataset.kind = kind;
  const names = {registration:['Create your demo profile','إنشاء ملفك التجريبي'],verification:['Verify your application','التحقق من طلبك'],application:['Prepare your application','تجهيز طلبك']};
  card.append(element('h3','',labels(...(names[kind] || names.application))));
  card.append(element('p','workflow-note',kind === 'application' ?
    labels('Prepare a real record in the demo database. Review the fee before confirming. No real payment or permit approval.', 'أنشئ سجلًا في قاعدة البيانات التجريبية. راجع الرسوم قبل التأكيد. لا يوجد دفع حقيقي أو موافقة على التصريح.') :
    labels('Use synthetic demo details only. These fields stay with the local service and are not sent to the AI.', 'استخدم بيانات تجريبية فقط. تبقى هذه الحقول لدى الخدمة المحلية ولا تُرسل إلى الذكاء الاصطناعي.')));
  function field(name,en,ar,options={}) {
    const label=element('label','',labels(en,ar)), input=element('input');
    input.name=name; input.required=options.required !== false; input.type=options.type || 'text';
    input.autocomplete='off'; if(options.pattern) input.pattern=options.pattern;
    if(options.value) input.value=options.value;
    if(options.maxLength) input.maxLength=options.maxLength;
    label.append(input); card.append(label); return input;
  }
  const status=element('p','workflow-status'); status.setAttribute('role','status');
  const submit=element('button','primary',labels('Continue','متابعة')); submit.type='submit';
  if(kind === 'registration') {
    field('display_name','Demo display name','اسم تجريبي للعرض',{maxLength:60});
    const last=field('last4','Last 4 ID digits (demo)','آخر ٤ أرقام للهوية (تجريبي)',{type:'password',pattern:'[0-9]{4}',maxLength:4});
    const mobile=field('mobile','Mobile (demo)','الجوال (تجريبي)',{type:'tel',pattern:'[+]?[0-9]{9,14}'});
    bindNormalization(last);bindNormalization(mobile);
    const consent=element('label','check-label'), checkbox=element('input');
    checkbox.type='checkbox';checkbox.name='consent';checkbox.required=true;
    consent.append(checkbox,document.createTextNode(labels('I confirm these are synthetic details and want to create a demo profile.','أؤكد أن هذه بيانات افتراضية وأرغب في إنشاء ملف تجريبي.')));card.append(consent);
    card.onsubmit=async event=>{
      event.preventDefault();submit.disabled=true;
      try{
        await api('/api/register','POST',{display_name:card.elements.display_name.value.trim(),last4:last.value,mobile:mobile.value,consent:checkbox.checked});
        complete(labels('Your demo profile is ready. Let’s continue your application.','ملفك التجريبي جاهز. لنتابع طلبك.'));
        renderChatRequest({type:'application'});
      }catch(error){status.textContent=error.message;submit.disabled=false;}finally{last.value='';mobile.value='';}
    };
  } else if(kind === 'verification') {
    const reference=field('permit_id','Application reference','رقم الطلب',{value:request.permit_id || '',pattern:'(BLD|REN|SGN|FTR|EVT)-[0-9]{5}'});
    const last=field('last4','Last 4 ID digits','آخر ٤ أرقام للهوية',{type:'password',pattern:'[0-9]{4}',maxLength:4});
    const mobile=field('mobile','Registered mobile','الجوال المسجّل',{type:'tel',pattern:'[+]?[0-9]{9,14}'});
    bindNormalization(reference,true);bindNormalization(last);bindNormalization(mobile);
    card.onsubmit=async event=>{
      event.preventDefault();submit.disabled=true;
      try{
        await api('/api/verify','POST',{permit_id:referenceValue(reference.value),last4:last.value,mobile:mobile.value});
        verificationState(true,labels('Application verified.','تم التحقق من الطلب.'));
        $('verify').elements.permit_id.value=referenceValue(reference.value);
        complete(labels('Verified. I’ll continue your request.','تم التحقق. سأتابع طلبك.'));
        await sendMessage(labels('I verified my application. Continue this request: ','تحققت من طلبي. تابع هذا الطلب: ')+pendingGoal,true);
      }catch(error){status.textContent=error.message;submit.disabled=false;}finally{last.value='';mobile.value='';}
    };
  } else {
    const body=element('div','application-fields');
    const typeLabel=element('label','',labels('Permit type','نوع التصريح')), type=element('select');
    type.name='permit_type';
    for(const [value,en,ar] of [['BLD','Building','بناء'],['REN','Renovation','ترميم'],['SGN','Signage','لوحة تجارية'],['FTR','Food truck','عربة طعام'],['EVT','Event','فعالية']]){
      const option=element('option','',labels(en,ar));option.value=value;type.append(option);
    }
    const goal=pendingGoal || '';
    type.value=request.permit_type || (/food.?truck|عربة|عربات/i.test(goal)?'FTR':/sign|لوحة/i.test(goal)?'SGN':/renov|ترميم/i.test(goal)?'REN':/event|فعالي/i.test(goal)?'EVT':'BLD');
    typeLabel.append(type);card.append(typeLabel);
    const districtLabel=element('label','',labels('District','الحي')), district=element('select');district.name='district';
    for(const value of ['Al-Shati','Al-Jamiah','Al-Rawdah','Al-Olaya','Al-Nakheel','Al-Malqa']){const option=element('option','',value);option.value=value;district.append(option);}
    districtLabel.append(district);card.append(districtLabel,body);
    let options=null;
    function draw(){
      body.replaceChildren();if(!options)return;
      const t=type.value;
      function localField(name,en,ar,inputType='number'){
        const label=element('label','',labels(en,ar)),input=element('input');input.name=name;input.type=inputType;
        if(inputType==='number'){input.min='0.1';input.step='0.1';input.required=t!=='REN';}
        label.append(input);body.append(label);return input;
      }
      if(t==='BLD'||t==='REN') localField('area_m2','Area in m²','المساحة بالمتر المربع');
      if(t==='REN') {const checkbox=localField('structural','Structural works','أعمال إنشائية','checkbox');checkbox.className='inline-checkbox';}
      if(t==='SGN'){localField('sign_m2','Sign face area in m²','مساحة وجه اللوحة');localField('illuminated','Illuminated sign','لوحة مضيئة','checkbox');}
      if(t==='EVT'){const days=localField('event_days','Event days (1–14)','عدد أيام الفعالية (١–١٤)');days.min='1';days.max='14';days.step='1';const attendees=localField('attendees','Expected attendees','عدد الحضور المتوقع');attendees.min='1';attendees.step='1';}
      body.append(element('p','workflow-note',labels('Select documents you have (demo declarations, not uploaded files):','حدد المستندات المتوفرة (إقرارات تجريبية وليست ملفات مرفوعة):')));
      const docs=[...options.documents[t]];
      if(t==='REN')docs.push('structural_report');
      if(t==='SGN')docs.push('electrical_certificate');
      if(t==='EVT')docs.push('civil_defense_review');
      for(const doc of docs){
        const label=element('label','check-label'),input=element('input');input.type='checkbox';input.name='document';input.value=doc;
        label.append(input,document.createTextNode(labels(...(documentLabels[doc]||[doc,doc]))));body.append(label);
      }
    }
    type.onchange=draw;
    api('/api/application-options').then(data=>{options=data;draw();}).catch(error=>{status.textContent=error.message;});
    card.onsubmit=async event=>{
      event.preventDefault();submit.disabled=true;
      const data={permit_type:type.value,district:district.value,documents:[...card.querySelectorAll('[name=document]:checked')].map(input=>input.value)};
      for(const name of ['area_m2','sign_m2','event_days','attendees']){const input=card.elements[name];if(input?.value)data[name]=Number(input.value);}
      for(const name of ['structural','illuminated']){const input=card.elements[name];if(input)data[name]=input.checked;}
      try{
        await api('/api/application-draft','POST',data);
        actions=await api('/api/actions');renderActions(actions);
        complete(labels('Your draft is ready. Review the fee and missing documents below, then confirm to submit.','مسودة طلبك جاهزة. راجع الرسوم والمستندات الناقصة أدناه، ثم أكّد التقديم.'));
        const inline=element('div','inline-actions');$('messages').append(inline);renderActions(actions.filter(a=>a.tool==='submit_application'&&a.status==='pending'),inline);scrollMessages();
      }catch(error){status.textContent=error.message;submit.disabled=false;}
    };
  }
  function complete(text){
    card.dataset.complete='true';card.replaceChildren(element('p','workflow-success',text));
  }
  card.append(submit,status);$('messages').append(card);scrollMessages();
}
function mountReviewerWorkspace() {
  if($('reviewer-panel'))return;
  const panel=element('details','officer-panel');panel.id='reviewer-panel';
  panel.append(element('summary','',labels('Licensing reviewer demo workspace','مساحة موظف التراخيص التجريبية')));
  panel.append(element('p','',labels('Separate reviewer authorization is required. Starting review does not approve the permit.','يلزم تصريح مستقل لموظف التراخيص. بدء المراجعة لا يعني الموافقة على التصريح.')));
  const label=element('label','',labels('Reviewer token','رمز موظف التراخيص')),token=element('input');
  token.type='password';token.autocomplete='off';label.append(token);
  const load=element('button','secondary',labels('Load new applications','عرض الطلبات الجديدة')),queue=element('div');
  panel.append(label,load,queue);document.querySelector('main').append(panel);
  async function call(path,method='GET',body){
    const response=await fetch(path,{method,credentials:'same-origin',headers:{'X-Rafeeq-Client':'1','X-Reviewer-Token':token.value,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    if(!response.ok)throw new Error(labels('Reviewer authorization failed or the application cannot enter review.','تعذر التحقق من الموظف أو بدء مراجعة الطلب.'));
    return response.json();
  }
  load.onclick=async()=>{
    load.disabled=true;queue.replaceChildren();
    try{
      const rows=await call('/api/reviewer/applications');
      if(!rows.length)queue.append(element('p','',labels('No new applications.','لا توجد طلبات جديدة.')));
      for(const row of rows){
        const card=element('div','action-card');card.append(element('h3','',row.permit_id+' · '+row.status));
        card.append(element('p','action-note',row.info_requested || labels('Document declarations need validation.','إقرارات المستندات تحتاج إلى التحقق.')));
        const button=element('button','secondary',labels('Take into review','بدء المراجعة'));
        button.onclick=async()=>{button.disabled=true;try{await call('/api/reviewer/begin-review','POST',{permit_id:row.permit_id});card.replaceChildren(element('p','',row.permit_id+' · '+labels('Under review — not approved','قيد المراجعة — لم تتم الموافقة')));}catch(error){queue.append(element('p','workflow-status',error.message));button.disabled=false;}};
        card.append(button);queue.append(card);
      }
    }catch(error){queue.append(element('p','workflow-status',error.message));}finally{load.disabled=false;}
  };
}
