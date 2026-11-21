import test from 'node:test';import assert from 'node:assert/strict';
import {managementPath,validManagementBody} from '../lib/management.mjs';
const id='84a50756-c668-43b0-91a8-e40c67f52a9d';
test('management routes use explicit allowlist',()=>{
  assert.equal(managementPath('GET',['collaborators','users']),'collaborators/users');
  assert.equal(managementPath('POST',['purchasing','requests']),'purchasing/requests');
  assert.equal(managementPath('PATCH',['collaborators','users',id,'suspension']),`collaborators/users/${id}/suspension`);
  assert.equal(managementPath('DELETE',['scheduling','allocations',id]),`scheduling/allocations/${id}`);
});
test('cannot traverse into arbitrary endpoints',()=>{
  assert.equal(managementPath('GET',['auth','sessions']),null);
  assert.equal(managementPath('POST',['materials','stock']),null);
  assert.equal(managementPath('POST',['purchasing','requests',id,'approve']),null);
  assert.equal(managementPath('GET',['..','secrets']),null);
  assert.equal(managementPath('GET',['collaborators','users'],'organization_id='+id),null);
});
test('calendar requires single ISO date',()=>{
  assert.equal(managementPath('GET',['scheduling','calendar'],'day=2026-11-21'),'scheduling/calendar?day=2026-11-21');
  assert.equal(managementPath('GET',['scheduling','calendar'],'day=2026-11-21&day=2026-11-22'),null);
  assert.equal(managementPath('GET',['scheduling','calendar'],'day=tomorrow'),null);
});
test('reports export accepts only csv or pdf, filters',()=>{
  assert.equal(managementPath('GET',['reports','export'],'format=csv'),'reports/export?format=csv');
  assert.equal(managementPath('GET',['reports','export'],'format=pdf&status=completed'),'reports/export?format=pdf&status=completed');
  assert.equal(managementPath('GET',['reports','export'],'format=html'),null);
  assert.equal(managementPath('GET',['reports','export'],'format=pdf&organization_id='+id),null);
});
test('reject unrequested body fields',()=>{
  assert.equal(validManagementBody('purchasing/requests','POST',{supplier_id:id,material_id:id,quantity:'3',unit_cost_mxn:'10'}),true);
  assert.equal(validManagementBody('purchasing/requests','POST',{supplier_id:id,org_id:id}),false);
  assert.equal(validManagementBody('notifications/scan','POST',{}),true);
  assert.equal(validManagementBody('notifications/scan','POST',{notifyEveryone:true}),false);
  assert.equal(validManagementBody('notifications/preferences','PUT',{due_soon:true,risk:false,material_shortage:true}),true);
});
