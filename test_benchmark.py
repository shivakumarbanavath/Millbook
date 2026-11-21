import os
import tempfile
import unittest
from uuid import uuid4
from db import balance, connect, initialize, today
from documents import invoice_pdf
from operations import execute, available
from reports import report,NAMES

class FactoryTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        prev=os.environ.get('MILL_DB')
        os.environ['MILL_DB']=self.temp.name+'/test.sqlite'
        self.addCleanup(lambda: os.environ.pop('MILL_DB',None) if prev is None else os.environ.update(MILL_DB=prev))
        self.addCleanup(self.temp.cleanup)
        initialize()
        self.db=connect()
        self.addCleanup(self.db.close)

    def post(self,act,role,**p):
        user={'sales':'sales-a','production':'floor','admin':'admin'}[role]
        with self.db:
            return execute(self.db,act,{'key':str(uuid4()),**p},user,role)

    def order(self,qty,customer=1,unit='packet'):
        self.post('order','sales',customer=customer,lines=[dict(product=6,qty=qty,unit=unit)])
        return self.db.execute('select max(id) from orders').fetchone()[0]

    def approve(self,id,qty):
        self.post('approve','admin',id=id,lines={'6':dict(qty=qty,price=50)})

    def test_benchmark(self):
        self.post('purchase','production',supplier=1,item=1,unit='g',qty=60000,rate=45)
        self.post('run','production',product=6,batches=1,good=188,damaged=6,issues=dict(zip('12345',[40,10.5,1.2,194,9])))
        self.assertEqual([balance(self.db,i)[0] for i in range(1,7)],[120000,19500,3800,306,21,238])
        a=self.order(150)
        self.approve(a,150)
        self.post('invoice','admin',id=a)
        i=self.db.execute('select * from invoices').fetchone()
        self.assertEqual((i['taxable'],i['cgst'],i['sgst'],i['igst']),(750000,18750,18750,0))
        self.assertTrue(invoice_pdf(self.db,i).startswith(b'%PDF'))
        self.post('dispatch','admin',id=a)
        b=self.order(120,2)
        with self.assertRaisesRegex(ValueError,'Short by 32'):
            self.approve(b,120)
        self.assertEqual(balance(self.db,6)[0],88)
        self.post('payment','admin',id=a,amount=4000)
        self.post('overhead','production',id=1,labour=1200,energy=600)
        def data(name):
            return report(self.db,name,today(),today())[1]
        self.assertEqual(data('Receivables ageing')[0][-1],'3875.00')
        self.assertEqual(data('Production runs')[0][6:],[-6.0,'Review','4055.00','1200.00','600.00','31.14','18.86'])
        self.assertEqual(data('Material variance')[1][5:7],[5.0,'Review'])
        for name in NAMES:
            self.assertTrue(report(self.db,name,today(),today())[0])

    def test_credit_reservation_units_and_retry(self):
        a=self.order(2,2,'carton')
        self.approve(a,40)
        self.assertEqual(available(self.db,6),10)
        self.post('invoice','admin',id=a)
        self.assertEqual(self.db.execute('select igst from invoices').fetchone()[0],10000)
        self.post('credit','admin',id=a,reason='Duplicate order')
        self.assertEqual(available(self.db,6),50)
        self.assertEqual(report(self.db,'Customer sales',today(),today())[1][0][-1],'0.00')
        key=str(uuid4())
        for _ in range(2):
            self.post('purchase','production',key=key,supplier=1,item=2,unit='mL',qty=500,rate=140)
        self.assertEqual(balance(self.db,2)[0],30500)

    def test_failed_run_rolls_back(self):
        with self.assertRaisesRegex(ValueError,'Insufficient'):
            self.post('run','production',product=6,batches=1,good=188,damaged=6,issues=dict(zip('12345',[40,35,1.2,194,9])))
        self.assertEqual(balance(self.db,1)[0],100000)
        self.assertEqual(self.db.execute('select count(*) from runs').fetchone()[0],0)
        with self.assertRaises(PermissionError):
            self.post('purchase','sales',item=1)

if __name__=='__main__':
    unittest.main()
