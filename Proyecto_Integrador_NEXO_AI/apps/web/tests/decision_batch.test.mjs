import test from 'node:test';import assert from 'node:assert/strict';
import {validKey,validateRecommend,validateConfirm,writableDecisionPath} from '../lib/decisions.mjs';
import {allowedApiPath} from '../lib/paths.mjs';
const id='84a50756-c668-43b0-91a8-e40c67f52a9d';
test('RF-022 idempotency requires safe key',()=>{assert.equal(validKey('rec-12345678'),true);assert.equal(validKey('../escape'),false);assert.equal(validKey('abc'),false)});
test('RF-018 proposal validates hypothetical input only',()=>{
 assert.deepEqual(validateRecommend({scenario:{order_id:id,product_id:id,quantity:'5.000'}}),{scenario:{order_id:id,product_id:id,quantity:'5.000'}});
 assert.equal(validateRecommend({scenario:{order_id:id,product_id:id,organization_id:id}}),null);
 assert.equal(validateRecommend({scenario:{order_id:id,product_id:id,unit_price_mxn:'nan'}}),null);
});
test('RF-018 explicit confirmation cannot be spoofed',()=>{
 assert.equal(validateConfirm({confirmation:'CONFIRMAR',expected_review_revision:0,acknowledge_estimates:true}).confirmation,'CONFIRMAR');
 assert.equal(validateConfirm({confirmation:'SI',expected_review_revision:0,acknowledge_estimates:true}),null);
 assert.equal(validateConfirm({confirmation:'CONFIRMAR',expected_review_revision:0,acknowledge_estimates:true,status:'confirmed'}),null);
});
test('RF-022 write routes strictly whitelisted',()=>{
 assert.equal(writableDecisionPath(['decisions','recommend']),'decisions/recommend');
 assert.equal(writableDecisionPath(['decisions',id,'confirm']),`decisions/${id}/confirm`);
 assert.equal(writableDecisionPath(['orders',id,'confirm']),null);
 assert.equal(writableDecisionPath(['decisions','../../evil','confirm']),null);
});
test('RF-019/020/021 read routes are scoped',()=>{
 assert.equal(allowedApiPath(['operations','summary'],'days=7'),'operations/summary?days=7');
 assert.equal(allowedApiPath(['operations','summary'],'tenant=x'),null);
 assert.equal(allowedApiPath(['decisions'],`order_id=${id}`),`decisions?order_id=${id}`);
 assert.equal(allowedApiPath(['decisions'],'order_id=evil'),null);
 assert.equal(allowedApiPath(['audit','events'],`entity_id=${id}`),`audit/events?entity_id=${id}`);
 assert.equal(allowedApiPath(['audit','events'],'actor_id=x'),null);
});
