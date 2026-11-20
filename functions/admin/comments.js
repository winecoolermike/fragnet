/* /admin/comments: tiny moderation page (no data in the page itself; it calls /api/admin/comments with the key you type).
   The key stays in this browser tab only (sessionStorage) and is sent as a header, never in the address. */
const PAGE = `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow"><title>Comments admin :: Esports Scoreboard</title>
<style>
body{margin:0;background:#14171b;color:#e6e2d6;font:17px/1.45 Verdana,Arial,sans-serif}
main{max-width:760px;margin:0 auto;padding:16px}
h1{font-size:22px;margin:4px 0 12px;color:#f0b35a}
label{display:block;margin:10px 0 4px}
input{width:100%;box-sizing:border-box;font-size:17px;padding:10px;border:1px solid #556;background:#0f1114;color:#e6e2d6;border-radius:4px}
button{font-size:16px;padding:10px 16px;border:1px solid #8a6a2f;background:#3a2c14;color:#f6e7c8;border-radius:4px;cursor:pointer;margin-top:10px}
button.del{background:#4a1d1d;border-color:#9a4a4a;margin:6px 0 0}
.c{border:1px solid #333a44;background:#1b1f25;border-radius:6px;padding:10px 12px;margin:10px 0}
.meta{color:#9aa3ad;font-size:14px}.b{white-space:pre-wrap;word-wrap:break-word;margin-top:6px}
#msg{margin:12px 0;color:#f0b35a}a{color:#f0b35a}
</style></head><body><main>
<h1>Comments admin</h1>
<p>Type the admin key, then tap <b>Show comments</b>. Tap <b>Delete</b> under any comment to remove it from the site.</p>
<form id="f"><label for="k">Admin key</label><input id="k" type="password" autocomplete="off" autocapitalize="off" spellcheck="false" required>
<button type="submit">Show comments</button></form>
<div id="msg" role="status"></div><div id="list"></div>
<p class="meta"><a href="/predictions/">Back to Predictions</a></p>
</main>
<script>
(function(){
  var k=document.getElementById("k"),msg=document.getElementById("msg"),list=document.getElementById("list");
  try{k.value=sessionStorage.getItem("esb-admin")||"";}catch(e){}
  function esc(s){return String(s==null?"":s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
  function api(method,q){return fetch("/api/admin/comments"+(q||""),{method:method,headers:{"X-Admin-Key":k.value.trim()},cache:"no-store"}).then(function(r){return r.json().then(function(j){j._s=r.status;return j;});});}
  function load(){
    msg.textContent="Loading...";
    api("GET").then(function(j){
      if(j.error){msg.textContent=j.error;list.innerHTML="";return;}
      try{sessionStorage.setItem("esb-admin",k.value.trim());}catch(e){}
      var items=j.items||[];msg.textContent=items.length+" comment"+(items.length===1?"":"s")+" (newest first).";
      list.innerHTML=items.map(function(c){return '<div class="c"><div class="meta">#'+esc(c.id)+' &middot; '+esc(new Date(c.t).toLocaleString("en-US",{timeZone:"America/Los_Angeles"}))+' PT &middot; <a href="/match/cs2/'+encodeURIComponent(c.m)+'/">match page</a></div><div><b>'+esc(c.name)+'</b></div><div class="b">'+esc(c.body)+'</div><button class="del" data-id="'+esc(c.id)+'">Delete</button></div>';}).join("");
    }).catch(function(){msg.textContent="Could not reach the server.";});
  }
  document.getElementById("f").addEventListener("submit",function(e){e.preventDefault();load();});
  list.addEventListener("click",function(e){var b=e.target.closest(".del");if(!b)return;if(!confirm("Delete comment #"+b.getAttribute("data-id")+"?"))return;
    api("DELETE","?id="+encodeURIComponent(b.getAttribute("data-id"))).then(function(j){msg.textContent=j.error||("Deleted comment #"+b.getAttribute("data-id")+".");load();});});
  if(k.value)load();
})();
</script></body></html>`;
export async function onRequest() {
  return new Response(PAGE, { headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow",
    "Content-Security-Policy": "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'none'; frame-ancestors 'none'; base-uri 'none'",
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer" } });
}
