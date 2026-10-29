// @vitest-environment jsdom
import {afterEach,describe,expect,it,vi} from 'vitest';
import {cleanup,fireEvent,render,screen} from '@testing-library/react';
import RealFlightPanel from '../components/RealFlightPanel';
import FlightStatusLookup from '../components/FlightStatusLookup';
import {api} from '../api/client';

vi.mock('../api/client',()=>({api:{
 aviationStatus:vi.fn(),flightStatus:vi.fn(),liveAlternatives:vi.fn(),liveRecovery:vi.fn(),review:vi.fn(),
}}));
const freeStatus={provider:'AirLabs',configured:true,credentials_status:'configured_unverified' as const,account_plan:'unknown',monthly_request_limit:null,live_status_access:true,future_schedules_access:true,schedule_access_level:'Plan-gated',availability_note:'Schedules do not confirm seats.',real_time_update_note:'Provider status can lag.'};
afterEach(()=>{cleanup();vi.clearAllMocks()});

describe('AirLabs panel',()=>{
 it('shows provider-managed plan details and enables schedule actions',async()=>{
  vi.mocked(api.aviationStatus).mockResolvedValue(freeStatus);
  render(<RealFlightPanel caseId="INDEMO0001" origin="DEL" destination="BLR" caseDate="2026-10-30" onReport={vi.fn()}/>);
  expect(await screen.findByText('AirLabs')).toBeTruthy();
  expect(screen.getByText(/account plan controls schedule access/)).toBeTruthy();
  expect(screen.getByRole('button',{name:'Search AirLabs schedules'}).hasAttribute('disabled')).toBe(false);
  expect(screen.getByRole('button',{name:'Run recovery agents'}).hasAttribute('disabled')).toBe(false);
  expect(screen.queryByLabelText('Flight number')).toBeNull();
 });
 it('shows search schedules as a full list and recovery as a deterministic three-flight shortlist',async()=>{
  vi.mocked(api.aviationStatus).mockResolvedValue(freeStatus);
  vi.mocked(api.liveAlternatives).mockResolvedValue({source:'airlabs',schedule_basis:'published_route_pattern',availability_confirmed:false,message:'Route patterns found',records:[{
   provider:'airlabs',schedule_basis:'published_route_pattern',flight_date:'2026-10-30',flight_number:'6E101',airline:'IndiGo',status:null,origin:'DEL',destination:'BLR',scheduled_departure:'2026-10-30T09:00:00',scheduled_arrival:'2026-10-30T11:00:00',departure:'2026-10-30T09:00:00',arrival:'2026-10-30T11:00:00',eligible:true,reason:'Timing fits',availability_confirmed:false,departure_local_time:'09:00',arrival_local_time:'11:00',operating_days:['fri'],
  }]});
  vi.mocked(api.liveRecovery).mockResolvedValue({run_id:'run-12345678',case_id:'INDEMO0001',recommendation_id:'rec-1',workflow_status:'awaiting_human_review',affected_flight:'AI1001',origin:'DEL',destination:'BLR',itinerary_summary:'DEL to BLR',disruption_summary:'Cancellation',policy_decision:'proceed',reason_codes:[],connection_assessments:[],best_candidate_flight:'6E101',candidate_alternatives:[{flight:'6E101',airline:'IndiGo',origin:'DEL',destination:'BLR',departure:'2026-10-30T09:00:00',arrival:'2026-10-30T11:00:00',eligible:true,reason:'Fits schedule',source:'airlabs_route_pattern',schedule_basis:'published_route_pattern',departure_local_time:'09:00',arrival_local_time:'11:00',operating_days:['fri'],shortlist_rank:1,is_best_match:true}],recommended_action:'Operator to verify 6E101',explanation:'A short AirLabs schedule shortlist is ready for operator review.',evidence:[],human_review_required:true,human_review_status:'pending',agent_trace_summary:[{step:1,agent:'Data Agent',tool:'get_disruption_case',status:'completed',result_summary:'Loaded case evidence'},{step:2,agent:'Recovery Agent',tool:'search_airlabs_alternatives',status:'completed',result_summary:'Compared 20 schedules'},{step:3,agent:'Policy Engine',status:'completed',result_summary:'Selected the earliest eligible schedule'}],limitations:[]});
  const onReport=vi.fn();render(<RealFlightPanel caseId="INDEMO0001" origin="DEL" destination="BLR" caseDate="2026-10-30" onReport={onReport}/>);
  await screen.findByText('AirLabs');fireEvent.click(screen.getByRole('button',{name:'Search AirLabs schedules'}));
  expect(await screen.findByText('Matching AirLabs schedules')).toBeTruthy();expect(screen.getByText('IndiGo · 6E101')).toBeTruthy();
  fireEvent.click(screen.getByRole('button',{name:'Run recovery agents'}));
  expect(await screen.findByText('Recovery recommendation')).toBeTruthy();expect(screen.getByText('BEST SCHEDULE MATCH · OPERATOR MUST VERIFY')).toBeTruthy();
  expect(screen.getByText('Agent activity · 3 steps')).toBeTruthy();expect(onReport).toHaveBeenCalledOnce();
 });
 it('keeps flight status in a separate collapsed lookup below the queue',async()=>{
  vi.mocked(api.aviationStatus).mockResolvedValue(freeStatus);
  vi.mocked(api.flightStatus).mockResolvedValue({source:'airlabs',availability_confirmed:false,message:null,records:[{
   provider:'airlabs',provider_flight_id:'provider-123',flight_date:'2026-10-29',flight_number:'AI 101',airline:'Air India',status:'active',origin:'DEL',destination:'LHR',origin_name:null,destination_name:null,scheduled_departure:'2026-10-29T13:00:00+05:30',scheduled_arrival:'2026-10-29T18:00:00+01:00',estimated_departure:null,estimated_arrival:null,actual_departure:null,actual_arrival:null,departure_delay_minutes:null,arrival_delay_minutes:null,retrieved_at:'2026-10-29T10:00:00Z',availability_confirmed:false,
  }]});
  render(<FlightStatusLookup/>);
  expect(await screen.findByText('Check a real flight status')).toBeTruthy();
  fireEvent.change(await screen.findByLabelText('Flight number'),{target:{value:'AI 101'}});
  fireEvent.click(screen.getByRole('button',{name:/Check status/}));
  expect(await screen.findByText('Air India · AI 101')).toBeTruthy();
  expect(screen.getByText(/provider status can lag airline operations/)).toBeTruthy();
  expect(api.flightStatus).toHaveBeenCalledTimes(1);
 });
});
