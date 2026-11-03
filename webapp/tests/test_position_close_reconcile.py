from position_close_reconcile import plan_close, execute_close
import pytest

P=dict(exchange='NFO',tradingsymbol='COFORGE26NOV1980CE',product='NRML',quantity=475)
O=dict(P,transaction_type='SELL',order_type='LIMIT',price=109,variety='regular')

def test_match_and_partial_mismatch():
    existing=dict(O,order_id='old',status='OPEN',pending_quantity=475,filled_quantity=0)
    assert plan_close(O,[P],[existing])[0]=='SKIP'
    existing.update(quantity=500,pending_quantity=300,filled_quantity=200)
    action,target,_=plan_close(O,[P],[existing])
    assert action=='MODIFY' and target['quantity']==675
    with pytest.raises(ValueError): plan_close(O,[P],[existing,existing])
    with pytest.raises(ValueError): plan_close(O,[dict(P,quantity=-475)],[])

class Broker:
    def __init__(self): self.book=[]; self.calls=[]
    def orders(self): return self.book
    def positions(self): return {'net':[P]}
    def place_order(self,**kw): self.calls.append(kw); return 'new'
    def modify_order(self,**kw): self.calls.append(kw)

def test_delayed_visibility_restart_blocks_duplicate(tmp_path):
    b=Broker(); path=tmp_path/'intents.db'
    execute_close(b,O,path,'test','2026-10-30',lambda o:o)
    with pytest.raises(ValueError,match='reconciliation'):
        execute_close(b,O,path,'test','2026-10-30',lambda o:o)
    assert len(b.calls)==1

def test_modifies_existing_never_places_another(tmp_path):
    b=Broker();b.book=[dict(O,order_id='old',status='OPEN',pending_quantity=400,filled_quantity=75)]
    execute_close(b,O,tmp_path/'i.db','test','day',lambda o:dict(o,price=102.65))
    assert b.calls==[dict(variety='regular',order_id='old',quantity=550,price=102.65,order_type='LIMIT')]

def test_timeout_not_retried_and_accounts_isolated(tmp_path):
    class TimeoutBroker(Broker):
        def place_order(self,**kw):
            self.calls.append(kw)
            raise TimeoutError('unknown result')
    b=TimeoutBroker(); path=tmp_path/'i.db'
    with pytest.raises(TimeoutError): execute_close(b,O,path,'a','day',lambda o:o)
    with pytest.raises(ValueError): execute_close(b,O,path,'a','day',lambda o:o)
    other=Broker()
    execute_close(other,O,path,'b','day',lambda o:o)
    assert len(b.calls)==1 and len(other.calls)==1
