import json
from db import D, balance, move, number, rounded, rows, today

PERMISSIONS = {'purchase':'production','run':'production','overhead':'production','order':'sales','approve':'admin','reject':'admin','invoice':'admin','dispatch':'admin','payment':'admin','credit':'admin'}

def require(condition,message):
    if not condition:
        raise ValueError(message)

def one(db,table,key):
    # Table names come only from application constants.
    row=db.execute(f"select * from {table} where id=?",(key,)).fetchone()
    require(row is not None,"Document or master record was not found.")
    return row

def variance(actual,planned):
    return rounded(D(actual-planned)*10000/planned)/100 if planned else None

def recipe(db,product):
    return rows(db,"select b.*,i.name,i.scale,i.kind,i.unit from bom b join items i on i.id=b.item where product=? order by b.item",(product,))

def product_row(db,product):
    row=db.execute("select * from products where item=?",(product,)).fetchone()
    require(row is not None,"Unknown product.")
    return row

def available(db,product,exclude=0):
    held=db.execute("select coalesce(sum(qty),0) from lines join orders on orders.id=ord where product=? and status in ('Approved','Invoiced') and ord!=?",(product,exclude)).fetchone()[0]
    return balance(db,product)[0]-held

def invoice_total(inv):
    return sum(inv[k] for k in ('taxable','cgst','sgst','igst'))

def due(db,inv):
    paid=db.execute("select coalesce(sum(amount),0) from payments where invoice=?",(inv['id'],)).fetchone()[0]
    return invoice_total(inv)-paid

def label(inv):
    return f"MB/{inv['fy']}/{inv['seq']:04d}"

def execute(db,action,p,user,role):
    if PERMISSIONS.get(action)!=role:
        raise PermissionError
    db.execute("BEGIN IMMEDIATE")
    key=str(p['key'])
    require(8<=len(key)<=100,"Invalid request identifier.")
    if db.execute("select 1 from requests where user=? and key=?",(user,key)).fetchone():
        return "Already saved"
    db.execute("insert into requests values(?,?)",(user,key))
    result=apply(db,action,p,user)
    db.execute("insert into audit(actor,action,detail) values(?,?,?)",(user,action,json.dumps({'document':result,'input':{k:v for k,v in p.items() if k!='key'}})))
    return result

def apply(db,a,p,user):
    day=today()
    if a=='purchase':
        item=one(db,'items',p['item'])
        require(item['kind']!='finished',"Choose a raw or packaging material.")
        one(db,'suppliers',p['supplier'])
        scale=item['scale'] if p['unit']==item['unit'] else 1
        require(p['unit'] in ([item['unit'],{'kg':'g','L':'mL'}.get(item['unit'],item['unit'])]),"Unsupported unit.")
        qty=number(p['qty'],scale)
        value=rounded(D(qty)*number(p['rate'],100)/item['scale'])
        n=db.execute("insert into purchases(day,supplier,item,qty,value) values(?,?,?,?,?)",(day,p['supplier'],item['id'],qty,value)).lastrowid
        move(db,item['id'],qty,value,f'PUR-{n}')
        return f'PUR-{n}'
    if a=='run':
        prod=product_row(db,p['product'])
        batches=number(p['batches'])
        expected=batches*prod['yield']
        good=number(p['good'])
        damage=number(p['damaged'],zero=True)
        n=db.execute("insert into runs(day,product,batches,expected,good,damaged) values(?,?,?,?,?,?)",(day,prod['item'],batches,expected,good,damage)).lastrowid
        for b in recipe(db,prod['item']):
            qty=number(p['issues'][str(b['item'])],b['scale'],zero=True)
            if b['item']==4:
                require(qty==good+damage,"Pouches issued must equal good packets plus damaged pouches.")
            stock,value=balance(db,b['item'])
            require(qty<=stock,f"Insufficient {b['name']} stock.")
            cost=rounded(D(value)*qty/stock) if qty else 0
            db.execute("insert into issues values(?,?,?,?,?)",(n,b['item'],b['qty']*batches,qty,cost))
            move(db,b['item'],-qty,-cost,f'RUN-{n}')
        move(db,prod['item'],good,0,f'RUN-{n}')
        return f'RUN-{n}'
    if a=='overhead':
        one(db,'runs',p['id'])
        db.execute("update runs set labour=?,energy=? where id=?",(number(p['labour'],100,True),number(p['energy'],100,True),p['id']))
        return f"RUN-{p['id']}"
    if a=='order':
        one(db,'customers',p['customer'])
        require(bool(p['lines']),"Add a product first.")
        n=db.execute("insert into orders(day,customer,seller,status) values(?,?,?,'Submitted')",(day,p['customer'],user)).lastrowid
        seen=set()
        for line in p['lines']:
            prod=product_row(db,line['product'])
            require(prod['item'] not in seen,"Combine duplicate product lines.")
            seen.add(prod['item'])
            require(line['unit'] in ('packet','carton'),"Unsupported selling unit.")
            qty=number(line['qty'])*(prod['carton'] if line['unit']=='carton' else 1)
            db.execute("insert into lines values(?,?,?,?)",(n,prod['item'],qty,prod['price']))
        return f'SO-{n}'
    o=one(db,'orders',p['id'])
    lines=rows(db,"select * from lines where ord=?",(o['id'],))
    status=o['status']
    inv=db.execute("select * from invoices where ord=?",(o['id'],)).fetchone()
    if a in ('approve','reject'):
        require(status=='Submitted',"Only submitted orders can be reviewed.")
        if a=='approve':
            for l in lines:
                edit=p['lines'][str(l['product'])]
                qty=number(edit['qty'])
                capacity=available(db,l['product'])
                require(qty<=capacity,f"Short by {qty-capacity} packets. Order remains submitted.")
                db.execute("update lines set qty=?,price=? where ord=? and product=?",(qty,number(edit['price'],100),o['id'],l['product']))
        status='Approved' if a=='approve' else 'Rejected'
    elif a=='invoice':
        require(status=='Approved',"Approve the order first.")
        local=one(db,'customers',o['customer'])['state']=='Tamil Nadu'
        tax=cg=sg=ig=0
        for l in lines:
            base=l['qty']*l['price']
            rate=product_row(db,l['product'])['gst_bp']
            tax+=base
            if local:
                cg+=rounded(D(base)*rate/20000)
                sg+=rounded(D(base)*rate/20000)
            else:
                ig+=rounded(D(base)*rate/10000)
        year=int(day[:4])-(int(day[5:7])<4)
        fy=f'{year%100:02d}-{(year+1)%100:02d}'
        seq=db.execute("select coalesce(max(seq),0)+1 from invoices where fy=?",(fy,)).fetchone()[0]
        db.execute("insert into invoices(ord,day,fy,seq,taxable,cgst,sgst,igst) values(?,?,?,?,?,?,?,?)",(o['id'],day,fy,seq,tax,cg,sg,ig))
        status='Invoiced'
    elif a=='dispatch':
        require(status=='Invoiced',"Dispatch requires an active invoice.")
        for l in lines:
            require(available(db,l['product'],o['id'])>=l['qty'],"Insufficient dispatch stock.")
            move(db,l['product'],-l['qty'],0,label(inv))
        status='Dispatched'
    elif a=='payment':
        require(status in ('Invoiced','Dispatched'),"Invoice is not open.")
        amount=number(p['amount'],100)
        require(amount<=due(db,inv),"Payment exceeds outstanding.")
        n=db.execute("insert into payments(day,invoice,amount) values(?,?,?)",(day,inv['id'],amount)).lastrowid
        return f'RCPT-{n}'
    elif a=='credit':
        require(status=='Invoiced' and due(db,inv)==invoice_total(inv),"Only unpaid, undispatched invoices can be cancelled.")
        reason=str(p['reason']).strip()
        require(0<len(reason)<=300,"Enter a short cancellation reason.")
        db.execute("insert into credits(day,invoice,reason) values(?,?,?)",(day,inv['id'],reason))
        status='Credited'
    db.execute("update orders set status=? where id=?",(status,o['id']))
    return f"SO-{o['id']} · {status}"
