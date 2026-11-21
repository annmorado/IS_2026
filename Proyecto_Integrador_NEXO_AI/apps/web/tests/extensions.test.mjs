import test from 'node:test';import assert from 'node:assert/strict';
import {extensionPath,validExtensionBody} from '../lib/extensions.mjs';
const id='84a50756-c668-43b0-91a8-e40c67f52a9d';
test('RF-028 subscription paths restricted',()=>{assert.equal(extensionPath('GET',['subscriptions','me']),'subscriptions/me');assert.equal(extensionPath('POST',['subscriptions','start-trial']),'subscriptions/start-trial');assert.equal(extensionPath('PUT',['subscriptions','me']),null)});
test('RF-029 upload only known multipart route',()=>{assert.equal(extensionPath('POST',['documents','ocr','proposals']),'documents/ocr/proposals?document_type=invoice');assert.equal(extensionPath('POST',['documents','ocr','proposals'],'document_type=../../orders'),null);assert.equal(extensionPath('POST',['documents','ocr','proposals',id,'review']),`documents/ocr/proposals/${id}/review`)});
test('RF-030 messaging has no automatic general send route',()=>{assert.equal(extensionPath('POST',['messaging','send-template']),'messaging/send-template');assert.equal(extensionPath('POST',['messaging','send-anything']),null);assert.equal(validExtensionBody('messaging/send-template',{recipient_e164:'+52155',template_name:'ok',consent_reference:'valid123456',confirm:false}),false)});
test('RF-031 templates explicit confirmation',()=>{assert.equal(validExtensionBody('sector-templates/apply',{code:'bakery',confirm:true}),true);assert.equal(validExtensionBody('sector-templates/apply',{code:'bakery',confirm:false}),false);assert.equal(extensionPath('POST',['sector-templates','anything']),null)});
test('RF-032 agent allowlist only approved flows',()=>{assert.equal(validExtensionBody('agents/prepare',{agent_kind:'capacity_planner',objective:'Evaluar capacidad'}),true);assert.equal(validExtensionBody('agents/prepare',{agent_kind:'danger',objective:'x',tool:'execute'}),false);assert.equal(extensionPath('POST',['agents','workflows',id,'authorize']),`agents/workflows/${id}/authorize`);assert.equal(validExtensionBody(`agents/workflows/${id}/authorize`,{confirm:false}),false)});
test('deny unrecognized paths, queries and traversal',()=>{for(const parts of [['admin','users'],['..','secrets'],['orders','confirm']])assert.equal(extensionPath('GET',parts),null);assert.equal(extensionPath('GET',['subscriptions','me'],'organization_id=x'),null);assert.equal(extensionPath('POST',['agents','workflows',id,'delete']),null)});
test('RF-030 requires documented consent and explicit revocation',()=>{
 assert.equal(extensionPath('GET',['messaging','consents']),'messaging/consents');
 assert.equal(extensionPath('POST',['messaging','consents']),'messaging/consents');
 assert.equal(validExtensionBody('messaging/consents',{recipient_e164:'+5215512345678',evidence_reference:'folio-consent-123',confirm:true}),true);
 assert.equal(validExtensionBody('messaging/consents',{recipient_e164:'+5215512345678',evidence_reference:'folio-consent-123',confirm:false}),false);
 assert.equal(extensionPath('POST',['messaging','consents',id,'revoke']),`messaging/consents/${id}/revoke`);
 assert.equal(validExtensionBody(`messaging/consents/${id}/revoke`,{confirm:false}),false);
});
