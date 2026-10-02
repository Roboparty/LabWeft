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

test('run provenance connects conditions without duplicating runs or inventing replication levels',()=>{
 const nodes=Object.fromEntries([node('study','module','project'),node('base','cell','study'),node('next','cell','study'),node('r1','run','base'),node('r2','run','next'),node('r3','run','next')].map(n=>[n.id,n]));
 const edges=[{id:'e1',source:'r2',target:'r1',relation:'derived_from'},{id:'e2',source:'r3',target:'r1',relation:'derived_from'},{id:'replicate',source:'r3',target:'r2',relation:'derived_from'}];
 const before=JSON.stringify({nodes,edges}),m=build(nodes,edges);
 assert.equal(m.nodes.length,2);assert.equal(m.links.length,1);assert.equal(m.nodes.find(n=>n.id==='next').level,1);
 assert.equal(m.links[0].projected,true);assert.equal(m.links[0].originalEdges.length,2);
 assert.equal(m.links[0].originalEdges[0].source,'r2');assert.equal(JSON.stringify({nodes,edges}),before);
});

test('focus retains origins and excludes unrelated history; all tracks remain available',()=>{
 const {nodes,edges}=fixture();nodes.focus=node('focus','module','project');nodes.current=node('current','cell','focus');edges.push({source:'current',target:'a2',relation:'derived_from'});
 const scoped=build(nodes,edges,new Set(),'focus');
 assert.deepEqual(Array.from(scoped.nodes,n=>n.id).sort(),['a1','a2','base','current']);
 assert.equal(scoped.total,6);assert.equal(build(nodes,edges).nodes.length,6);
 assert.equal(scoped.lanes.length,1);assert.equal(scoped.lanes[0].owner.id,'focus');
 assert.equal(build(nodes,edges,new Set(),'missing').nodes.length,6);
});

test('missing explicit ancestry is warned rather than replaced with hierarchy',()=>{
 const {nodes,edges}=fixture();nodes.a1.parent_id='base';edges.splice(0,1,{source:'a1',target:'missing',relation:'derived_from'});
 const m=build(nodes,edges);assert.equal(m.parent.has('a1'),false);assert.ok(m.warnings.some(w=>w.id==='a1'&&w.type==='missing_parent'));
});

test('different run origins remain multiple parents, not an invented clean chain',()=>{
 const {nodes,edges}=fixture();nodes.r1=node('r1','run','a1');nodes.r2=node('r2','run','b1');nodes.r3=node('r3','run','a3');nodes.r4=node('r4','run','a3');
 edges.push({source:'r3',target:'r1',relation:'derived_from'},{source:'r4',target:'r2',relation:'derived_from'});
 const m=build(nodes,edges);assert.ok(m.warnings.some(w=>w.id==='a3'&&w.type==='multiple_parents'));assert.ok(m.secondary.some(e=>e.target==='a3'));
});

test('focusing a run displays its owning condition and recorded origins',()=>{
 const {nodes,edges}=fixture();nodes.r1=node('r1','run','a2');
 const m=build(nodes,edges,new Set(),'r1');
 assert.deepEqual(Array.from(m.nodes,n=>n.id).sort(),['a1','a2','base']);
 assert.equal(m.lanes[0].owner.id,'a2');
});

test('focused condition preserves hierarchy ancestry when no relation was recorded',()=>{
 const {nodes}=fixture();nodes.a1.parent_id='base';nodes.a2.parent_id='a1';
 const m=build(nodes,[],new Set(),'a2');
 assert.deepEqual(Array.from(m.nodes,n=>n.id).sort(),['a1','a2','base']);
 assert.equal(m.links.length,2);
});

test('archived declarations and unsupported focus targets cannot hide the tree',()=>{
 const {nodes,edges}=fixture();nodes.study.status='archived';nodes.study.attrs.current_focus='a1';
 nodes.A.attrs.current_focus='a2';
 assert.equal(context.recordedTreeFocus(nodes),'a2');
 nodes.eval=node('eval','evaluation','a2');nodes.A.attrs.current_focus='eval';
 assert.equal(context.recordedTreeFocus(nodes),null);
 assert.equal(build(nodes,edges,new Set(),'eval').nodes.length,5);
 nodes.r1=node('r1','run','a1');nodes.a1.status='archived';
 assert.equal(context.resolveTreeFocus(nodes,'r1'),null);
});

test('reprojecting relations preserves original run provenance',()=>{
 const {nodes}=fixture();nodes.r1=node('r1','run','a1');nodes.r2=node('r2','run','a2');
 const edges=[{id:'origin',source:'r2',target:'r1',relation:'derived_from'}];
 const once=context.projectedCellRelations(nodes,edges),before=JSON.stringify(once);
 const twice=context.projectedCellRelations(nodes,once);
 assert.equal(JSON.stringify(twice),before);assert.equal(JSON.stringify(once),before);
});
