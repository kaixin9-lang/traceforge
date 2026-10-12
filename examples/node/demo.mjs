import fs from 'node:fs';
const config=JSON.parse(fs.readFileSync('config.json','utf8'));
const expected='http://127.0.0.1:8000';
if(config.proxyTarget!==expected) { console.error('ECONNREFUSED: proxy target '+config.proxyTarget+'; backend expected '+expected); process.exit(1); }
console.log('Node proxy configuration verified: '+config.proxyTarget);
