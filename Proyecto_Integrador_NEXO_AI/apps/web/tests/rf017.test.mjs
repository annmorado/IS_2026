import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {validateScenarioInput} from '../lib/scenario.mjs';
import {allowedApiPath} from '../lib/paths.mjs';
const view = readFileSync(new URL('../app/components/ScenarioPanel.jsx',import.meta.url),'utf8');
const proxy = readFileSync(new URL('../app/api/data/[...path]/route.js',import.meta.url),'utf8');
const uuid='84a50756-c668-43b0-91a8-e40c67f52a9d';
test('RF-017 web renders explanations, shortage and calculated alternative',()=>{
 assert.match(view,/Restricciones y alternativa calculada/);
 assert.match(view,/missing_product_units/);
 assert.match(view,/units_to_reschedule/);
 assert.match(view,/estimated_delivery_date_by_capacity/);
 assert.match(view,/result\.explanation\.caveat/);
});
test('RF-017 explanation requires no API mutations or new arbitrary parameters',()=>{
 assert.equal(allowedApiPath(['simulations','evaluate']),null);
 assert.equal(validateScenarioInput({order_id:uuid,product_id:uuid,commit:true}),null);
 assert.equal(validateScenarioInput({order_id:uuid,product_id:uuid,apply:true}),null);
 assert.match(proxy,/simulations\/evaluate/);
 assert.doesNotMatch(proxy,/simulations\/apply|simulations\/commit/);
});
test('RF-017 remains read-only via same scenario endpoint',()=>{
 assert.match(view,/Evaluar sin guardar/);
 assert.match(view,/sin aplicar cambios/);
 assert.match(view,/fetch\('\/api\/data\/simulations\/evaluate'/);
});
