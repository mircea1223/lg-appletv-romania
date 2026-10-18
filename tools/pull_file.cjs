'use strict';
// Read one explicitly requested file through the configured LG Developer Mode device.
// SPDX-License-Identifier: AGPL-3.0-or-later
const fs=require('fs'),path=require('path'),cp=require('child_process');
const args=process.argv.slice(2);
if(args.length!==3){console.error('Usage: node pull_file.cjs DEVICE REMOTE_ABSOLUTE_PATH NEW_LOCAL_PATH');process.exit(2)}
const [device,remote,localArg]=args,local=path.resolve(localArg);
if(!/^[a-zA-Z0-9_.-]+$/.test(device)||!remote.startsWith('/')||remote.includes('\0')||fs.existsSync(local)){console.error('Refused invalid device/path or existing local output');process.exit(2)}
let novacom;
try{
 const globalRoot=cp.execFileSync(process.platform==='win32'?'npm.cmd':'npm',['root','-g'],{encoding:'utf8'}).trim();
 const pkg=path.join(globalRoot,'@webos-tools','cli');
 if(JSON.parse(fs.readFileSync(path.join(pkg,'package.json'),'utf8')).version!=='3.2.6')throw Error('Install the tested CLI version 3.2.6 first');
 novacom=require(path.join(pkg,'lib','base','novacom'));
}catch(e){console.error('CLI loading failed: '+e.message);process.exit(1)}
const temporaryDirectory=fs.mkdtempSync(path.join(path.dirname(local),'.lg-appletv-download-'));
const temporary=path.join(temporaryDirectory,'download');
function cleanup(){try{if(fs.existsSync(temporary))fs.unlinkSync(temporary);fs.rmdirSync(temporaryDirectory)}catch(_){}}
process.on('exit',cleanup);
let session,completed=false;
const timeout=setTimeout(()=>finish(Error('Transfer timed out')),180000);
function finish(error){if(completed)return;completed=true;clearTimeout(timeout);if(session)session.end();if(error){console.error('Transfer failed: '+error.message);process.exitCode=1}else{try{fs.chmodSync(temporary,0o600);fs.linkSync(temporary,local);cleanup();console.log('Saved '+local)}catch(e){console.error('Local save failed: '+e.message);process.exitCode=1}}}
new novacom.Session(device,false,(error,value)=>{if(error)return finish(error);session=value;session.get(remote,temporary,finish)});
