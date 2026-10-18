import test from "node:test";
import assert from "node:assert/strict";
import {capture, connectivity} from "../chrome/core.mjs";

function fixture({incognito=true, allowed=true, store="private-store", fail=false}={}) {
  const sent = [], reads = [];
  const tab = {id: 42, incognito, url: "https://www.youtube.com/", status: "complete"};
  const api = {
    extension: {inIncognitoContext: incognito, isAllowedIncognitoAccess: async () => allowed},
    tabs: {query: async () => [tab], update: async (_, change) => Object.assign(tab, change), get: async () => tab},
    cookies: {getAllCookieStores: async () => [{id:"normal-store",tabIds:[1]}, {id:"private-store",tabIds:[42]}],
      getAll: async options => { reads.push(options); return [{name:"SID",value:"synthetic-only",domain:".youtube.com",path:"/",secure:true,httpOnly:true,hostOnly:false,session:true,sameSite:"lax",storeId:store}]; }},
    runtime: {sendNativeMessage: async (_, message) => { if(fail) throw new Error("offline"); sent.push(message); return message.type === "hello" ? {status:"pending",operation_id:"operation",nonce:"nonce"} : {status:message.type === "ping" ? "ready":"imported",cookie_count:1}; }},
  };
  return {api, sent, reads};
}
test("capture only selects the active Incognito tab's store", async () => {
  const {api, sent, reads} = fixture(); const result = await capture(api, true);
  assert.equal(result.status, "imported"); assert.deepEqual(reads, [{domain:"youtube.com",storeId:"private-store"}]);
  assert.equal(sent[1].cookies[0].httpOnly,true); assert.equal(sent[1].incognito,true);
});
for(const options of [{incognito:false}, {allowed:false}]) test(`reject ${JSON.stringify(options)}`, async () => {
  const {api, reads, sent} = fixture(options); await assert.rejects(capture(api,true)); assert.equal(reads.length,0); assert.equal(sent.length,0);
});
test("consent precedes cookie access", async () => { const {api,reads} = fixture(); await assert.rejects(capture(api,false)); assert.equal(reads.length,0); });
test("normal-store cookies can never be transferred", async () => { const {api,sent} = fixture({store:"normal-store"}); await assert.rejects(capture(api,true)); assert.equal(sent.length,1); });
test("unavailable native host can be retried without retaining a transfer", async () => {
  assert.equal(await connectivity(fixture({fail:true}).api),false); assert.equal(await connectivity(fixture().api),true);
});
test("connectivity reports Incognito readiness without reading cookies", async () => {
  const {api,sent,reads} = fixture();
  assert.equal(await connectivity(api),true);
  assert.deepEqual(sent,[{type:"ping",incognito:true,incognito_allowed:true}]);
  assert.equal(reads.length,0);
});
test("ambiguous stores stop before reading cookies or requesting transfer", async () => {
  const {api,reads,sent} = fixture();
  api.cookies.getAllCookieStores = async () => [{id:"normal",tabIds:[42]},{id:"private",tabIds:[42]}];
  await assert.rejects(capture(api,true)); assert.deepEqual(reads,[]); assert.deepEqual(sent,[]);
});
test("partitioned cookies are not flattened into a normal session", async () => {
  const {api,sent} = fixture(); const read = api.cookies.getAll;
  api.cookies.getAll = async options => (await read(options)).map(c => ({...c,partitionKey:{topLevelSite:"https://www.youtube.com"}}));
  await assert.rejects(capture(api,true)); assert.equal(sent.filter(m => m.type === "capture").length,0);
});
test("Google or lookalike tabs cannot be used as the capture source", async () => {
  for (const url of ["https://accounts.google.com/", "https://youtube.com.attacker.test/"]) {
    const {api,reads,sent} = fixture();
    api.tabs.query = async () => [{id:42,incognito:true,url,status:"complete"}];
    await assert.rejects(capture(api,true)); assert.equal(reads.length,0); assert.equal(sent.length,0);
  }
});
