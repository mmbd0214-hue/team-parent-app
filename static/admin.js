
let adminToken=sessionStorage.getItem("adminToken")||"",cache={players:[],parents:[],events:[],payments:[]},currentEventId=null;
const $=id=>document.getElementById(id),fmtMoney=n=>new Intl.NumberFormat("zh-TW",{style:"currency",currency:"TWD",maximumFractionDigits:0}).format(Number(n||0));
async function api(path,options={}){options.headers={...(options.headers||{}),"Content-Type":"application/json"};if(adminToken)options.headers.Authorization=`Bearer ${adminToken}`;const r=await fetch(path,options);if(!r.ok){let m="操作失敗";try{m=(await r.json()).detail||m}catch{};if(r.status===401){sessionStorage.removeItem("adminToken");adminToken="";showLogin()}throw new Error(m)}return r.json()}
function toast(m){$("toast").textContent=m;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),2200)}
function showLogin(){$("loginBox").classList.remove("hidden");$("adminApp").classList.add("hidden")}function showAdmin(){$("loginBox").classList.add("hidden");$("adminApp").classList.remove("hidden")}
$("loginBtn").onclick=async()=>{try{const r=await api("/api/admin/login",{method:"POST",body:JSON.stringify({password:$("adminPassword").value})});adminToken=r.token;sessionStorage.setItem("adminToken",adminToken);showAdmin();await loadAll()}catch(e){$("loginError").textContent=e.message}};
$("adminPassword").addEventListener("keydown",e=>{if(e.key==="Enter")$("loginBtn").click()});$("logoutBtn").onclick=()=>{sessionStorage.clear();adminToken="";showLogin()};
const titles={dashboard:"總覽",players:"球員管理",parents:"家長管理",events:"活動 / 比賽",payments:"繳費管理",messages:"LINE 訊息中心"};
window.showPage=async p=>{document.querySelectorAll(".page").forEach(x=>x.classList.add("hidden"));$(p).classList.remove("hidden");document.querySelectorAll("nav button").forEach(b=>b.classList.toggle("active",b.dataset.page===p));$("pageTitle").textContent=titles[p];if(p==="dashboard")await loadDashboard();if(p==="players")await loadPlayers();if(p==="parents")await loadParents();if(p==="events")await loadEvents();if(p==="payments")await loadPayments();if(p==="messages")await loadMessages()};
document.querySelectorAll("nav button").forEach(b=>b.onclick=()=>showPage(b.dataset.page));
async function loadAll(){await Promise.all([loadPlayers(),loadParents(),loadEvents(),loadPayments(),loadDashboard()])}
async function loadDashboard(){const d=await api("/api/admin/dashboard");$("stats").innerHTML=[["球員",d.players],["家長",d.parents],["未綁定家長",d.unbound_parents],["近期活動",d.events],["未回覆",d.pending_replies],["未收款",fmtMoney(d.unpaid)]].map(x=>`<div class="stat"><div class="l">${x[0]}</div><div class="k">${x[1]}</div></div>`).join("")}

async function loadPlayers(){cache.players=await api("/api/admin/players");$("playerTable").innerHTML=`<div class="tableWrap"><table><thead><tr><th>背號</th><th>姓名</th><th>組別</th><th>綁定碼</th><th>家長</th><th>狀態</th><th>操作</th></tr></thead><tbody>${cache.players.map(p=>`<tr><td>${p.number||"-"}</td><td><strong>${p.name}</strong></td><td>${p.team}</td><td><code class="bindCode">${p.bind_code||"-"}</code><div class="muted">${p.linked_parent_count}/${p.max_parents} 位家長</div></td><td>${(p.parents||[]).map(x=>`<span class="tag">${x.display_name}</span>`).join("")||"-"}</td><td><span class="tag ${p.active?"green":"red"}">${p.active?"啟用":"停用"}</span></td><td><div class="rowActions"><button onclick="copyCode('${p.bind_code}')">複製碼</button><button onclick="resetCode(${p.id})">重設碼</button><button onclick="openPlayer(${p.id})">編輯</button><button onclick="openBind(null,${p.id})">綁家長</button><button onclick="deletePlayer(${p.id}, '${p.name.replace(/'/g, "\\'")}')">刪除</button></div></td></tr>`).join("")}</tbody></table></div>`}
window.copyCode=async c=>{try{await navigator.clipboard.writeText(c);toast("綁定碼已複製")}catch{toast(`綁定碼：${c}`)}};
window.resetCode=async id=>{if(!confirm("重設後舊綁定碼會立即失效，確定嗎？"))return;const r=await api(`/api/admin/players/${id}/reset-bind-code`,{method:"POST"});toast(`新綁定碼：${r.bind_code}`);await loadPlayers()};
window.openPlayer=id=>{const p=id?cache.players.find(x=>x.id===id):null;$("playerDialogTitle").textContent=p?"編輯球員":"新增球員";$("playerId").value=p?.id||"";$("playerNameInput").value=p?.name||"";$("playerTeamInput").value=p?.team||"";$("playerNumberInput").value=p?.number||"";$("playerMaxParentsInput").value=p?.max_parents||2;$("playerActiveInput").checked=p?.active??true;playerDialog.showModal()};
$("playerForm").onsubmit=async e=>{e.preventDefault();const id=$("playerId").value,b={name:$("playerNameInput").value,team:$("playerTeamInput").value,number:$("playerNumberInput").value,max_parents:Number($("playerMaxParentsInput").value||2),active:$("playerActiveInput").checked};try{await api(id?`/api/admin/players/${id}`:"/api/admin/players",{method:id?"PUT":"POST",body:JSON.stringify(b)});playerDialog.close();toast("球員已儲存");await Promise.all([loadPlayers(),loadDashboard()])}catch(e){toast(e.message)}};

async function loadParents() {
  cache.parents = await api("/api/admin/parents");

  $("parentTable").innerHTML = `
    <div class="tableWrap">
      <table>
        <thead>
          <tr>
            <th>家長</th>
            <th>電話</th>
            <th>LINE User ID</th>
            <th>綁定球員</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          ${cache.parents.map(p => `
            <tr>
              <td><strong>${p.display_name}</strong></td>
              <td>${p.phone || "-"}</td>
              <td><code>${p.line_user_id || "-"}</code></td>
              <td>
                ${
                  (p.players || []).length
                    ? (p.players || []).map(x =>
                        `<span class="tag">${x.name} / ${x.team}</span>`
                      ).join("")
                    : `<span class="tag amber">尚未綁定</span>`
                }
              </td>
              <td>
                <div class="rowActions">
                  <button onclick="openBind(${p.id}, null)">綁定球員</button>
                  ${(p.players || []).map(x => `
                    <button onclick="unbind(${p.id}, ${x.id})">
                      解除 ${x.name}
                    </button>
                  `).join("")}
                  <button onclick="deleteParent(${p.id})">刪除家長</button>
                </div>
              </td>
            </tr>
          `).join("")}
        </tbody>
      </table>
    </div>
  `;
}

window.openParent=()=>{$("parentForm").reset();$("bindPlayerInput").innerHTML=`<option value="">先不綁定</option>`+cache.players.filter(p=>p.active).map(p=>`<option value="${p.id}">${p.name}/${p.team}</option>`).join("");parentDialog.showModal()};
$("parentForm").onsubmit=async e=>{e.preventDefault();try{const p=await api("/api/admin/parents",{method:"POST",body:JSON.stringify({display_name:$("parentNameInput").value,line_user_id:$("parentLineInput").value,phone:$("parentPhoneInput").value,is_primary:true})});if($("bindPlayerInput").value)await api("/api/admin/bind",{method:"POST",body:JSON.stringify({parent_id:p.id,player_id:Number($("bindPlayerInput").value)})});parentDialog.close();toast("家長已新增");await Promise.all([loadParents(),loadPlayers(),loadDashboard()])}catch(e){toast(e.message)}};
window.openBind=(pa,pl)=>{$("bindParentSelect").innerHTML=cache.parents.map(x=>`<option value="${x.id}">${x.display_name}</option>`).join("");$("bindPlayerSelect").innerHTML=cache.players.filter(x=>x.active).map(x=>`<option value="${x.id}">${x.name}/${x.team}</option>`).join("");if(pa)$("bindParentSelect").value=pa;if(pl)$("bindPlayerSelect").value=pl;bindDialog.showModal()};
$("bindForm").onsubmit=async e=>{e.preventDefault();try{await api("/api/admin/bind",{method:"POST",body:JSON.stringify({parent_id:Number($("bindParentSelect").value),player_id:Number($("bindPlayerSelect").value)})});bindDialog.close();toast("綁定完成");await Promise.all([loadPlayers(),loadParents(),loadDashboard()])}catch(e){toast(e.message)}};
window.unbind=async(pa,pl)=>{if(!confirm("確定解除綁定？"))return;await api(`/api/admin/bind?parent_id=${pa}&player_id=${pl}`,{method:"DELETE"});await Promise.all([loadPlayers(),loadParents(),loadDashboard()]);toast("已解除綁定")};

function matchRowHtml(index,match={}){const t=match.game_time||"",tbd=!!match.game_time_tbd,o=match.opponent||"";return `<div class="matchRow"><div class="matchNo">第 ${index+1} 場</div><label>比賽時間<input class="matchTime" type="time" value="${t}" ${tbd?"disabled":""}></label><label>對戰對手<input class="matchOpponent" value="${o.replace(/"/g,"&quot;")}" placeholder="例如 KEEP"></label><label class="check"><input class="matchTimeTbd" type="checkbox" ${tbd?"checked":""}> 時間未定</label><button type="button" class="removeMatch" onclick="removeMatchRow(this)">刪除</button></div>`}
window.addMatchRow=(m={})=>{const r=$("matchRows");r.insertAdjacentHTML("beforeend",matchRowHtml(r.children.length,m));renumberMatchRows()};window.removeMatchRow=b=>{b.closest(".matchRow").remove();renumberMatchRows()};function renumberMatchRows(){[...$("matchRows").children].forEach((r,i)=>r.querySelector(".matchNo").textContent=`第 ${i+1} 場`)}function collectMatches(){return [...document.querySelectorAll(".matchRow")].map(r=>({game_time:r.querySelector(".matchTimeTbd").checked?null:(r.querySelector(".matchTime").value||null),game_time_tbd:r.querySelector(".matchTimeTbd").checked,opponent:r.querySelector(".matchOpponent").value.trim()}))}document.addEventListener("change",e=>{if(e.target.classList.contains("matchTimeTbd")){const r=e.target.closest(".matchRow"),t=r.querySelector(".matchTime");t.disabled=e.target.checked;if(e.target.checked)t.value=""}if(e.target.id==="eventMeetTimeTbdInput"){$("eventMeetTimeInput").disabled=e.target.checked;if(e.target.checked)$("eventMeetTimeInput").value=""}});

async function loadEvents(){cache.events=await api("/api/admin/events");$("eventTable").innerHTML=`<div class="tableWrap"><table><thead><tr><th>日期</th><th>活動</th><th>類型</th><th>通知對象</th><th>回覆</th><th>出席</th><th>請假</th><th>餐點</th><th>操作</th></tr></thead><tbody>${cache.events.map(e=>`<tr><td>${e.event_date}</td><td><strong>${e.title}</strong><div>${e.location}</div><div class="muted">集合：${e.meet_time_tbd?"未定":(e.meet_time||"未定")}｜${e.match_count||0} 場</div></td><td><span class="tag">${e.event_type==="game"?"比賽":e.event_type==="practice"?"練球":"活動"}</span></td><td>${e.invited} 位球員</td><td>${e.replied}/${e.invited} <span class="tag ${Number(e.replied)<Number(e.invited)?"amber":"green"}">${Number(e.invited)-Number(e.replied)} 未回覆</span></td><td>${e.attend}</td><td>${e.leave}</td><td>${e.meal_enabled===false?'<span class="tag">不訂餐</span>':`${e.meals} 份`}</td><td><div class="rowActions"><button onclick="viewEvent(${e.id})">統計 / 通知</button><button onclick="editEvent(${e.id})">編輯</button><button onclick="deleteEvent(${e.id}, '${e.title.replace(/'/g, "\\'")}')">刪除</button></div></td></tr>`).join("")}</tbody></table></div>`}
function renderEventPlayers(sel=[]){const s=new Set(sel.map(Number));$("eventPlayerChoices").innerHTML=cache.players.filter(p=>p.active).map(p=>`<label class="choice"><input type="checkbox" value="${p.id}" ${s.has(Number(p.id))?"checked":""}> ${p.name}/${p.team}${p.number?` #${p.number}`:""}</label>`).join("")}
window.toggleAllPlayers=v=>document.querySelectorAll("#eventPlayerChoices input").forEach(x=>x.checked=v);
function updateMealOptionUI(){
  const enabled=$("eventMealEnabledInput").checked;
  $("eventMealPriceWrap").classList.toggle("hidden",!enabled);
  $("eventMealInput").disabled=!enabled;
}
$("eventMealEnabledInput").onchange=updateMealOptionUI;

window.openEvent=()=>{$("adminEventForm").reset();$("editEventId").value="";$("eventDialogTitle").textContent="建立活動 / 比賽";$("eventStatusLabel").classList.add("hidden");$("eventMealEnabledInput").checked=true;$("eventMealInput").value=100;updateMealOptionUI();$("eventMeetTimeInput").value="";$("eventMeetTimeInput").disabled=false;$("eventMeetTimeTbdInput").checked=false;$("matchRows").innerHTML="";addMatchRow();renderEventPlayers([]);eventDialog.showModal()};
window.editEvent=async id=>{try{const d=await api(`/api/admin/events/${id}`),e=d.event;$("editEventId").value=e.id;$("eventDialogTitle").textContent="編輯活動 / 比賽";$("eventTitleInput").value=e.title;$("eventDateInput").value=e.event_date;$("eventDeadlineInput").value=e.response_deadline||"";$("eventLocationInput").value=e.location;$("eventTypeInput").value=e.event_type;$("eventMealEnabledInput").checked=e.meal_enabled!==false;$("eventMealInput").value=e.meal_price;updateMealOptionUI();$("eventStatusInput").value=e.status;$("eventStatusLabel").classList.remove("hidden");$("eventMeetTimeTbdInput").checked=!!e.meet_time_tbd;$("eventMeetTimeInput").disabled=!!e.meet_time_tbd;$("eventMeetTimeInput").value=e.meet_time||"";$("matchRows").innerHTML="";(d.matches||[]).forEach(m=>addMatchRow(m));if(!(d.matches||[]).length)addMatchRow();renderEventPlayers(d.players.map(x=>x.id));eventDialog.showModal()}catch(e){toast(e.message)}};
$("adminEventForm").onsubmit=async e=>{e.preventDefault();const id=$("editEventId").value,b={title:$("eventTitleInput").value,event_date:$("eventDateInput").value,location:$("eventLocationInput").value,meal_enabled:$("eventMealEnabledInput").checked,meal_price:$("eventMealEnabledInput").checked?Number($("eventMealInput").value||0):0,event_type:$("eventTypeInput").value,response_deadline:$("eventDeadlineInput").value||null,meet_time:$("eventMeetTimeTbdInput").checked?null:($("eventMeetTimeInput").value||null),meet_time_tbd:$("eventMeetTimeTbdInput").checked,matches:collectMatches(),player_ids:[...document.querySelectorAll("#eventPlayerChoices input:checked")].map(x=>Number(x.value))};if(id)b.status=$("eventStatusInput").value;try{await api(id?`/api/admin/events/${id}`:"/api/admin/events",{method:id?"PUT":"POST",body:JSON.stringify(b)});eventDialog.close();toast("活動已儲存");await Promise.all([loadEvents(),loadDashboard()])}catch(e){toast(e.message)}};

async function loadTargets(mode="all"){if(!currentEventId)return;const primary=$("primaryOnly").checked,d=await api(`/api/admin/events/${currentEventId}/notification-targets?mode=${mode}&primary_only=${primary}`);$("notifyTargets").innerHTML=`<div><strong>${mode==="unanswered"?"未回覆提醒":"本次通知"}：${d.recipient_count} 位 LINE 家長</strong></div><div class="recipientList">${d.recipients.map(r=>`<span class="tag green">${r.parent_name}｜${r.players.map(p=>p.name).join("、")}</span>`).join("")||'<span class="tag amber">沒有可通知家長</span>'}</div>${d.missing_count?`<div class="missingBox">⚠️ ${d.missing_count} 筆缺少可用 LINE User ID，無法推播。</div>`:""}`}
async function loadLogs(){const logs=await api(`/api/admin/events/${currentEventId}/notification-logs`);$("notifyLogs").innerHTML=`<div class="tableWrap"><table><thead><tr><th>時間</th><th>類型</th><th>家長</th><th>球員</th><th>結果</th></tr></thead><tbody>${logs.map(x=>`<tr><td>${new Date(x.sent_at).toLocaleString("zh-TW")}</td><td>${x.notification_type==="reminder"?"提醒":"通知"}</td><td>${x.parent_name||"-"}</td><td>${x.player_name||"-"}</td><td><span class="tag ${x.status==="sent"?"green":"red"}">${x.status==="sent"?"成功":"失敗"}</span>${x.error_message?`<div>${x.error_message}</div>`:""}</td></tr>`).join("")||'<tr><td colspan="5">尚無通知紀錄</td></tr>'}</tbody></table></div>`}
window.viewEvent=async id=>{try{currentEventId=id;const d=await api(`/api/admin/events/${id}`);$("eventDetailTitle").textContent=`${d.event.event_date}｜${d.event.title}`;const matchInfo=(d.matches||[]).map((m,i)=>`<span class="tag">第${i+1}場 ${m.game_time_tbd?"未定":(m.game_time||"未定")} vs ${m.opponent||"未定"}</span>`).join("");const replied=d.players.filter(x=>x.attendance_status).length,attend=d.players.filter(x=>x.attendance_status==="attend").length,leave=d.players.filter(x=>x.attendance_status==="leave").length,pending=d.players.length-replied,meals=d.players.reduce((s,x)=>s+Number(x.player_meals||0)+Number(x.parent_meals||0),0);$("eventSummary").innerHTML=[["集合",d.event.meet_time_tbd?"未定":(d.event.meet_time||"未定")],["出席",attend],["請假",leave],["未回覆",pending],["餐點",`${meals} 份`]].map(x=>`<div class="stat"><div class="l">${x[0]}</div><div class="k">${x[1]}</div></div>`).join("");$("eventDetailBody").innerHTML=`<div class="panel"><strong>比賽場次</strong><div class="recipientList">${matchInfo||"<span class=\"tag amber\">尚未設定場次</span>"}</div></div><div class="tableWrap"><table><thead><tr><th>球員</th><th>組別</th><th>回覆</th><th>出席方式 / 備註</th><th>請假原因</th><th>球員餐</th><th>家長餐</th></tr></thead><tbody>${d.players.map(p=>`<tr><td><strong>${p.name}</strong></td><td>${p.team}</td><td>${p.attendance_status==="attend"?'<span class="tag green">出席</span>':p.attendance_status==="leave"?'<span class="tag red">請假</span>':p.attendance_status==="maybe"?'<span class="tag amber">未確定</span>':'<span class="tag amber">未回覆</span>'}</td><td>${p.attendance_status==="attend"?(d.event.event_type==="practice"?(p.practice_duration==="half"?"練半天":"全天"):(p.attendance_note||"-")):"-"}</td><td>${p.leave_reason||"-"}</td><td>${p.player_meals}</td><td>${p.parent_meals}</td></tr>`).join("")}</tbody></table></div>`;$("primaryOnly").checked=false;await Promise.all([loadTargets("all"),loadLogs()]);eventDetailDialog.showModal()}catch(e){toast(e.message)}};
$("primaryOnly").onchange=()=>loadTargets("all");
$("notifyAllBtn").onclick=async()=>{await loadTargets("all");if(!confirm("確定發送 LINE 比賽通知？"))return;try{const r=await api(`/api/admin/events/${currentEventId}/notify`,{method:"POST",body:JSON.stringify({mode:"all",primary_only:$("primaryOnly").checked})});toast(`LINE 通知：成功 ${r.sent}、失敗 ${r.failed}`);await loadLogs()}catch(e){toast(e.message)}};
$("notifyPendingBtn").onclick=async()=>{await loadTargets("unanswered");if(!confirm("確定只提醒尚未回覆的家長？"))return;try{const r=await api(`/api/admin/events/${currentEventId}/notify`,{method:"POST",body:JSON.stringify({mode:"unanswered",primary_only:$("primaryOnly").checked})});toast(`提醒：成功 ${r.sent}、失敗 ${r.failed}`);await Promise.all([loadTargets("unanswered"),loadLogs()])}catch(e){toast(e.message)}};

async function loadPayments(){cache.payments=await api("/api/admin/payments");$("paymentTable").innerHTML=`<div class="tableWrap"><table><thead><tr><th>球員</th><th>項目</th><th>金額</th><th>期限</th><th>狀態</th><th>操作</th></tr></thead><tbody>${cache.payments.map(p=>`<tr><td>${p.player_name}/${p.team}</td><td><strong>${p.title}</strong><div>${p.note||""}</div></td><td>${fmtMoney(p.amount)}</td><td>${p.due_date||"-"}</td><td><span class="tag ${p.status==="paid"?"green":p.status==="pending"?"amber":"red"}">${p.status==="paid"?"已繳":p.status==="pending"?"待確認":"未繳"}</span></td><td><div class="rowActions"><button onclick="setPayment(${p.id},'paid')">已繳</button><button onclick="setPayment(${p.id},'pending')">待確認</button><button onclick="setPayment(${p.id},'unpaid')">未繳</button><button onclick="deletePayment(${p.id})">刪除</button></div></td></tr>`).join("")}</tbody></table></div>`}

function updatePaymentTargetUI(){
  const type=$("paymentTargetType").value;
  $("paymentTeamWrap").classList.toggle("hidden",type!=="team");
  $("paymentPlayerWrap").classList.toggle("hidden",type!=="player");
}
$("paymentTargetType").onchange=updatePaymentTargetUI;

window.openPayment=()=>{
  $("paymentForm").reset();

  $("paymentPlayerInput").innerHTML=cache.players
    .filter(p=>p.active)
    .map(p=>`<option value="${p.id}">${p.name}/${p.team}</option>`)
    .join("");

  $("paymentTargetType").value="all";
  updatePaymentTargetUI();

  paymentDialog.showModal();
};
$("paymentForm").onsubmit=async e=>{
  e.preventDefault();

  try{
    const targetType=$("paymentTargetType").value;
    let targetValue=null;

    let targetValues=[];

    if(targetType==="team"){
      targetValues=[...document.querySelectorAll('input[name="paymentTeam"]:checked')].map(x=>x.value);
      if(!targetValues.length){
        toast("請至少選擇一個組別");
        return;
      }
    }else if(targetType==="player"){
      targetValue=$("paymentPlayerInput").value;
    }

    const r=await api("/api/admin/payments/batch",{
      method:"POST",
      body:JSON.stringify({
        target_type:targetType,
        target_value:targetValue,
        target_values:targetValues,
        title:$("paymentTitleInput").value,
        amount:Number($("paymentAmountInput").value),
        due_date:$("paymentDueInput").value||null,
        status:"unpaid",
        note:$("paymentNoteInput").value
      })
    });

    paymentDialog.close();
    toast(`收費已建立，共 ${r.created_count} 位球員`);

    await Promise.all([
      loadPayments(),
      loadDashboard()
    ]);
  }catch(e){
    toast(e.message);
  }
};
window.setPayment=async(id,status)=>{try{await api(`/api/admin/payments/${id}/status?status=${status}`,{method:"PUT"});toast("狀態已更新");await Promise.all([loadPayments(),loadDashboard()])}catch(e){toast(e.message)}};


window.deletePayment = async (id) => {
  const p = cache.payments.find(x => Number(x.id) === Number(id));

  if (!p) {
    toast("找不到繳費資料");
    return;
  }

  const msg =
    `確定要刪除這筆繳費項目嗎？\n\n` +
    `球員：${p.player_name} / ${p.team}\n` +
    `項目：${p.title}\n` +
    `金額：${fmtMoney(p.amount)}\n` +
    `狀態：${p.status === "paid" ? "已繳" : p.status === "pending" ? "待確認" : "未繳"}\n\n` +
    `刪除後無法復原。`;

  if (!confirm(msg)) return;

  try {
    await api(`/api/admin/payments/${id}`, {
      method: "DELETE"
    });

    toast(`已刪除繳費項目：${p.title}`);

    await Promise.all([
      loadPayments(),
      loadDashboard()
    ]);
  } catch (e) {
    toast(e.message);
  }
};


function updateMessageTargetUI(){
  const type=$("messageTargetType").value;
  $("messageTeamWrap").classList.toggle("hidden",type!=="team");
  $("messageParentWrap").classList.toggle("hidden",type!=="parent");
  previewMessageRecipients();
}

function selectedMessageTargets(){
  const type=$("messageTargetType").value;
  if(type==="team"){
    return [...document.querySelectorAll('input[name="messageTeam"]:checked')].map(x=>x.value);
  }
  if(type==="parent"){
    return [...document.querySelectorAll('input[name="messageParent"]:checked')].map(x=>x.value);
  }
  return [];
}

async function previewMessageRecipients(){
  if(!$("messageTargetType"))return;
  const type=$("messageTargetType").value;
  const values=selectedMessageTargets();

  if((type==="team"||type==="parent")&&!values.length){
    $("messageRecipientCount").textContent="預計發送：0 位家長";
    $("messageRecipientNames").innerHTML="";
    return;
  }

  try{
    const d=await api(`/api/admin/messages/preview?target_type=${encodeURIComponent(type)}&target_values=${encodeURIComponent(values.join(","))}`);
    $("messageRecipientCount").textContent=`預計發送：${d.recipient_count} 位家長`;
    $("messageRecipientNames").innerHTML=
      d.recipients.slice(0,30).map(x=>`<span class="tag">${x.display_name}</span>`).join("")+
      (d.recipient_count>30?`<span class="tag amber">另 ${d.recipient_count-30} 位</span>`:"");
  }catch(e){
    $("messageRecipientCount").textContent="無法取得發送對象";
    $("messageRecipientNames").innerHTML="";
  }
}

async function loadMessageLogs(){
  const rows=await api("/api/admin/messages/logs?limit=100");
  $("messageLogs").innerHTML=`<div class="tableWrap"><table><thead><tr><th>時間</th><th>家長</th><th>對象</th><th>訊息</th><th>結果</th></tr></thead><tbody>${
    rows.map(x=>`<tr><td>${new Date(x.sent_at).toLocaleString("zh-TW")}</td><td>${x.recipient_name||"-"}</td><td>${x.target_label||x.target_type}</td><td class="messageLogText">${x.message_text||""}</td><td><span class="tag ${x.status==="sent"?"green":"red"}">${x.status==="sent"?"成功":"失敗"}</span>${x.error_message?`<div class="muted">${x.error_message}</div>`:""}</td></tr>`).join("")||'<tr><td colspan="5">尚無訊息紀錄</td></tr>'
  }</tbody></table></div>`;
}

async function loadMessages(){
  if(!cache.parents.length)await loadParents();

  $("messageParentChoices").innerHTML=cache.parents.map(p=>`
    <label class="check parentChoice">
      <input type="checkbox" name="messageParent" value="${p.id}">
      ${p.display_name}
      ${(p.players||[]).length?`<span class="muted">(${p.players.map(x=>x.name).join("、")})</span>`:""}
    </label>`).join("");

  updateMessageTargetUI();
  await loadMessageLogs();
}

$("messageTargetType").onchange=updateMessageTargetUI;

document.addEventListener("change",e=>{
  if(e.target.name==="messageTeam"||e.target.name==="messageParent"){
    previewMessageRecipients();
  }
});

$("messageText").addEventListener("input",()=>{
  $("messageCharCount").textContent=$("messageText").value.length;
});

$("sendMessageBtn").onclick=async()=>{
  const type=$("messageTargetType").value;
  const values=selectedMessageTargets();
  const message=$("messageText").value.trim();

  if(!message)return toast("請輸入訊息內容");
  if((type==="team"||type==="parent")&&!values.length){
    return toast(type==="team"?"請至少選擇一個組別":"請至少選擇一位家長");
  }

  await previewMessageRecipients();

  if(!confirm(`${$("messageRecipientCount").textContent}\n\n訊息內容：\n${message}\n\n確定發送？`))return;

  try{
    $("sendMessageBtn").disabled=true;
    $("sendMessageBtn").textContent="發送中...";

    const r=await api("/api/admin/messages/send",{
      method:"POST",
      body:JSON.stringify({target_type:type,target_values:values,message})
    });

    toast(`發送完成：成功 ${r.sent}、失敗 ${r.failed}`);
    $("messageText").value="";
    $("messageCharCount").textContent="0";
    await loadMessageLogs();
  }catch(e){
    toast(e.message);
  }finally{
    $("sendMessageBtn").disabled=false;
    $("sendMessageBtn").textContent="📨 發送 LINE 訊息";
  }
};


if(adminToken){showAdmin();loadAll().catch(()=>showLogin())}else showLogin();

// === DELETE helpers to add into static/admin.js ===

window.deletePlayer = async (id, name) => {
  const p = cache.players.find(x => Number(x.id) === Number(id));
  const linked = Number(p?.linked_parent_count || 0);

  const msg =
    `確定要永久刪除球員「${name}」嗎？\n\n` +
    `此操作會一併刪除：\n` +
    `• 家長綁定\n` +
    `• 活動名單\n` +
    `• 出席 / 請假紀錄\n` +
    `• 訂餐紀錄\n` +
    `• 繳費紀錄\n` +
    (linked ? `\n目前綁定家長：${linked} 位\n` : "") +
    `\n此操作無法復原。`;

  if (!confirm(msg)) return;

  try {
    await api(`/api/admin/players/${id}`, {method:"DELETE"});
    toast(`已刪除球員：${name}`);
    await Promise.all([
      loadPlayers(),
      loadParents(),
      loadEvents(),
      loadPayments(),
      loadDashboard()
    ]);
  } catch (e) {
    toast(e.message);
  }
};


window.deleteEvent = async (id, title) => {
  const e = cache.events.find(x => Number(x.id) === Number(id));

  const msg =
    `確定要永久刪除活動「${title}」嗎？\n\n` +
    `日期：${e?.event_date || "-"}\n` +
    `此操作會一併刪除：\n` +
    `• 活動指定球員\n` +
    `• 出席 / 請假紀錄\n` +
    `• 訂餐紀錄\n` +
    `• LINE 通知紀錄\n\n` +
    `此操作無法復原。`;

  if (!confirm(msg)) return;

  try {
    await api(`/api/admin/events/${id}`, {method:"DELETE"});
    toast(`已刪除活動：${title}`);
    await Promise.all([
      loadEvents(),
      loadDashboard()
    ]);
  } catch (e) {
    toast(e.message);
  }
};



window.deleteParent = async (id) => {
  const p = cache.parents.find(x => Number(x.id) === Number(id));

  if (!p) {
    toast("找不到家長資料");
    return;
  }

  const children = (p.players || [])
    .map(x => `${x.name} / ${x.team}`)
    .join("、");

  let msg = `確定要刪除家長「${p.display_name}」嗎？\n\n`;

  if (children) {
    msg += `目前綁定球員：${children}\n\n`;
  }

  msg +=
    `刪除後會解除此家長與所有球員的綁定。\n` +
    `球員、活動、出席、訂餐及繳費資料不會被刪除。\n\n` +
    `如果家長之後再次使用 LINE 登入，系統會重新建立帳號，並需要重新輸入球員綁定碼。\n\n` +
    `確定刪除？`;

  if (!confirm(msg)) return;

  try {
    await api(`/api/admin/parents/${id}`, {method: "DELETE"});
    toast(`已刪除家長：${p.display_name}`);

    await Promise.all([
      loadParents(),
      loadPlayers(),
      loadDashboard()
    ]);
  } catch (e) {
    toast(e.message);
  }
};
