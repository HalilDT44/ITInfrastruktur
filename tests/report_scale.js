import http from 'k6/http';
import { sleep, check } from 'k6';
import { Counter, Trend } from 'k6/metrics';
const success = new Counter('reports_completed');
const duration = new Trend('report_success_latency',true);
http.setResponseCallback(http.expectedStatuses(200,429));
export const options={vus:16,duration:'30s',insecureSkipTLSVerify:true,summaryTrendStats:['avg','p(50)','p(95)','p(99)'],thresholds:{checks:['rate==1'],reports_completed:['count>0']}};
export default function(){
 const r=http.post((__ENV.BASE_URL||'https://zendo.local:8443')+'/api/reports/generate','{}',{headers:{'Content-Type':'application/json'}});
 check(r,{'200 oder kontrolliertes 429':r=>r.status===200||r.status===429});
 if(r.status===200){success.add(1);duration.add(r.timings.duration);}else sleep(1);
}
export function handleSummary(data){return {[__ENV.OUTPUT||'/out/report.json']:JSON.stringify(data,null,2)};}
