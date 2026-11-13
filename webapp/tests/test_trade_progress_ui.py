import json
import subprocess
from trade_progress_ui import TRADE_PROGRESS_SCRIPT


def test_progress_feedback_is_readonly_and_does_not_resubmit():
    harness=r'''
const vm=require('vm'),assert=require('assert');
const listeners={},windowListeners={},elements={};let begin=0,end=0,interval;
for(const id of ['trade-work-progress','trade-work-steps','trade-work-note','trade-work-elapsed'])elements[id]={hidden:true,textContent:'',replaceChildren(...x){this.children=x;}};
const context={URL,Set,performance:{now:()=>0},location:{href:'http://localhost/trade'},
 document:{getElementById:id=>elements[id],createElement:()=>({}),addEventListener:(name,fn)=>listeners[name]=fn},
 window:{addEventListener:(name,fn)=>windowListeners[name]=fn},queueMicrotask:fn=>fn(),
 setInterval:fn=>{interval=fn;return 1;},clearInterval:()=>{},beginGlobalWork:()=>begin++,endGlobalWork:()=>end++};
vm.runInNewContext(SCRIPT,context);
const form={action:'http://localhost/trade/review',setAttribute(){},removeAttribute(){}};
function send(path,prevented=false){const e={target:form,submitter:{formAction:'http://localhost'+path},defaultPrevented:prevented,preventDefault(){this.defaultPrevented=true;}};listeners.submit(e);return e;}
assert(!send('/trade/submit').defaultPrevented);assert.equal(begin,0);
send('/trade/review',true);assert.equal(begin,0);
send('/trade/review');assert.equal(begin,1);assert.equal(elements['trade-work-steps'].children.length,4);
assert.equal(elements['trade-work-progress'].hidden,false);
assert(send('/trade/review').defaultPrevented);
windowListeners.pageshow();assert.equal(end,1);assert.equal(elements['trade-work-progress'].hidden,true);
send('/trade/best/live');assert.equal(begin,2);
'''.replace('SCRIPT',json.dumps(TRADE_PROGRESS_SCRIPT))
    subprocess.run(['node','-'],input=harness.encode('utf-8'),check=True)
