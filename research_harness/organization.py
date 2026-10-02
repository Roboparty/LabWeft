"""Read-only structural review hints; not a scientific-quality certificate."""
from __future__ import annotations


def organization(state: dict) -> dict:
    nodes = {key: n for key, n in state['nodes'].items() if n.get('status') != 'archived'}
    warnings = []
    children = {}
    for n in nodes.values():
        children.setdefault(n.get('parent_id'), []).append(n)

    def ancestor(node_id, kinds):
        seen = set()
        while node_id in nodes and node_id not in seen:
            seen.add(node_id)
            n = nodes[node_id]
            if n['kind'] in kinds:
                return node_id
            node_id = n.get('parent_id')
        return None

    studies = {}
    for n in nodes.values():
        if n['kind'] == 'cell':
            owner = ancestor(n.get('parent_id'), {'module', 'question'})
            studies.setdefault(owner, []).append(n['id'])
    related = set()
    run_lineage = 0
    for e in state.get('edges', {}).values():
        if e['relation'] not in {'derived_from', 'compares', 'inspired_by'}:
            continue
        source, target = nodes.get(e['source']), nodes.get(e['target'])
        if not source or not target or source['kind'] not in {'cell', 'run'} or target['kind'] not in {'cell', 'run'}:
            continue
        a, b = ancestor(source['id'], {'cell'}), ancestor(target['id'], {'cell'})
        if a and b and a != b:
            related.update((a, b))
            if e['relation'] == 'derived_from' and (source['kind'] == 'run' or target['kind'] == 'run'):
                run_lineage += 1
    for owner, cells in studies.items():
        if len(cells) < 5 or nodes.get(owner, {}).get('attrs', {}).get('role') == 'evidence_audit':
            continue
        attrs = nodes.get(owner, {}).get('attrs', {})
        if not attrs.get('study_summary'):
            warnings.append({'code': 'missing_study_synthesis', 'node_id': owner, 'cell_ids': cells,
                             'message': 'Several conditions have no study synthesis. Record the question, comparison, outcome and remaining gap on their study.'})
        if not any(c in related for c in cells) and not attrs.get('design'):
            warnings.append({'code': 'unexplained_condition_list', 'node_id': owner, 'cell_ids': cells,
                             'message': 'Conditions have neither recorded comparisons/lineage nor an explicit independent study design. Review evidence; never invent edges to make a tree.'})
    for parent, items in children.items():
        modules = [n for n in items if n['kind'] in {'module', 'question'} and n.get('attrs', {}).get('role') != 'evidence_audit']
        if len(modules) >= 8:
            warnings.append({'code': 'wide_research_outline', 'node_id': parent,
                             'related_ids': [n['id'] for n in modules],
                             'message': 'Many peer research sections. Review whether they form method families, comparisons, or historical diagnostics; retain independent topics when justified.'})
    focuses = []
    for n in nodes.values():
        focus = n.get('attrs', {}).get('current_focus')
        if focus is None:
            continue
        target = nodes.get(focus) if isinstance(focus, str) else None
        if (not target or target['kind'] not in {'module', 'question', 'cell', 'run'}
                or (target['kind'] == 'run' and ancestor(focus, {'cell'}) is None)):
            warnings.append({'code': 'invalid_current_focus', 'node_id': n['id'],
                             'message': 'Current focus must reference a visible module, question, cell, or run with a visible owning cell.'})
        else:
            focuses.append(focus)
    return {'needs_review': bool(warnings), 'warnings': warnings,
            'run_lineage_edges': run_lineage, 'current_focus_ids': sorted(set(focuses)),
            'scope': 'Structural review hints only. Independent experiments need not form a lineage; schema validity does not certify research organization or scientific conclusions.'}
