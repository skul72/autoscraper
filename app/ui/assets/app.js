let lastStateData = {};

async function postJson(url, payload){
  const res = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload||{})});
  return await res.json();
}

async function postAction(path){
  const res = await fetch(path,{method:'POST'});
  const data = await res.json();
  alert(data.message||'OK');
  loadState();
}

function renderSlots(d){
  const select=document.getElementById('slot_select');
  const slots=d.slots||[];
  select.innerHTML=slots.map(s=>`<option value="${s.name}">${s.name}${s.is_default?' ⭐':''}</option>`).join('');
  select.value=d.current_slot||'';
  document.getElementById('slot_current_label').textContent=d.current_slot||'-';
  document.getElementById('slot_default_label').textContent=d.default_slot||'-';
  document.getElementById('slot_default_checkbox').checked=(d.current_slot||'')===(d.default_slot||'');
}

async function createSlot(){ const name=(document.getElementById('new_slot_name').value||'').trim(); if(!name) return; const d=await postJson('/slot/create',{slot_name:name}); alert(d.message||'OK'); loadState(); }
async function switchSlot(){ const slot=document.getElementById('slot_select').value; const d=await postJson('/slot/switch',{slot_name:slot}); alert(d.message||'OK'); loadState(); }
async function setDefaultSlotToggle(){ if(!document.getElementById('slot_default_checkbox').checked){loadState();return;} const slot=document.getElementById('slot_select').value; const d=await postJson('/slot/default',{slot_name:slot}); alert(d.message||'OK'); loadState(); }
async function deleteCurrentSlot(){ const slot=document.getElementById('slot_select').value; if(!slot)return; const d=await postJson('/slot/delete',{slot_name:slot}); alert(d.message||'OK'); loadState(); }

async function saveConfig(){
  const payload={verify_mode:document.getElementById('verify_mode').value,scope_mode:document.getElementById('scope_mode').value,scope_start:document.getElementById('scope_start').value,scope_end:document.getElementById('scope_end').value,scope_match_text:document.getElementById('scope_match_text').value,save_every_items:document.getElementById('save_every_items').value,save_every_minutes:document.getElementById('save_every_minutes').value,selected_categories:[]};
  const d=await postJson('/config',payload); alert(d.message||'OK'); loadState();
}

async function runMode(mode){ const d=await postJson('/run/'+mode,{}); alert(d.message||'OK'); loadState(); }
async function runPrimary(){ const d=await postJson('/run/primary',{}); alert(d.message||'OK'); loadState(); }

async function loadState(){
  const snap=await (await fetch('/state')).json();
  const d=snap.data||{}; lastStateData=d;
  ['status','run_mode_label','current_phase','timer_text','summary','current_category','current_item','saved_count','pending_count','queue_detected_count','new_links_detected','existing_links_detected','new_items_added','items_updated','items_unchanged','reused_categories','refetched_categories','updated_at','verify_mode_view','scope_mode_view','save_every_items_status','save_every_minutes_status'].forEach(id=>{const el=document.getElementById(id); if(el) el.textContent=(d[id]??'-');});
  document.getElementById('resume_info').textContent=(Number(d.resume_queue_total||0)>0)?`${d.resume_queue_index||0}/${d.resume_queue_total||0}`:'-';
  document.getElementById('primary_run_button').textContent=d.primary_button_label||'▶️ Iniciar';
  renderSlots(d);
  document.getElementById('logs').textContent=(snap.logs||[]).join('\n');
  document.getElementById('verify_mode').value=d.verify_mode||'normal';
  document.getElementById('scope_mode').value=d.scope_mode||'all';
  document.getElementById('scope_start').value=d.scope_start??1;
  document.getElementById('scope_end').value=d.scope_end??0;
  document.getElementById('scope_match_text').value=d.scope_match_text||'';
  document.getElementById('save_every_items').value=d.save_every_items??5;
  document.getElementById('save_every_minutes').value=d.save_every_minutes??1;
}

loadState();
setInterval(loadState,1200);
