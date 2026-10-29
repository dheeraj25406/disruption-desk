import type {CaseItem} from '../types';
export function filterCases(cases:CaseItem[],query:string):CaseItem[]{const q=query.trim().toLowerCase();return cases.filter(c=>`${c.case_id} ${c.passenger_label} ${c.airline} ${c.affected_flight} ${c.disruption_type}`.toLowerCase().includes(q));}
