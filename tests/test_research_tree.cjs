const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../research_harness/static/app.js'),'utf8');
const blocks=['grouped-relation-model','research-tree-model'].map(name=>source.split('// BEGIN '+name)[1].split('// END '+name)[0]).join('\n');
const context={};vm.createContext(context);vm.runInContext(blocks,context);
const build=context.researchTreeModel;
const node=(id,kind,parent_id,order=0)=>({id,kind,parent_id,label:id,attrs:{order},status:'recorded'});
function fixture(){
 const nodes=Object.fromEntries([node('study','module','project'),node('A','module','study'),node('B','module','study',1),node('base','cell','study'),node('a1','cell','A'),node('a2','cell','A'),node('a3','cell','A'),node('b1','cell','B')].map(n=>[n.id,n]));
 const edges=[['a1','base'],['a2','a1'],['a3','a1'],['b1','a2']].map(([source,target])=>({source,target,relation:'derived_from'}));
 return {nodes,edges};
}
test('one connected lineage retains cross-track parents and increasing depth',()=>{
 const {nodes,edges}=fixture(),model=build(nodes,edges),map=new Map(model.nodes.map(n=>[n.id,n]));
 assert.equal(model.nodes.length,5);assert.equal(model.links.length,4);
 for(const e of model.links)assert.ok(map.get(e.source).x<map.get(e.target).x);
 assert.equal(map.get('b1').level,3);assert.notEqual(map.get('b1').lane,map.get('a2').lane);
});
test('fork siblings never overlap; all node coordinates stay inside canvas',()=>{
 const {nodes,edges}=fixture(),m=build(nodes,edges),seen=new Set();
 for(const n of m.nodes){const key=[n.x,n.y].join(',');assert.ok(!seen.has(key));seen.add(key);assert.ok(Number.isFinite(n.x)&&Number.isFinite(n.y));assert.ok(n.x>0&&n.x<m.width&&n.y>0&&n.y<m.height);}
});
test('folding hides descendants while preserving identities and counts',()=>{
 const {nodes,edges}=fixture(),before=JSON.stringify({nodes,edges}),m=build(nodes,edges,new Set(['a1']));
 assert.equal(m.total,5);assert.equal(m.nodes.length,2);assert.equal(m.nodes.find(n=>n.id==='a1').hidden,3);
 assert.equal(JSON.stringify({nodes,edges}),before);
});
test('cycles remain warned secondary edges instead of recursive layout failure',()=>{
 const {nodes,edges}=fixture();edges.push({source:'base',target:'b1',relation:'derived_from'});
 const m=build(nodes,edges);assert.equal(m.nodes.length,5);assert.ok(m.warnings.some(w=>w.type==='cycle'));assert.ok(m.secondary.length>0);
});
test('inspiration is optional secondary context, not a fabricated primary generation',()=>{
 const {nodes,edges}=fixture();edges.push({source:'a1',target:'b1',relation:'inspired_by'});
 const m=build(nodes,edges);assert.equal(m.nodes.find(n=>n.id==='a1').level,1);assert.equal(m.secondary.length,1);
});
