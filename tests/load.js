import http from 'k6/http';
import { check, sleep } from 'k6';

const target = __ENV.BASE_URL || 'https://zendo.local';
const n = Number(__ENV.VUS || 10);
const ramp = Number(__ENV.RAMP || 0);
const mode = __ENV.MODE || 'web';
const body = mode === 'large' ? 'x'.repeat(5*1024*1024) : mode === 'report' ? '{}' : 'normal submission';
export const options = {
  insecureSkipTLSVerify: true,
  summaryTrendStats: ['avg','min','max','p(50)','p(95)','p(99)'],
  scenarios: __ENV.SOAK === '1' ? {
    load: {executor:'constant-arrival-rate',rate:1000,timeUnit:'1m',duration:'10m',preAllocatedVUs:100,maxVUs:1000},
  } : {
    load: {executor:'per-vu-iterations',vus:n,iterations:1,maxDuration:'5m'},
  },
  thresholds: {http_req_failed:['rate==0'],checks:['rate==1'],dropped_iterations:['count==0']},
};
export default function () {
  // Distribute exactly N requests over the requested ramp interval.
  if(ramp) sleep(((__VU-1)/n)*ramp);
  const url=mode==='web'?target+'/':target+(mode==='report'?'/api/reports/generate':'/api/submissions');
  const response=mode==='web'?http.get(url):http.post(url,body,{headers:{'Content-Type':mode==='report'?'application/json':'application/octet-stream'},timeout:'180s'});
  check(response,{'HTTP 200':r=>r.status===200,'Body vorhanden':r=>Boolean(r.body && r.body.length)});
}
export function handleSummary(data) { return { [(__ENV.OUTPUT || 'summary.json')]:JSON.stringify(data,null,2), stdout:JSON.stringify(data.metrics,null,2)+'\n' }; }
