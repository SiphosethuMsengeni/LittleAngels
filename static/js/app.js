const products = window.SHOP_PRODUCTS || [];
const cartVersion = "3";
const storedCart = localStorage.getItem("littleAngelsCartVersion") === cartVersion
  ? JSON.parse(localStorage.getItem("littleAngelsCart") || "[]")
  : [];
const cart = new Map(storedCart.filter(([key]) => {
  const [id, size] = String(key).split("|");
  return products.some(product => product.id === Number(id) && product.sizes.some(entry => entry.name === size));
}));
localStorage.setItem("littleAngelsCartVersion", cartVersion);
const $ = (id) => document.getElementById(id);
const money = (p) => p == null ? "Price on request" : `R ${Number(p).toFixed(2)}`;
const imageUrl = (filename) => filename.startsWith("uploads/")
  ? `/media/${encodeURIComponent(filename.slice("uploads/".length))}`
  : `/static/images/${filename.split("/").map(encodeURIComponent).join("/")}`;
let activeProduct = null;
let activePhotoIndex = 0;
let touchStartX = null;
function saveCart(){localStorage.setItem("littleAngelsCart",JSON.stringify([...cart.entries()]));renderCart();}
function showToast(message){const t=$("toast");t.textContent=message;t.classList.add("show");setTimeout(()=>t.classList.remove("show"),2100);}
function renderCart(){
  const count=[...cart.values()].reduce((a,b)=>a+b,0);
  $("cart-count").textContent=count;$("cart-total").textContent=count;
  const host=$("cart-items");
  if(!count){host.innerHTML='<p class="cart-empty">Your basket is waiting for something lovely ♡</p>';return;}
  host.innerHTML="";
  for(const [key,qty] of cart){
    const [id,sizeName]=String(key).split("|");
    const p=products.find(x=>x.id===Number(id));if(!p)continue;
    const size=p.sizes.find(entry=>entry.name===sizeName);
    const row=document.createElement("div");row.className="cart-row";
    row.innerHTML=`<img src="${imageUrl(p.images[0])}" alt=""><div class="cart-row-info"><strong>${escapeHtml(p.name)}</strong><small>Size ${escapeHtml(sizeName)} · ${money(p.price)}</small><div class="qty-controls"><button data-qty="${escapeHtml(key)}" data-change="-1">−</button><span>${qty}</span><button data-qty="${escapeHtml(key)}" data-change="1" ${!size||qty>=Math.min(size.stock,20)?"disabled":""}>+</button></div></div><button class="remove-item" data-remove="${escapeHtml(key)}" aria-label="Remove item">×</button>`;
    host.appendChild(row);
  }
}
function escapeHtml(s){return String(s).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
function add(productId,sizeName){
  const product=products.find(item=>item.id===Number(productId));
  const size=product?.sizes.find(entry=>entry.name===sizeName);
  if(!product||!size){showToast("Choose an available size first.");return;}
  const key=`${product.id}|${size.name}`,quantity=cart.get(key)||0;
  if(quantity>=Math.min(size.stock,20)){showToast("There is no more stock available for that size in this order.");return;}
  cart.set(key,quantity+1);saveCart();showToast("Added to your basket ♡");
}
function openProduct(product){
  activeProduct=product;
  activePhotoIndex=0;
  $("gallery-title").textContent=product.name;
  $("gallery-category").textContent=product.category;
  $("gallery-description").textContent=product.description||"";
  $("gallery-price").textContent=money(product.price);
  const sizeSelect=$("gallery-size");
  const firstInStock=product.sizes.findIndex(entry=>entry.stock>0);
  sizeSelect.innerHTML=product.sizes.map((size,index)=>`<option value="${escapeHtml(size.name)}" ${size.stock<1?"disabled":""} ${index===(firstInStock<0?0:firstInStock)?"selected":""}>${escapeHtml(size.name)} — ${size.stock} in stock</option>`).join("");
  if(!product.sizes.length)sizeSelect.innerHTML='<option value="">No sizes configured</option>';
  $("gallery-add").dataset.add=product.id;
  $("gallery-add").disabled=!product.sizes.some(size=>size.stock>0);
  $("product-modal").classList.add("show");
  renderGallery();
}
function renderGallery(){
  if(!activeProduct)return;
  const images=activeProduct.images;
  const image=$("gallery-image");
  image.src=imageUrl(images[activePhotoIndex]);
  image.alt=`${activeProduct.name}, photo ${activePhotoIndex+1} of ${images.length}`;
  $("gallery-position").textContent=`Photo ${activePhotoIndex+1} of ${images.length}`;
  $("gallery-previous").disabled=images.length<2;
  $("gallery-next").disabled=images.length<2;
  $("gallery-dots").innerHTML=images.map((_,index)=>`<button class="gallery-dot${index===activePhotoIndex?" active":""}" type="button" data-gallery-index="${index}" aria-label="Show photo ${index+1}" aria-current="${index===activePhotoIndex}"></button>`).join("");
  $("gallery-thumbnails").innerHTML=images.map((src,index)=>`<button class="gallery-thumbnail${index===activePhotoIndex?" active":""}" type="button" data-gallery-index="${index}" aria-label="Show photo ${index+1}" aria-current="${index===activePhotoIndex}"><img src="${imageUrl(src)}" alt="" loading="lazy"></button>`).join("");
}
function changePhoto(step){
  if(!activeProduct||activeProduct.images.length<2)return;
  activePhotoIndex=(activePhotoIndex+step+activeProduct.images.length)%activeProduct.images.length;
  renderGallery();
}
function closeProduct(){
  $("product-modal").classList.remove("show");
  activeProduct=null;
}
function openCart(){ $("cart-drawer").classList.add("open");$("drawer-backdrop").classList.add("show");$("cart-drawer").setAttribute("aria-hidden","false");}
function closeCart(){ $("cart-drawer").classList.remove("open");$("drawer-backdrop").classList.remove("show");$("cart-drawer").setAttribute("aria-hidden","true");}
function selectedItems(){return [...cart.entries()].map(([key,quantity])=>{const [id,size]=String(key).split("|");return {id:Number(id),size,quantity,product:products.find(p=>p.id===Number(id))};}).filter(x=>x.product);}
function orderText(formData){
 const lines=selectedItems().map(x=>`• ${x.product.name} — size ${x.size} x ${x.quantity} (${money(x.product.price)})`);
 return `Hello Little Angels Boutique! I would like to place an order.\n\n${lines.join("\n")}\n\nName: ${formData.get("name")||""}\nPhone: ${formData.get("phone")||""}\nEmail: ${formData.get("email")||"Not provided"}\nCollection/delivery: ${formData.get("delivery")||""}\nAddress: ${formData.get("address")||"Not provided"}\nSize requests/notes: ${formData.get("notes")||"None"}\n\nPlease confirm availability and final prices.`;
}
function updateSummary(){
 const items=selectedItems();
 $("order-summary").innerHTML="<strong>Your basket</strong><br>"+items.map(x=>`${escapeHtml(x.product.name)} — size ${escapeHtml(x.size)} × ${x.quantity} — ${money(x.product.price)}`).join("<br>");
}
document.addEventListener("click",e=>{
 const addBtn=e.target.closest("[data-add]");if(addBtn)add(addBtn.dataset.add,$("gallery-size").value);
 const choose=e.target.closest("[data-choose-size]");if(choose){const p=products.find(x=>x.id===Number(choose.dataset.chooseSize));if(p)openProduct(p);}
 const qty=e.target.closest("[data-qty]");if(qty){const key=qty.dataset.qty,next=(cart.get(key)||0)+Number(qty.dataset.change),[id,sizeName]=key.split("|"),size=products.find(x=>x.id===Number(id))?.sizes.find(entry=>entry.name===sizeName);if(next<=0)cart.delete(key);else if(size&&next<=Math.min(size.stock,20))cart.set(key,next);else showToast("There is no more stock available for that size in this order.");saveCart();}
 const remove=e.target.closest("[data-remove]");if(remove){cart.delete(remove.dataset.remove);saveCart();}
 const preview=e.target.closest("[data-preview]");if(preview){const p=products.find(x=>x.id===Number(preview.dataset.preview));if(p)openProduct(p);}
 const photo=e.target.closest("[data-gallery-index]");if(photo){activePhotoIndex=Number(photo.dataset.galleryIndex);renderGallery();}
});
$("open-cart").addEventListener("click",openCart);$("close-cart").addEventListener("click",closeCart);$("drawer-backdrop").addEventListener("click",closeCart);
$("close-product").addEventListener("click",closeProduct);
$("product-modal").addEventListener("click",e=>{if(e.target===$("product-modal"))closeProduct();});
$("gallery-previous").addEventListener("click",()=>changePhoto(-1));
$("gallery-next").addEventListener("click",()=>changePhoto(1));
$("gallery-image").addEventListener("touchstart",e=>{touchStartX=e.changedTouches[0].clientX;},{passive:true});
$("gallery-image").addEventListener("touchend",e=>{
 if(touchStartX===null)return;
 const distance=e.changedTouches[0].clientX-touchStartX;
 if(Math.abs(distance)>45)changePhoto(distance<0?1:-1);
 touchStartX=null;
},{passive:true});
document.addEventListener("keydown",e=>{
 if(!$("product-modal").classList.contains("show"))return;
 if(e.key==="Escape")closeProduct();
 if(e.key==="ArrowLeft")changePhoto(-1);
 if(e.key==="ArrowRight")changePhoto(1);
});
$("checkout-button").addEventListener("click",()=>{if(!cart.size){showToast("Add a style to your basket first.");return;}closeCart();updateSummary();$("checkout-modal").classList.add("show");});
$("close-checkout").addEventListener("click",()=>$("checkout-modal").classList.remove("show"));
$("checkout-modal").addEventListener("click",e=>{if(e.target===$("checkout-modal"))$("checkout-modal").classList.remove("show");});
$("product-search").addEventListener("input",filterProducts);$("category-filter").addEventListener("change",filterProducts);
function filterProducts(){
 const q=$("product-search").value.toLowerCase(),cat=$("category-filter").value;let shown=0;
 document.querySelectorAll(".product-card").forEach(card=>{const yes=card.dataset.name.includes(q)&&(cat==="all"||card.dataset.category===cat);card.hidden=!yes;if(yes)shown++;});
 $("empty-state").hidden=shown>0;
}
$("order-form").addEventListener("submit",async e=>{
 e.preventDefault();if(!cart.size){$("form-message").textContent="Your basket is empty.";return;}
 const formData=new FormData(e.target);
 const payload=Object.fromEntries(formData.entries());payload.items=selectedItems().map(x=>({id:x.product.id,size:x.size,quantity:x.quantity}));
 $("form-message").textContent="Sending your order...";
 try{
  const res=await fetch("/api/order",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
  const result=await res.json();if(!res.ok)throw new Error(result.message||"Please try again.");
  $("form-message").textContent=`Thank you! Your order ${result.reference} has been received. The boutique will contact you to confirm details.`;
  cart.clear();saveCart();e.target.reset();updateSummary();
 }catch(err){$("form-message").textContent=err.message+" You can also send the order via WhatsApp below.";}
});
$("whatsapp-order").addEventListener("click",()=>{
 if(!cart.size){$("form-message").textContent="Your basket is empty.";return;}
 const number=window.WHATSAPP_NUMBER||"";
 if(!number){$("form-message").textContent="WhatsApp ordering is ready, but the shop's WhatsApp number has not been configured yet. Please add it in the .env file and restart the app.";return;}
 const data=new FormData($("order-form"));const url=`https://wa.me/${number}?text=${encodeURIComponent(orderText(data))}`;window.open(url,"_blank","noopener");
});
const contact=$("contact-whatsapp");
if(window.WHATSAPP_NUMBER){contact.href=`https://wa.me/${window.WHATSAPP_NUMBER}?text=${encodeURIComponent("Hello Little Angels Boutique! I would like to make an enquiry.")}`;}
else{contact.addEventListener("click",e=>{e.preventDefault();showToast("The shop WhatsApp number still needs to be added.");});}
$("year").textContent=new Date().getFullYear();renderCart();
