
let token=localStorage.getItem("teamToken")||"",config={liff_id:"",mock_login:false},state={parent:null,players:[],playerId:null,events:[],attendance:{}},pendingCode="",currentEventType="";
const $=id=>document.getElementById(id),money=n=>new Intl.NumberFormat("zh-TW",{style:"currency",currency:"TWD",maximumFractionDigits:0}).format(Number(n||0));
async function api(path,options={}){options.headers={...(options.headers||{}),"Content-Type":"application/json"};if(token)options.headers.Authorization=`Bearer ${token}`;const r=await fetch(path,options);if(!r.ok){let m="操作失敗";try{m=(await r.json()).detail||m}catch{}throw new Error(m)}return r.json()}
function toast(m){$("toast").textContent=m;$("toast").classList.add("show");setTimeout(()=>$("toast").classList.remove("show"),1800)}
function showOnly(id){["loading","login","friendship","binding","app"].forEach(x=>$(x).classList.toggle("hidden",x!==id))}
async function finishLogin(accessToken){const r=await api("/api/auth/line",{method:"POST",body:JSON.stringify({access_token:accessToken})});token=r.token;localStorage.setItem("teamToken",token);await loadApp()}
async function ensureLineFriendship(){
  if(config.mock_login && (!config.liff_id || typeof liff==="undefined")) return true;
  if(!config.liff_id || typeof liff==="undefined") return true;

  try{
    const friendship=await liff.getFriendship();
    if(friendship && friendship.friendFlag){
      $("friendshipError").classList.add("hidden");
      return true;
    }
    showOnly("friendship");
    return false;
  }catch(e){
    console.error("getFriendship failed:",e);
    $("friendshipError").textContent="無法確認好友狀態。請確認 LINE Login Channel 已連結『青山社區棒球隊小幫手』。";
    $("friendshipError").classList.remove("hidden");
    showOnly("friendship");
    return false;
  }
}

async function continueAfterFriendCheck(){
  const ok=await ensureLineFriendship();
  if(!ok)return;
  await loadApp();
}

async function start(){
  try{
    config=await api("/api/config");
    if(config.mock_login) $("mockLogin").classList.remove("hidden");

    if(config.liff_id && typeof liff!=="undefined"){
      $("loadingText").textContent="正在啟動 LINE...";
      await liff.init({liffId:config.liff_id});
      if(!liff.isLoggedIn()){
        liff.login({redirectUri:location.href});
        return;
      }
      const accessToken=liff.getAccessToken();
      if(!accessToken) throw new Error("無法取得 LINE access token");
      const r=await api("/api/auth/line",{method:"POST",body:JSON.stringify({access_token:accessToken})});
      token=r.token;
      localStorage.setItem("teamToken",token);
      await continueAfterFriendCheck();
      return;
    }

    if(token){
      try{await loadApp();return}catch{localStorage.removeItem("teamToken");token=""}
    }
    showOnly("login");
  }catch(e){
    console.error(e);
    $("loadingText").textContent=e.message||"LINE 初始化失敗";
    showOnly("login");
  }
}

$("lineLogin").onclick=async()=>{
  try{
    if(!config.liff_id)return toast("尚未設定 LINE_LIFF_ID");
    await liff.init({liffId:config.liff_id});
    if(!liff.isLoggedIn()){liff.login({redirectUri:location.href});return}
    const accessToken=liff.getAccessToken();
    if(!accessToken)throw new Error("無法取得 LINE access token");
    const r=await api("/api/auth/line",{method:"POST",body:JSON.stringify({access_token:accessToken})});
    token=r.token;
    localStorage.setItem("teamToken",token);
    await continueAfterFriendCheck();
  }catch(e){toast("LINE 登入失敗："+e.message)}
};
$("mockLogin").onclick=()=>finishLogin("mock").catch(e=>toast(e.message));$("retryBinding").onclick=()=>loadApp().catch(e=>toast(e.message));

async function loadApp(){const me=await api("/api/me");state.parent=me.parent;state.players=me.players;if(me.needs_binding||!state.players.length){$("bindingHello").textContent=`${state.parent.display_name}，登入成功`;showOnly("binding");return}state.playerId=state.playerId||state.players[0].id;$("hello").textContent=`${state.parent.display_name}，你好`;$("parentName").textContent=state.parent.display_name;$("childrenCount").textContent=`${state.players.length} 位`;$("playerSelect").innerHTML=state.players.map(p=>`<option value="${p.id}">${p.name}</option>`).join("");$("playerSelect").value=state.playerId;$("playerSelect").onchange=async e=>{state.playerId=Number(e.target.value);await refresh()};state.events=await api("/api/events");showOnly("app");await refresh();const eventId=Number(new URLSearchParams(location.search).get("event"));if(eventId&&state.events.find(x=>Number(x.id)===eventId)){setTimeout(()=>openEvent(eventId),250)}}

$("previewBindBtn").onclick=async()=>{const code=$("bindCodeInput").value.trim().toUpperCase();if(code.length<4)return toast("請輸入完整綁定碼");try{const d=await api("/api/bind/preview",{method:"POST",body:JSON.stringify({code})});pendingCode=code;const p=d.player;$("bindPreview").classList.remove("hidden");$("bindPreview").innerHTML=`<div class="bindResult"><div class="bindPlayer">⚾ ${p.name}</div><div>${p.team}${p.number?` / #${p.number}`:""}</div><div class="muted">目前已綁定 ${d.linked_parents}/${d.max_parents} 位家長</div>${d.already_bound?'<div class="bindOk">✅ 你已綁定此球員</div>':d.can_bind?'<button id="confirmBindBtn" class="primary">確認綁定</button>':'<div class="bindError">此球員已達家長綁定上限</div>'}</div>`;const b=$("confirmBindBtn");if(b)b.onclick=confirmBinding}catch(e){toast(e.message)}};
async function confirmBinding(){try{const d=await api("/api/bind/confirm",{method:"POST",body:JSON.stringify({code:pendingCode})});toast(`已綁定 ${d.player.name}`);$("bindCodeInput").value="";$("bindPreview").classList.add("hidden");await loadApp()}catch(e){toast(e.message)}}


async function previewExtraBinding(){
  const code=$("extraBindCodeInput").value.trim().toUpperCase();
  if(code.length<4)return toast("請輸入完整綁定碼");

  try{
    const d=await api("/api/bind/preview",{
      method:"POST",
      body:JSON.stringify({code})
    });

    pendingCode=code;
    const p=d.player;

    $("extraBindPreview").classList.remove("hidden");
    $("extraBindPreview").innerHTML=`
      <div class="bindResult">
        <div class="bindPlayer">⚾ ${p.name}</div>
        <div>${p.team}${p.number?` / #${p.number}`:""}</div>
        <div class="muted">目前已綁定 ${d.linked_parents}/${d.max_parents} 位家長</div>
        ${
          d.already_bound
            ? '<div class="bindOk">✅ 你已經綁定此球員</div>'
            : d.can_bind
              ? '<button id="extraConfirmBindBtn" class="primary">確認綁定</button>'
              : '<div class="bindError">此球員已達家長綁定上限</div>'
        }
      </div>`;

    const btn=$("extraConfirmBindBtn");
    if(btn)btn.onclick=confirmExtraBinding;

  }catch(e){
    toast(e.message);
  }
}

async function confirmExtraBinding(){
  try{
    const d=await api("/api/bind/confirm",{
      method:"POST",
      body:JSON.stringify({code:pendingCode})
    });

    toast(`已綁定 ${d.player.name}`);
    $("extraBindCodeInput").value="";
    $("extraBindPreview").classList.add("hidden");

    // Reload account/player list so the newly bound child appears immediately.
    state.playerId=null;
    await loadApp();

    // Return user to profile page after reload.
    document.querySelectorAll(".page").forEach(p=>p.classList.add("hidden"));
    $("profilePage").classList.remove("hidden");
    document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));
    const profileNav=document.querySelector('nav button[data-page="profilePage"]');
    if(profileNav)profileNav.classList.add("active");

  }catch(e){
    toast(e.message);
  }
}

async function refresh(){const p=state.players.find(x=>x.id===state.playerId);$("playerName").textContent=p.name;$("playerTeam").textContent=p.team;const a=await api(`/api/players/${state.playerId}/attendance`);state.attendance=Object.fromEntries(a.map(x=>[x.event_id,x]));const payments=await api(`/api/players/${state.playerId}/payments`);renderEvents();renderPayments(payments)}
function renderEvents(){
  $("events").innerHTML=state.events.map(ev=>{
    const a=state.attendance[ev.id],ans=a?(a.attendance_status==="attend"?"✅ 已登記出席":a.attendance_status==="leave"?"請假":"未確定"):"尚未回覆";
    const meet=ev.meet_time_tbd?"未定":(ev.meet_time||"未定");
    const matches=(ev.matches||[]).map((m,i)=>`<div class="matchLine"><strong>第${i+1}場</strong>　${m.game_time_tbd?"未定":(m.game_time||"未定")}　🆚 ${m.opponent||"未定"}</div>`).join("");
    return `<div class="card eventCard"><div class="top"><div><div>${ev.event_date}</div><h4>${ev.title}</h4></div><span class="status ${a?'paid':'unpaid'}">${ans}</span></div><div class="meta">📍 ${ev.location}</div><div class="meta">🕗 集合：${meet}</div>${matches?`<div class="matchList">${matches}</div>`:""}${ev.meal_enabled===false?"":`<div class="meta">🍱 ${money(ev.meal_price)}/份</div>`}<button onclick="openEvent(${ev.id})">${a?"修改登記":"立即回覆"}</button></div>`
  }).join("")||`<div class="card muted">目前沒有活動</div>`
}
function renderPayments(rows){const card=p=>`<div class="card payment"><div><strong>${p.title}</strong><div class="meta">${p.due_date||""}</div></div><div><strong>${money(p.amount)}</strong><div><span class="status ${p.status}">${p.status==="paid"?"已繳":p.status==="pending"?"待確認":"未繳"}</span></div></div></div>`;$("payments").innerHTML=rows.map(card).join("")||`<div class="card">目前沒有繳費項目</div>`;const u=rows.filter(x=>x.status!=="paid");$("paymentsPreview").innerHTML=u.slice(0,3).map(card).join("")||`<div class="card">目前沒有待繳費用</div>`}
window.openEvent=id=>{
  const ev=state.events.find(x=>Number(x.id)===Number(id));
  if(!ev)return;

  currentEventType=ev.event_type||"practice";
  const a=state.attendance[id];

  $("eventId").value=id;
  $("dialogEventTitle").textContent=ev.title;

  const s=a?.attendance_status||"attend";
  const r=document.querySelector(`input[name=status][value=${s}]`);
  if(r)r.checked=true;

  $("leaveReason").value=a?.leave_reason||"";
  $("attendanceNote").value=a?.attendance_note||"";

  const duration=a?.practice_duration||"full";
  const dr=document.querySelector(`input[name=practiceDuration][value=${duration}]`);
  if(dr)dr.checked=true;

  $("mealSection").classList.toggle("hidden",ev.meal_enabled===false);
  $("playerMeals").value=ev.meal_enabled===false?0:(a?.player_meals??1);
  $("parentMeals").value=ev.meal_enabled===false?0:(a?.parent_meals??0);

  toggleAttendanceOptions();
  eventDialog.showModal();
};
function toggleAttendanceOptions(){
  const status=document.querySelector("input[name=status]:checked").value;
  const isAttend=status==="attend";

  $("leaveBox").classList.toggle("hidden",isAttend);
  $("practiceAttendBox").classList.toggle(
    "hidden",
    !(isAttend && currentEventType==="practice")
  );
  $("gameAttendNoteBox").classList.toggle(
    "hidden",
    !(isAttend && currentEventType==="game")
  );
}
document.querySelectorAll("input[name=status]").forEach(x=>x.onchange=toggleAttendanceOptions);$("closeDialog").onclick=()=>eventDialog.close();
$("eventForm").onsubmit=async e=>{e.preventDefault();try{const id=Number($("eventId").value);await api(`/api/events/${id}/attendance`,{method:"PUT",body:JSON.stringify({
  player_id:state.playerId,
  attendance_status:document.querySelector("input[name=status]:checked").value,
  leave_reason:$("leaveReason").value,
  practice_duration:document.querySelector("input[name=practiceDuration]:checked")?.value||"full",
  attendance_note:$("attendanceNote").value,
  player_meals:$("mealSection").classList.contains("hidden")?0:Number($("playerMeals").value),
  parent_meals:$("mealSection").classList.contains("hidden")?0:Number($("parentMeals").value)
})});eventDialog.close();toast("登記完成");await refresh()}catch(e){toast(e.message)}};
document.querySelectorAll("nav button").forEach(btn=>btn.onclick=()=>{document.querySelectorAll(".page").forEach(p=>p.classList.add("hidden"));$(btn.dataset.page).classList.remove("hidden");document.querySelectorAll("nav button").forEach(b=>b.classList.remove("active"));btn.classList.add("active")});

const extraPreviewBtn=$("extraPreviewBindBtn");
if(extraPreviewBtn)extraPreviewBtn.onclick=previewExtraBinding;


const requestFriendBtn=$("requestFriendBtn");
if(requestFriendBtn){
  requestFriendBtn.onclick=async()=>{
    try{
      $("friendshipError").classList.add("hidden");
      if(typeof liff==="undefined" || !config.liff_id) throw new Error("LIFF 尚未初始化");
      if(typeof liff.isApiAvailable==="function" && !liff.isApiAvailable("requestFriendship")) throw new Error("目前環境不支援加入好友功能");
      await liff.requestFriendship();
      const friendship=await liff.getFriendship();
      if(friendship && friendship.friendFlag){
        toast("已加入青山社區棒球隊小幫手");
        await loadApp();
      }else{
        $("friendshipError").textContent="目前仍未偵測到好友狀態，請完成加入後再按『重新檢查』。";
        $("friendshipError").classList.remove("hidden");
      }
    }catch(e){
      console.error("requestFriendship failed:",e);
      $("friendshipError").textContent="加入好友沒有完成："+(e.message||"請稍後再試");
      $("friendshipError").classList.remove("hidden");
    }
  };
}

const recheckFriendBtn=$("recheckFriendBtn");
if(recheckFriendBtn){
  recheckFriendBtn.onclick=async()=>{
    try{
      const ok=await ensureLineFriendship();
      if(ok){toast("好友狀態確認完成");await loadApp()}
    }catch(e){toast(e.message)}
  };
}

start();
