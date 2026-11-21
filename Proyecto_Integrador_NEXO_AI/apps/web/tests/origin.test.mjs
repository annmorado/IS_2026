import test from 'node:test';
import assert from 'node:assert/strict';
import {allowedOrigin} from '../lib/origin.mjs';

function request({origin,host,url='http://127.0.0.1:3000/api/auth/session'}={}) {
  const headers = new Headers();
  if (origin !== undefined) headers.set('origin',origin);
  if (host !== undefined) headers.set('host',host);
  return new Request(url,{headers});
}

test('accept same-origin 127.0.0.1:3000',()=>{
  assert.equal(allowedOrigin(request({origin:'http://127.0.0.1:3000',host:'127.0.0.1:3000'})),true);
});
test('accept same-origin localhost:3000',()=>{
  assert.equal(allowedOrigin(request({origin:'http://localhost:3000',host:'localhost:3000',url:'http://localhost:3000/api/auth/session'})),true);
});
test('accept browser 127.0.0.1 when Next.js normalizes request.url to localhost',()=>{
  assert.equal(allowedOrigin(request({origin:'http://127.0.0.1:3000',host:'127.0.0.1:3000',url:'http://localhost:3000/api/auth/session'})),true);
});
test('accept browser localhost when Next.js normalizes request.url to 127.0.0.1',()=>{
  assert.equal(allowedOrigin(request({origin:'http://localhost:3000',host:'localhost:3000',url:'http://127.0.0.1:3000/api/auth/session'})),true);
});
test('reject requests with missing Origin or Host',()=>{
  assert.equal(allowedOrigin(request({host:'127.0.0.1:3000'})),false);
  assert.equal(allowedOrigin(request({origin:'http://127.0.0.1:3000'})),false);
});
test('reject malicious or mismatched origins',()=>{
  for (const origin of ['http://attacker.test:3000','http://127.0.0.1:4000','null','http://127.0.0.1:3000/path','https://127.0.0.1:3000']) {
    assert.equal(allowedOrigin(request({origin,host:'127.0.0.1:3000'})),false,origin);
  }
});
test('reject Host mismatch even for both local addresses',()=>{
  assert.equal(allowedOrigin(request({origin:'http://localhost:3000',host:'127.0.0.1:3000',url:'http://localhost:3000/api/auth/session'})),false);
});
test('reject loopback normalization from a non-loopback external host',()=>{
  assert.equal(allowedOrigin(request({origin:'http://my-domain.test:3000',host:'my-domain.test:3000',url:'http://localhost:3000/api/auth/session'})),false);
});
test('accept matching HTTPS origin for web hosting with the same request.url origin',()=>{
  assert.equal(allowedOrigin(request({origin:'https://nexo.example:443',host:'nexo.example',url:'https://nexo.example/api/auth/session'})),false);
  assert.equal(allowedOrigin(request({origin:'https://nexo.example',host:'nexo.example',url:'https://nexo.example/api/auth/session'})),true);
});
