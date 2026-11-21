import test from 'node:test';import assert from 'node:assert/strict';
import {aiPath,validAiBody} from '../lib/ai.mjs';
const id='c1f364d7-75b7-4d54-b343-455cda18d921';
test('RIA allowlist read paths and exact scopes',()=>{
 assert.equal(aiPath('GET',['voice-note-options']),'voice-note-options');
 assert.equal(aiPath('GET',['transcriptions',id]),'transcriptions/'+id);
 assert.equal(aiPath('GET',['extractions'],'limit=12'),'extractions?limit=12');
 assert.equal(aiPath('GET',['extractions'],'limit=51'),null);
 assert.equal(aiPath('GET',['extractions'],'organization_id=x'),null);
 assert.equal(aiPath('GET',['../secrets']),null);
 assert.equal(aiPath('POST',['orders','confirm']),null);
 assert.equal(aiPath('GET',['ai','transcriptions']),null);
});
test('RIA only intentional writes, never confirmation',()=>{
 assert.equal(aiPath('POST',['transcriptions',id,'cancel']),'transcriptions/'+id+'/cancel');
 assert.equal(aiPath('POST',['transcriptions',id,'retry']),'transcriptions/'+id+'/retry');
 assert.equal(aiPath('PATCH',['transcriptions',id,'text']),'transcriptions/'+id+'/text');
 assert.equal(aiPath('POST',['transcriptions',id,'text']),null);
 assert.equal(aiPath('POST',['extractions',id,'delete']),null);
 assert.equal(aiPath('DELETE',['transcriptions']),null);
});
test('RIA strict body validation',()=>{
 assert.equal(validAiBody('POST','extractions',{raw_text:'Pedido de 12 prendas'}),true);
 assert.equal(validAiBody('POST','extractions',{raw_text:'hello',owner_role:'admin'}),false);
 assert.equal(validAiBody('POST','transcriptions',{voice_note_id:id}),true);
 assert.equal(validAiBody('POST','transcriptions',{voice_note_id:'../../x'}),false);
 assert.equal(validAiBody('POST','validate',{product_id:id,quantity:'2',requested_date:'2026-12-01'}),true);
 assert.equal(validAiBody('PATCH','transcriptions/'+id+'/text',{text:'ok',confirm:false}),false);
 assert.equal(validAiBody('PATCH','transcriptions/'+id+'/text',{text:'ok',confirm:true}),true);
 assert.equal(validAiBody('POST','transcriptions/'+id+'/cancel',{}),true);
 assert.equal(validAiBody('POST','estimates',{product_id:id,quantity:'3.000'}),true);
});
