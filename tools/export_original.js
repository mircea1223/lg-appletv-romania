// SPDX-License-Identifier: AGPL-3.0-or-later
/* Template: export only root-owned static Apple TV files. No app/data or DB reads.
 * The generator substitutes the stage and pins transaction.json by SHA-256.
 * Run only through the separately reviewed one-shot launcher; no autoroot handoff. */
'use strict';
const fs=require('fs'),crypto=require('crypto'),cp=require('child_process');
const stage='__STAGE__',planSHA='__PLAN_SHA__';
const app='/media/cryptofs/apps/usr/palm/applications/com.apple.appletv';
const images='/media/cryptofs/apps/usr/palm/data/images/com.apple.appletv';
const inputs=[app+'/AppleTV',app+'/appinfo.json',app+'/res',app+'/lib',images];
const archive=stage+'/apple-tv-original.tar';
const payloadNames=['main.js','package.json','transaction.json'];
function fail(message){throw Error(message)}
function ls(path){return fs.lstatSync(path)}
function attrs(s){return{dev:s.dev,ino:s.ino,uid:s.uid,gid:s.gid,mode:s.mode,size:s.size,mtimeMs:s.mtimeMs,ctimeMs:s.ctimeMs}}
function safeDirectory(path,strict){const s=ls(path);if(!s.isDirectory()||s.isSymbolicLink()||s.uid!==0||![0,5000].includes(s.gid)||(s.mode&(strict?0o022:0o002))!==0||fs.realpathSync(path)!==path)fail('Unsafe directory: '+path);return s}
function safeFile(path){const s=ls(path);if(!s.isFile()||s.isSymbolicLink()||s.uid!==0||![0,5000].includes(s.gid)||(s.mode&0o022)!==0||s.nlink!==1||fs.realpathSync(path)!==path)fail('Unsafe static file: '+path);return s}
function parents(path){let current='';for(const name of path.split('/').filter(Boolean).slice(0,-1)){current+='/'+name;safeDirectory(current,false)}}
function digest(path,expected){const before=safeFile(path),fd=fs.openSync(path,fs.constants.O_RDONLY|fs.constants.O_NOFOLLOW);try{const opened=fs.fstatSync(fd);if(JSON.stringify(attrs(opened))!==JSON.stringify(attrs(before))||(expected&&JSON.stringify(attrs(opened))!==JSON.stringify(expected)))fail('Source changed before hashing: '+path);const h=crypto.createHash('sha256'),buffer=Buffer.alloc(65536);let length;while((length=fs.readSync(fd,buffer,0,buffer.length,null))>0)h.update(buffer.slice(0,length));if(JSON.stringify(attrs(fs.fstatSync(fd)))!==JSON.stringify(attrs(before)))fail('Source changed while hashing: '+path);return h.digest('hex')}finally{fs.closeSync(fd)}}
function mountRows(){return fs.readFileSync('/proc/self/mountinfo','utf8').split('\n').filter(Boolean).map(line=>{const f=line.split(' ');if(f.length<10||f.indexOf('-')<6)fail('Invalid mountinfo');return(f[4]||'').replace(/\\([0-7]{3})/g,(_,n)=>String.fromCharCode(parseInt(n,8)))})}
function noMounts(path){if(mountRows().some(p=>p===path||p.startsWith(path+'/')))fail('Unexpected mount inside export scope: '+path)}
function inventory(){
 const rows=[];let total=0,files=0;
 function walk(path){
  if(path===app+'/data'||path.startsWith(app+'/data/'))fail('Application data is outside export scope');
  if(rows.length>=10000)fail('Static export has too many entries');
  const s=ls(path);if(s.isSymbolicLink())fail('Static export contains symlink');
  if(s.isDirectory()){
   safeDirectory(path,false);rows.push({path,kind:'directory',attrs:attrs(s)});
   for(const name of fs.readdirSync(path).sort()){if(!name||name==='.'||name==='..'||name.includes('/'))fail('Invalid static filename');walk(path+'/'+name)}
  }else{
   safeFile(path);total+=s.size;files++;if(total>536870912)fail('Static export is unexpectedly large');rows.push({path,kind:'file',attrs:attrs(s),sha256:digest(path,attrs(s))});
  }
 }
 for(const path of inputs){parents(path);noMounts(path);walk(path)}
 const imageNames=fs.readdirSync(images).sort();if(JSON.stringify(imageNames)!==JSON.stringify(['data.img','data.img.md5']))fail('Unexpected registered image files');
 return{rows,total,files,sha256:crypto.createHash('sha256').update(JSON.stringify(rows)).digest('hex')};
}
function report(name,value){const fd=fs.openSync(stage+'/'+name,fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_WRONLY|fs.constants.O_NOFOLLOW,0o600);try{fs.writeFileSync(fd,JSON.stringify(value,null,2)+'\n');fs.fchownSync(fd,6303,5000);fs.fchmodSync(fd,0o600);fs.fsyncSync(fd)}finally{fs.closeSync(fd)}}
function syncStage(){const fd=fs.openSync(stage,'r');try{fs.fsyncSync(fd)}finally{fs.closeSync(fd)}}
function run(){let safeStage=false,code=1;try{
 if(process.getuid()!==0||__dirname!==stage||!/^\/media\/internal\/downloads\/[a-z0-9][a-z0-9-]{10,127}$/.test(stage)||!/^[a-f0-9]{64}$/.test(planSHA))fail('Unexpected root export context');
 safeDirectory('/media/internal/downloads',true);const stageInfo=attrs(safeDirectory(stage,true));noMounts(stage);process.umask(0o077);
 const names=fs.readdirSync(stage).sort();if(JSON.stringify(names)!==JSON.stringify(payloadNames.slice().sort()))fail('Unexpected export staging files');for(const name of names)safeFile(stage+'/'+name);safeStage=true;
 const planFile=stage+'/transaction.json',p=ls(planFile);if(p.size<2||p.size>65536||digest(planFile)!==planSHA)fail('Export transaction SHA mismatch');
 const plan=JSON.parse(fs.readFileSync(planFile,'utf8'));if(plan.kind!=='lg-appletv-ro-export-v1'||plan.appId!=='com.apple.appletv'||plan.stage!==stage||plan.persistentRoot!==false)fail('Unexpected export transaction');
 const snapshot=inventory(),appInfoFile=app+'/appinfo.json';if(ls(appInfoFile).size>65536)fail('Unexpected application manifest size');
 const appinfo=JSON.parse(fs.readFileSync(appInfoFile,'utf8'));if(appinfo.id!=='com.apple.appletv'||appinfo.main!=='AppleTV'||appinfo.type!=='native'||appinfo.trustLevel!=='trusted'||appinfo.privilegedJail!==true)fail('Unexpected original native identity');
 const df=cp.execFileSync('/bin/df',['-Pk',stage],{encoding:'utf8',timeout:5000,maxBuffer:65536}).trim().split('\n');const freeKiB=Number(df[df.length-1].trim().split(/\s+/)[3]);if(!Number.isFinite(freeKiB)||freeKiB<262144||freeKiB*1024<snapshot.total+33554432)fail('At least 256 MiB free storage and export headroom are required');
 // Archive only these fixed static roots; never archive the app directory itself.
 const fd=fs.openSync(archive,fs.constants.O_CREAT|fs.constants.O_EXCL|fs.constants.O_WRONLY|fs.constants.O_NOFOLLOW,0o600);const created=attrs(fs.fstatSync(fd));fs.closeSync(fd);
 cp.execFileSync('/bin/tar',['-C','/','-cf',archive].concat(inputs.map(path=>path.slice(1))),{timeout:180000,maxBuffer:65536});
 const archiveInfo=safeFile(archive);if(archiveInfo.dev!==created.dev||archiveInfo.ino!==created.ino||archiveInfo.size<snapshot.total)fail('Export archive identity or size changed');
 const after=inventory();if(after.sha256!==snapshot.sha256)fail('Static sources changed during export');
 const now=safeDirectory(stage,true);if(now.dev!==stageInfo.dev||now.ino!==stageInfo.ino)fail('Export stage identity changed');noMounts(stage);
 const portable=snapshot.rows.map(r=>({path:r.path.slice(1),kind:r.kind,sha256:r.sha256}));
 const archiveSHA=digest(archive),sourceSHA256={};for(const path of inputs){const selected=portable.filter(r=>r.path===path.slice(1)||r.path.startsWith(path.slice(1)+'/'));sourceSHA256[path.slice(1)]=selected.length===1&&selected[0].kind==='file'?selected[0].sha256:crypto.createHash('sha256').update(JSON.stringify(selected)).digest('hex')}
 fs.chownSync(archive,6303,5000);fs.chmodSync(archive,0o600);
 report('result.json',{status:'success',kind:'lg-appletv-ro-export-v1',appId:'com.apple.appletv',stage,archivePath:archive,archiveBytes:archiveInfo.size,archiveSHA256:archiveSHA,sourceSHA256,sourceInventorySHA256:crypto.createHash('sha256').update(JSON.stringify(portable)).digest('hex'),sourceFileCount:snapshot.files,sourceBytes:snapshot.total,sourcePaths:inputs.map(path=>path.slice(1)),preservedNativeFlags:{id:appinfo.id,version:appinfo.version,main:appinfo.main,type:appinfo.type,trustLevel:appinfo.trustLevel,privilegedJail:appinfo.privilegedJail,internalInstallationOnly:appinfo.internalInstallationOnly,fileSystemType:appinfo.fileSystemType},originalFilesModified:false,originalDataRead:false,databaseRecordsRead:false,persistentRootInstalled:false,installedPersistentRoot:false,installedHomebrew:false,stageRetainedUntilLocalVerification:true});
 fs.chmodSync(stage,0o711);syncStage();console.log('Static Apple TV export complete; archive and result retained for verified retrieval.');code=0;
 }catch(error){if(safeStage){try{safeDirectory(stage,true);report('error.json',{status:'failed',kind:'lg-appletv-ro-export-v1',error:error.message,originalFilesModified:false,originalDataRead:false,databaseRecordsRead:false,persistentRootInstalled:false,installedPersistentRoot:false,stageRetained:true});fs.chmodSync(stage,0o711);syncStage()}catch(reportError){console.error('Unable to export error receipt: '+reportError.message)}}console.error('Static Apple TV export failed: '+error.message)
 }finally{process.exit(code)}}
module.exports={run};
