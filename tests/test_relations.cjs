const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../research_harness/static/app.js'),'utf8');
const code=source.split('// BEGIN grouped-relation-model')[1].split('// END grouped-relation-model')[0];
const scope={};vm.createContext(scope);vm.runInContext(code,scope);
const build=scope.groupedRelationModel;
const n=(id,kind,parent_id,order=0)=>({id,kind,parent_id,label:id,status:'recorded',attrs:{order}});
const graph=()=>Object.fromEntries([n('root','module','project'),n('A','module','root',1),n('B','module','root',2),n('baseline','cell','root'),n('a1','cell','A',1),n('a2','cell','a1',2),n('b1','cell','B'),n('run','run','a1')].map(x=>[x.id,x]));
test('keeps nested cells in their research track; runs do not clutter overview',()=>{
 const groups=build(graph(),[]).groups;
 assert.deepEqual(Array.from(groups,g=>[g.id,Array.from(g.cells,n=>n.id)]),[['root',['baseline']],['A',['a1','a2']],['B',['b1']]]);
 assert.equal(groups[1].parent.get('a2'),'a1');
});
test('stored derived_from is rendered origin to derivative, not backwards',()=>{
 const nodes=graph();nodes.a2.parent_id='A';
 const group=build(nodes,[{relation:'derived_from',source:'a2',target:'a1'}]).groups.find(g=>g.id==='A');
 assert.equal(group.parent.get('a2'),'a1');
 assert.deepEqual(Array.from(group.roots,n=>n.id),['a1']);
});
test('cross-track origins remain separate relationships rather than merging trees',()=>{
 const model=build(graph(),[{relation:'derived_from',source:'b1',target:'a2'}]);
 assert.equal(model.cross.length,1);
 assert.deepEqual(Array.from(model.groups.find(g=>g.id==='B').roots,n=>n.id),['b1']);
});
test('cycles and multiple sources stay visible with warnings, original data unmodified',()=>{
 const nodes=graph();const edges=[{relation:'derived_from',source:'a1',target:'a2'},{relation:'derived_from',source:'a2',target:'a1'},{relation:'derived_from',source:'a1',target:'baseline'}];
 const before=JSON.stringify({nodes,edges});
 const group=build(nodes,edges).groups.find(g=>g.id==='A');
 assert.ok(group.warnings.some(x=>x.type==='cycle'));
 assert.ok(group.warnings.some(x=>x.type==='multiple_parents'));
 assert.equal(group.roots.length,1);
 assert.equal(JSON.stringify({nodes,edges}),before);
});
test('archive and missing parents cannot create invisible inherited roots',()=>{
 const nodes=graph();nodes.a1.status='archived';nodes.extra=n('extra','cell','missing');
 const model=build(nodes,[{relation:'derived_from',source:'a2',target:'a1'}]);
 assert.ok(!model.groups.some(g=>g.cells.some(x=>x.id==='a1')));
 assert.ok(model.groups.find(g=>g.id==='__unassigned__').roots.some(x=>x.id==='extra'));
 assert.ok(model.groups.flatMap(g=>Array.from(g.roots)).some(x=>x.id==='a2'));
});
test('a child with explicit cross-track provenance does not gain a false local parent',()=>{
 const nodes=graph();
 const g=build(nodes,[{relation:'derived_from',source:'a2',target:'b1'}]).groups.find(g=>g.id==='A');
 assert.equal(g.parent.has('a2'),false);
});
