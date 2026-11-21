import test from 'node:test';
import assert from 'node:assert/strict';
import {allowedApiPath} from '../lib/paths.mjs';
const A='84a50756-c668-43b0-91a8-e40c67f52a9d';
test('permitted order search with query filters',()=>{
 assert.equal(allowedApiPath(['orders','search'],'q=playeras&status=confirmed&limit=10'),'orders/search?q=playeras&status=confirmed&limit=10');
});
test('list quotes for a single order',()=>{
 assert.equal(allowedApiPath(['quotes'],'order_id='+A),'quotes?order_id='+A);
 assert.equal(allowedApiPath(['quotes'],''),null);
});
test('read order, history, quote, document and pdf',()=>{
 for(const p of ['orders/'+A,'orders/'+A+'/history','quotes/'+A,'quotes/'+A+'/document','quotes/'+A+'/pdf'])
   assert.equal(allowedApiPath(p.split('/')),p);
});
test('reject mutation routes and arbitrary proxy traversal',()=>{
 for(const p of ['auth/login','organizations','users','orders/'+A+'/status','quotes/'+A+'/approve','quotes/'+A+'/document/delete','../auth/login','orders/%2E%2E','health'])
   assert.equal(allowedApiPath(p.split('/')),null,p);
});
test('reject arbitrary and repeated parameters',()=>{
 assert.equal(allowedApiPath(['orders','search'],'organization_id='+A),null);
 assert.equal(allowedApiPath(['orders','search'],'q=a&q=b'),null);
 assert.equal(allowedApiPath(['quotes'],'order_id='+A+'&foo=x'),null);
 assert.equal(allowedApiPath(['orders',A],'q=none'),null);
});
test('reject malformed and untrusted UUID',()=>{
 assert.equal(allowedApiPath(['orders','not-a-uuid']),null);
 assert.equal(allowedApiPath(['quotes','ab123','pdf']),null);
});
