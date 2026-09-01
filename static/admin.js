
let adminToken = sessionStorage.getItem("adminToken") || "";
let cache = {players:[],parents:[],events:[],payments:[]};

const $ = id => document.getElementById(id);
const fmtMoney = n => new Intl.NumberFormat("zh-TW",{style:"currency",currency:"TWD",maximumFractionDigits:0}).format(Number(n||0));

async function api(path, options={}){
  options.headers = {...(options.headers||{}), "Content-Type":"application/json"};
  if(adminToken) options.headers.Authorization = `Bearer ${adminToken}`;
  const r = await fetch(path, options);
  if(!r.ok){
    let msg="操作失敗";
    try{ msg=(await r.json()).detail||msg }catch{}
    if(r.status===401){ sessionStorage.removeItem("adminToken"); adminToken=""; showLogin(); }
    throw new Error(msg);
  }
  return r.status===204 ? null : r.json();
}
function toast(msg){$("toast").textContent=msg;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),1800)}
function showLogin(){$("loginBox").classList.remove("hidden");$("adminApp").classList.add("hidden")}
function showAdmin(){$("loginBox").classList.add("hidden");$("adminApp").classList.remove("hidden")}

$("loginBtn").onclick=async()=>{
  $("loginError").textContent="";
  try{
    const r=await api("/api/admin/login",{method:"POST",body:JSON.stringify({password:$("adminPassword").value})});
    adminToken=r.token;sessionStorage.setItem("adminToken",adminToken);showAdmin();await loadAll();
  }catch(e){$("loginError").textContent=e.message}
};
$("adminPassword").addEventListener("keydown",e=>{if(e.key==="Enter")$("loginBtn").click()});
$("logoutBtn").onclick=()=>{sessionStorage.removeItem("adminToken");adminToken="";showLogin()};

const titles={dashboard:"總覽",players:"球員管理",parents:"家長管理",events:"活動 / 比賽",payments:"繳費管理"};
window.showPage=async page=>{
  document.querySelectorAll(".page").forEach(x=>x.classList.add("hidden"));
  $(page).classList.remove("hidden");
  document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.page===page));
  $("pageTitle").textContent=titles[page];
  if(page==="dashboard") await loadDashboard();
  if(page==="players") await loadPlayers();
  if(page==="parents") await loadParents();
  if(page==="events") await loadEvents();
  if(page==="payments") await loadPayments();
};
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>showPage(b.dataset.page));

async function loadAll(){
  await Promise.all([loadPlayers(),loadParents(),loadEvents(),loadPayments(),loadDashboard()]);
}

async function loadDashboard(){
  const d=await api("/api/admin/dashboard");
  const items=[
    ["球員",d.players],["家長",d.parents],["近期活動",d.events],["未回覆",d.pending_replies],["未收款",fmtMoney(d.unpaid)]
  ];
  $("stats").innerHTML=items.map(x=>`<div class="stat"><div class="l">${x[0]}</div><div class="k">${x[1]}</div></div>`).join("");
}

async function loadPlayers(){
  cache.players=await api("/api/admin/players");
  $("playerTable").innerHTML=`<div class="tableWrap"><table><thead><tr><th>背號</th><th>姓名</th><th>組別</th><th>家長</th><th>狀態</th><th>操作</th></tr></thead><tbody>${
    cache.players.map(p=>`<tr>
      <td>${p.number||"-"}</td><td><strong>${p.name}</strong></td><td>${p.team}</td>
      <td>${(p.parents||[]).map(x=>`<span class="tag">${x.display_name}</span>`).join("")||"-"}</td>
      <td><span class="tag ${p.active?'green':'red'}">${p.active?"啟用":"停用"}</span></td>
      <td><div class="rowActions"><button onclick="openPlayer(${p.id})">編輯</button><button onclick="openBind(null,${p.id})">綁定家長</button></div></td>
    </tr>`).join("")
  }</tbody></table></div>`;
}

window.openPlayer=id=>{
  const p=id?cache.players.find(x=>x.id===id):null;
  $("playerDialogTitle").textContent=p?"編輯球員":"新增球員";
  $("playerId").value=p?.id||"";
  $("playerNameInput").value=p?.name||"";
  $("playerTeamInput").value=p?.team||"";
  $("playerNumberInput").value=p?.number||"";
  $("playerActiveInput").checked=p?.active??true;
  playerDialog.showModal();
};
$("playerForm").onsubmit=async e=>{
  e.preventDefault();
  const id=$("playerId").value;
  const body={name:$("playerNameInput").value,team:$("playerTeamInput").value,number:$("playerNumberInput").value,active:$("playerActiveInput").checked};
  try{
    await api(id?`/api/admin/players/${id}`:"/api/admin/players",{method:id?"PUT":"POST",body:JSON.stringify(body)});
    playerDialog.close();toast("球員資料已儲存");await loadPlayers();await loadDashboard();
  }catch(e){toast(e.message)}
};

async function loadParents(){
  cache.parents=await api("/api/admin/parents");
  $("parentTable").innerHTML=`<div class="tableWrap"><table><thead><tr><th>家長</th><th>電話</th><th>LINE User ID</th><th>綁定球員</th><th>操作</th></tr></thead><tbody>${
    cache.parents.map(p=>`<tr>
      <td><strong>${p.display_name}</strong></td><td>${p.phone||"-"}</td><td><code>${p.line_user_id}</code></td>
      <td>${(p.players||[]).map(x=>`<span class="tag">${x.name} / ${x.team}</span>`).join("")||"-"}</td>
      <td><div class="rowActions"><button onclick="openBind(${p.id},null)">綁定球員</button>${
        (p.players||[]).map(x=>`<button onclick="unbind(${p.id},${x.id})">解除 ${x.name}</button>`).join("")
      }</div></td>
    </tr>`).join("")
  }</tbody></table></div>`;
}

window.openParent=()=>{
  $("parentForm").reset();
  $("bindPlayerInput").innerHTML=`<option value="">先不綁定</option>`+cache.players.filter(p=>p.active).map(p=>`<option value="${p.id}">${p.name} / ${p.team}</option>`).join("");
  parentDialog.showModal();
};
$("parentForm").onsubmit=async e=>{
  e.preventDefault();
  try{
    const p=await api("/api/admin/parents",{method:"POST",body:JSON.stringify({
      display_name:$("parentNameInput").value,line_user_id:$("parentLineInput").value,phone:$("parentPhoneInput").value,is_primary:true
    })});
    const pid=$("bindPlayerInput").value;
    if(pid) await api("/api/admin/bind",{method:"POST",body:JSON.stringify({parent_id:p.id,player_id:Number(pid)})});
    parentDialog.close();toast("家長已新增");await loadParents();await loadDashboard();
  }catch(e){toast(e.message)}
};

window.openBind=(parentId,playerId)=>{
  $("bindParentSelect").innerHTML=cache.parents.map(p=>`<option value="${p.id}">${p.display_name}</option>`).join("");
  $("bindPlayerSelect").innerHTML=cache.players.filter(p=>p.active).map(p=>`<option value="${p.id}">${p.name} / ${p.team}</option>`).join("");
  if(parentId)$("bindParentSelect").value=parentId;
  if(playerId)$("bindPlayerSelect").value=playerId;
  bindDialog.showModal();
};
$("bindForm").onsubmit=async e=>{
  e.preventDefault();
  try{
    await api("/api/admin/bind",{method:"POST",body:JSON.stringify({parent_id:Number($("bindParentSelect").value),player_id:Number($("bindPlayerSelect").value)})});
    bindDialog.close();toast("綁定完成");await Promise.all([loadPlayers(),loadParents()]);
  }catch(e){toast(e.message)}
};
window.unbind=async(parentId,playerId)=>{
  if(!confirm("確定解除這個家長與球員的綁定？"))return;
  try{
    await api(`/api/admin/bind?parent_id=${parentId}&player_id=${playerId}`,{method:"DELETE"});
    toast("已解除綁定");await Promise.all([loadPlayers(),loadParents()]);
  }catch(e){toast(e.message)}
};

async function loadEvents(){
  cache.events=await api("/api/admin/events");
  $("eventTable").innerHTML=`<div class="tableWrap"><table><thead><tr><th>日期</th><th>活動</th><th>類型</th><th>邀請</th><th>回覆</th><th>出席</th><th>請假</th><th>餐點</th><th>操作</th></tr></thead><tbody>${
    cache.events.map(e=>`<tr>
      <td>${e.event_date}</td><td><strong>${e.title}</strong><div>${e.location}</div></td>
      <td><span class="tag">${e.event_type==="game"?"比賽":e.event_type==="practice"?"練球":"活動"}</span></td>
      <td>${e.invited}</td><td>${e.replied}<div class="tag ${Number(e.replied)<Number(e.invited)?'amber':'green'}">${Number(e.invited)-Number(e.replied)} 未回覆</div></td>
      <td>${e.attend}</td><td>${e.leave}</td><td>${e.meals} 份</td>
      <td><div class="rowActions"><button onclick="viewEvent(${e.id})">統計</button><button onclick="editEvent(${e.id})">編輯</button></div></td>
    </tr>`).join("")
  }</tbody></table></div>`;
}
function renderEventPlayers(selected=[]){
  const set=new Set(selected.map(Number));
  $("eventPlayerChoices").innerHTML=cache.players.filter(p=>p.active).map(p=>`
    <label class="choice"><input type="checkbox" value="${p.id}" ${set.has(Number(p.id))?"checked":""}> ${p.name} / ${p.team}${p.number?` #${p.number}`:""}</label>
  `).join("");
}
window.toggleAllPlayers=checked=>document.querySelectorAll("#eventPlayerChoices input").forEach(x=>x.checked=checked);

window.openEvent=()=>{
  $("adminEventForm").reset();$("editEventId").value="";$("eventDialogTitle").textContent="建立活動 / 比賽";$("eventStatusLabel").classList.add("hidden");$("eventMealInput").value=100;renderEventPlayers([]);eventDialog.showModal();
};
window.editEvent=async id=>{
  try{
    const d=await api(`/api/admin/events/${id}`);
    const e=d.event;
    $("editEventId").value=e.id;$("eventDialogTitle").textContent="編輯活動 / 比賽";
    $("eventTitleInput").value=e.title;$("eventDateInput").value=e.event_date;$("eventDeadlineInput").value=e.response_deadline||"";
    $("eventLocationInput").value=e.location;$("eventTypeInput").value=e.event_type;$("eventMealInput").value=e.meal_price;
    $("eventStatusInput").value=e.status;$("eventStatusLabel").classList.remove("hidden");renderEventPlayers(d.players.map(x=>x.id));eventDialog.showModal();
  }catch(e){toast(e.message)}
};
$("adminEventForm").onsubmit=async e=>{
  e.preventDefault();
  const id=$("editEventId").value;
  const player_ids=[...document.querySelectorAll("#eventPlayerChoices input:checked")].map(x=>Number(x.value));
  const body={
    title:$("eventTitleInput").value,event_date:$("eventDateInput").value,location:$("eventLocationInput").value,
    meal_price:Number($("eventMealInput").value||0),event_type:$("eventTypeInput").value,
    response_deadline:$("eventDeadlineInput").value||null,player_ids
  };
  if(id)body.status=$("eventStatusInput").value;
  try{
    await api(id?`/api/admin/events/${id}`:"/api/admin/events",{method:id?"PUT":"POST",body:JSON.stringify(body)});
    eventDialog.close();toast("活動已儲存");await loadEvents();await loadDashboard();
  }catch(e){toast(e.message)}
};

window.viewEvent=async id=>{
  try{
    const d=await api(`/api/admin/events/${id}`);
    $("eventDetailTitle").textContent=`${d.event.event_date}｜${d.event.title}`;
    const replied=d.players.filter(x=>x.attendance_status).length;
    const attend=d.players.filter(x=>x.attendance_status==="attend").length;
    const leave=d.players.filter(x=>x.attendance_status==="leave").length;
    const pending=d.players.length-replied;
    const meals=d.players.reduce((s,x)=>s+Number(x.player_meals||0)+Number(x.parent_meals||0),0);
    $("eventSummary").innerHTML=[
      ["邀請",d.players.length],["出席",attend],["請假",leave],["未回覆",pending],["餐點",`${meals} 份`]
    ].map(x=>`<div class="stat"><div class="l">${x[0]}</div><div class="k">${x[1]}</div></div>`).join("");
    $("eventDetailBody").innerHTML=`<div class="tableWrap"><table><thead><tr><th>球員</th><th>組別</th><th>回覆</th><th>原因</th><th>球員餐</th><th>家長餐</th></tr></thead><tbody>${
      d.players.map(p=>`<tr><td><strong>${p.name}</strong></td><td>${p.team}</td><td>${
        p.attendance_status==="attend"?'<span class="tag green">出席</span>':
        p.attendance_status==="leave"?'<span class="tag red">請假</span>':
        p.attendance_status==="maybe"?'<span class="tag amber">未確定</span>':
        '<span class="tag amber">未回覆</span>'
      }</td><td>${p.leave_reason||"-"}</td><td>${p.player_meals}</td><td>${p.parent_meals}</td></tr>`).join("")
    }</tbody></table></div>`;
    eventDetailDialog.showModal();
  }catch(e){toast(e.message)}
};

async function loadPayments(){
  cache.payments=await api("/api/admin/payments");
  $("paymentTable").innerHTML=`<div class="tableWrap"><table><thead><tr><th>球員</th><th>項目</th><th>金額</th><th>期限</th><th>狀態</th><th>操作</th></tr></thead><tbody>${
    cache.payments.map(p=>`<tr><td>${p.player_name} / ${p.team}</td><td><strong>${p.title}</strong><div>${p.note||""}</div></td><td>${fmtMoney(p.amount)}</td><td>${p.due_date||"-"}</td>
    <td><span class="tag ${p.status==="paid"?'green':p.status==="pending"?'amber':'red'}">${p.status==="paid"?"已繳":p.status==="pending"?"待確認":"未繳"}</span></td>
    <td><div class="rowActions"><button onclick="setPayment(${p.id},'paid')">已繳</button><button onclick="setPayment(${p.id},'pending')">待確認</button><button onclick="setPayment(${p.id},'unpaid')">未繳</button></div></td></tr>`).join("")
  }</tbody></table></div>`;
}
window.openPayment=()=>{
  $("paymentForm").reset();
  $("paymentPlayerInput").innerHTML=cache.players.filter(p=>p.active).map(p=>`<option value="${p.id}">${p.name} / ${p.team}</option>`).join("");
  paymentDialog.showModal();
};
$("paymentForm").onsubmit=async e=>{
  e.preventDefault();
  try{
    await api("/api/admin/payments",{method:"POST",body:JSON.stringify({
      player_id:Number($("paymentPlayerInput").value),title:$("paymentTitleInput").value,
      amount:Number($("paymentAmountInput").value),due_date:$("paymentDueInput").value||null,
      status:"unpaid",note:$("paymentNoteInput").value
    })});
    paymentDialog.close();toast("收費項目已建立");await loadPayments();await loadDashboard();
  }catch(e){toast(e.message)}
};
window.setPayment=async(id,status)=>{
  try{await api(`/api/admin/payments/${id}/status?status=${status}`,{method:"PUT"});toast("繳費狀態已更新");await loadPayments();await loadDashboard()}catch(e){toast(e.message)}
};

if(adminToken){showAdmin();loadAll().catch(()=>showLogin())}else showLogin();
