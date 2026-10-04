import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const args=process.argv.slice(2);
if(args.length<2){console.error('Usage: node build_reader.mjs input.md output.html [--modules node_modules]');process.exit(2)}
const input=path.resolve(args[0]),output=path.resolve(args[1]);
if(input===output)throw Error('Input and output must differ');
const pos=args.indexOf('--modules');
const modules=pos>=0?args[pos+1]:process.env.CODEX_NODE_MODULES;
let marked;
try{({marked}=modules?await import(pathToFileURL(path.join(modules,'marked/lib/marked.esm.js'))):await import('marked'))}catch(e){throw Error('marked unavailable; provide --modules pointing to an existing node_modules directory',{cause:e})}
const escape=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const source=fs.readFileSync(input,'utf8').replace(/^\uFEFF/,'');
const title=(source.match(/^# (.+)$/m)||[])[1]||path.basename(input,'.md');
marked.use({renderer:{html(token){return escape(typeof token==='string'?token:token.text)}}});
let content=marked.parse(source);
const toc=[];
content=content.replace(/<h2>(.*?)<\/h2>/g,(_,label)=>{const id='section-'+(toc.length+1);toc.push({id,label});return `<h2 id="${id}">${label}</h2>`});
let count=0;
content=content.replace(/<img\b[^>]*>/g,tag=>{
 const match=tag.match(/\bsrc="([^"]*)"/);if(!match)throw Error('Image has no source');
 let src=match[1].replace(/&amp;/g,'&');try{src=decodeURIComponent(src)}catch{}
 if(/^[a-z][a-z0-9+.-]*:/i.test(src)||src.startsWith('//'))throw Error('Offline reader requires a local image: '+src);
 const file=path.resolve(path.dirname(input),src);
 const mime={'.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg','.gif':'image/gif','.webp':'image/webp','.svg':'image/svg+xml'}[path.extname(file).toLowerCase()];
 if(!mime)throw Error('Unsupported image format: '+src);
 const data=fs.readFileSync(file);count++;
 return tag.replace(match[0],`src="data:${mime};base64,${data.toString('base64')}" tabindex="0" role="button" class="guide-image" title="点击放大图片"`);
});
content=content.replace(/<a\b[^>]*href="([^"]*)"[^>]*>/g,(tag,href)=>{
 if(/^\s*(javascript|data|vbscript):/i.test(href))return '<a>';
 if(!/^[a-z][a-z0-9+.-]*:/i.test(href)&&!href.startsWith('#')){
  const file=path.resolve(path.dirname(input),href.split('#')[0]);
  const relative=path.relative(path.dirname(output),file).split(path.sep).map(encodeURIComponent).join('/');
  return tag.replace(`href="${href}"`,`href="${relative}${href.includes('#')?'#'+href.split('#').slice(1).join('#'):''}"`);
 }
 return tag;
});
content=content.replace(/<table>/g,'<div class="table-wrap"><table>').replace(/<\/table>/g,'</table></div>');
const css=`*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;color:#233e4b;background:#f2f5f7;font:16px/1.9 'Microsoft YaHei','Segoe UI',sans-serif}aside{position:fixed;width:260px;height:100vh;padding:30px 22px;overflow:auto;background:#183d4d;color:white}aside strong{font-size:21px}nav a{display:block;color:#dceaf0;padding:10px 0;border-bottom:1px solid #355969;font-size:13px;text-decoration:none}main{margin-left:290px;max-width:1120px;padding:40px 50px 100px;background:white}h1{font-size:34px;line-height:1.5}h2{font-size:25px;margin:45px 0 20px;border-top:2px solid #dce5ea;padding-top:20px;scroll-margin-top:15px}h3{font-size:20px;color:#196478;margin-top:30px}p{margin:18px 0}a{color:#087b94;overflow-wrap:anywhere}img.guide-image{display:block;max-width:100%;max-height:850px;width:auto;height:auto;margin:25px auto;cursor:zoom-in;border:1px solid #e3ebee;padding:10px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;text-align:left;border-bottom:1px solid #dce5ea;vertical-align:top}th{background:#ecf3f5}.table-wrap{overflow:auto}pre{padding:20px;background:#183d4d;color:#eff8fb;overflow:auto;border-radius:7px}code{font-family:Consolas,'Microsoft YaHei',monospace}blockquote{margin:20px 0;border-left:3px solid #378ba0;padding:5px 20px;background:#f0f6f8}dialog{width:96vw;max-width:1800px;max-height:95vh;padding:0;border:0;border-radius:8px}dialog::backdrop{background:#142f3be0}.bar{position:sticky;top:0;padding:12px;background:#183d4d;color:white;display:flex;gap:12px}.bar span{flex:1}.bar button{padding:7px 12px;cursor:pointer}.viewer{max-height:82vh;overflow:auto;text-align:center;padding:20px}.viewer img{max-width:100%}.viewer.original img{max-width:none}@media(max-width:960px){aside{position:relative;width:auto;height:auto}main{margin:0;padding:25px}nav{display:grid;grid-template-columns:1fr 1fr;gap:0 20px}h1{font-size:28px}}@media(max-width:520px){nav{display:block}main{padding:20px 15px}body{font-size:15px}}@media print{aside,dialog{display:none}main{margin:0;padding:0;max-width:none}h2,h3{break-after:avoid}img.guide-image{max-height:180mm}a{color:inherit}}`;
const html=`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escape(title)}</title><style>${css}</style></head><body><aside><strong>${escape(title)}</strong><nav>${toc.map(t=>`<a href="#${t.id}">${t.label}</a>`).join('')}</nav><p style="font-size:12px">点击图片可放大。正文与图片可离线阅读。</p></aside><main>${content}</main><dialog aria-label="图片放大"><div class="bar"><span></span><button id="size">适配 / 原始大小</button><button id="close">关闭</button></div><div class="viewer"><img alt=""></div></dialog><script>const d=document.querySelector('dialog'),v=d.querySelector('.viewer'),big=v.querySelector('img');function show(el){big.src=el.src;big.alt=el.alt;d.querySelector('span').textContent=el.alt;v.classList.remove('original');d.showModal()}document.querySelectorAll('.guide-image').forEach(el=>{el.onclick=()=>show(el);el.onkeydown=e=>{if(e.key==='Enter')show(el)}});document.getElementById('close').onclick=()=>d.close();document.getElementById('size').onclick=()=>v.classList.toggle('original');</script></body></html>`;
fs.writeFileSync(output,html,'utf8');
console.log(JSON.stringify({output,embeddedImages:count,sections:toc.length,bytes:Buffer.byteLength(html)}));

