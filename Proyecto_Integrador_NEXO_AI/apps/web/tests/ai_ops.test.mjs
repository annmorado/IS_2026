import {test} from 'node:test';
import {strict as assert} from 'node:assert';
import {aiOpsPath,validAiOpsBody} from '../lib/ai-ops.mjs';
const id='123e4567-e89b-42d3-a456-426614174000';
test('RIA-006 to 018: explicit read-only paths',()=>{
 for(const p of ['models','runs','quality',`runs/${id}`])assert.equal(aiOpsPath('GET',p.split('/')),p);
 for(const p of ['forecast','optimize','agent/prepare','agent/attempt-sensitive','quality/refresh','twin','models/train',`models/${id}/promote`,`models/${id}/rollback`])assert.equal(aiOpsPath('POST',p.split('/')),p);
});
test('RIA-014: deny generic confirmation, messaging or orders via proxy',()=>{
 for(const p of ['orders/confirm','messaging/send','purchases','prices','admin/delete','agent/execute','models/train/execute','/../orders'])
  assert.equal(aiOpsPath('POST',p.split('/')),null);
});
test('RIA-014: approval needs true confirm, strict schemas',()=>{
 assert.equal(validAiOpsBody('POST',`models/${id}/promote`,{confirm:false}),false);
 assert.equal(validAiOpsBody('POST',`models/${id}/promote`,{confirm:true,extra:1}),false);
 assert.equal(validAiOpsBody('POST',`models/${id}/promote`,{confirm:true}),true);
 assert.equal(validAiOpsBody('POST','quality/refresh',{}),true);
 assert.equal(validAiOpsBody('POST','quality/refresh',{bad:1}),false);
});
test('RIA-006: reject malformed dataset and arbitrary bodies',()=>{
 assert.equal(validAiOpsBody('POST','models/train',{confirm:true,data_origin:'synthetic',observations:[{}]}),false);
 assert.equal(validAiOpsBody('POST','agent/prepare',{product_id:id,quantity:'2',execute:true}),false);
});
test('RIA evidence GET only supports safe scoped query',()=>{
 assert.equal(aiOpsPath('GET',['runs'],'kind=forecast&limit=10'),'runs?kind=forecast&limit=10');
 assert.equal(aiOpsPath('GET',['runs'],'limit=51'),null);
 assert.equal(aiOpsPath('GET',['runs'],'kind=orders'),null);
 assert.equal(aiOpsPath('GET',['models'],'limit=10'),null);
 assert.equal(aiOpsPath('GET',['runs'],'kind=agent&kind=forecast'),null);
});
