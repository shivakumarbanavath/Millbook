from collections import defaultdict
from datetime import date
from db import D, rounded, rows
from operations import invoice_total, label, variance

NAMES=['Sales register','Customer sales','Product sales','Outward GST','Purchases','Stock summary','Stock ledger','Production runs','Material variance','Collections','Receivables ageing','Audit trail']
def money(paise):
    return f'{D(paise)/100:.2f}'
def units(qty,scale):
    return format(D(qty)/scale,'f')
def report(db,name,start,end,seller=None):
    args=(start,end)
    def read(sql,params=args):
        return rows(db,sql,params)
    if name in NAMES[:4]:
        # Credit notes are negative documents in their posting period.
        docs=read("""select i.*,i.day posting,1 sign,'Invoice' kind,c.name,c.gstin,c.state,o.seller from invoices i join orders o on o.id=i.ord join customers c on c.id=o.customer
        union all select i.*,cr.day posting,-1 sign,'Credit note',c.name,c.gstin,c.state,o.seller from credits cr join invoices i on i.id=cr.invoice join orders o on o.id=i.ord join customers c on c.id=o.customer order by posting,id""",())
        docs=[r for r in docs if start<=r['posting']<=end and (not seller or r['seller']==seller)]
        if name==NAMES[0]:
            return ['Date','Document','Invoice ref','Customer','Taxable Rs','CGST Rs','SGST Rs','IGST Rs','Gross Rs'],[[r['posting'],r['kind'],label(r),r['name'],*[money(r[k]*r['sign']) for k in ('taxable','cgst','sgst','igst')],money(invoice_total(r)*r['sign'])] for r in docs]
        agg=defaultdict(lambda:[0]*4)
        if name==NAMES[3]:
            for r in docs:
                k=(r['state'],r['gstin'],r['name'])
                for i,col in enumerate(('taxable','cgst','sgst','igst')):
                    agg[k][i]+=r[col]*r['sign']
            return ['Place of supply','GSTIN','Customer','Taxable Rs','CGST Rs','SGST Rs','IGST Rs'],[[*k,*map(money,v)] for k,v in agg.items()]
        for r in docs:
            for l in read("select qty,price,name from lines join items on items.id=product where ord=?",(r['ord'],)):
                k=r['name'] if name==NAMES[1] else l['name']
                agg[k][0]+=l['qty']*r['sign']
                agg[k][1]+=l['price']*l['qty']*r['sign']
        return [name.split()[0],'Packets','Taxable sales Rs'],[[k,v[0],money(v[1])] for k,v in agg.items()]
    if name=='Stock summary':
        data=read("""select i.*,coalesce(sum(case when day<? then qty else 0 end),0) opening,
        coalesce(sum(case when day between ? and ? and qty>0 then qty else 0 end),0) receipts,
        coalesce(sum(case when day between ? and ? and qty<0 then -qty else 0 end),0) issued
        from items i left join movements m on m.item=i.id group by i.id""",(start,*args,*args))
        return ['Item','Category','Unit','Opening','Receipts incl. opening entries','Issues','Closing'],[[r['name'],r['kind'],r['unit'],*[units(q,r['scale']) for q in (r['opening'],r['receipts'],r['issued'],r['opening']+r['receipts']-r['issued'])]] for r in data]
    if name=='Stock ledger':
        data=read("""select * from (select m.*,i.name,i.unit,i.scale,sum(qty) over(partition by item order by m.id) closing from movements m join items i on i.id=m.item) where day between ? and ? order by id""")
        return ['Date','Source','Item','Movement','Running balance','Unit'],[[r['day'],r['source'],r['name'],units(r['qty'],r['scale']),units(r['closing'],r['scale']),r['unit']] for r in data]
    if name=='Purchases':
        data=read("select p.*,s.name supplier_name,i.name,i.scale,i.unit from purchases p join suppliers s on s.id=p.supplier join items i on i.id=p.item where day between ? and ?")
        return ['Date','Receipt','Supplier','Material','Quantity','Unit','Value Rs'],[[r['day'],f"PUR-{r['id']}",r['supplier_name'],r['name'],units(r['qty'],r['scale']),r['unit'],money(r['value'])] for r in data]
    if name=='Production runs':
        data=read("select r.*,i.name,p.price,sum(s.cost) material from runs r join items i on i.id=r.product join products p on p.item=r.product join issues s on s.run=r.id where day between ? and ? group by r.id")
        out=[]
        for r in data:
            unitcost=rounded(D(r['material']+r['labour']+r['energy'])/r['good'])
            v=variance(r['good'],r['expected'])
            out.append([r['day'],f"RUN-{r['id']}",r['name'],r['expected'],r['good'],r['damaged'],v,'Review' if abs(v)>3 else 'OK',money(r['material']),money(r['labour']),money(r['energy']),money(unitcost),money(r['price']-unitcost)])
        return ['Date','Run','Product','Plan','Good','Pouch scrap','Yield %','Flag','Inputs Rs','Labour Rs','Energy Rs','Rs/packet','Margin Rs'],out
    if name=='Material variance':
        data=read("select s.*,i.name,i.unit,i.scale from issues s join runs r on r.id=s.run join items i on i.id=s.item where day between ? and ?")
        return ['Run','Material','Unit','Standard','Issued','Variance %','Flag','Issue cost Rs'],[[f"RUN-{r['run']}",r['name'],r['unit'],units(r['planned'],r['scale']),units(r['actual'],r['scale']),variance(r['actual'],r['planned']),'Review' if abs(variance(r['actual'],r['planned']))>3 else 'OK',money(r['cost'])] for r in data]
    if name=='Collections':
        data=read("select p.day,p.id receipt,p.amount,i.fy,i.seq,c.name from payments p join invoices i on i.id=p.invoice join orders o on o.id=i.ord join customers c on c.id=o.customer where p.day between ? and ?")
        return ['Date','Receipt','Invoice','Customer','Collected Rs'],[[r['day'],f"RCPT-{r['receipt']}",label(r),r['name'],money(r['amount'])] for r in data]
    if name=='Receivables ageing':
        data=read("""select i.*,c.name,coalesce((select sum(amount) from payments where invoice=i.id and day<=?),0) paid from invoices i join orders o on o.id=i.ord join customers c on c.id=o.customer where i.day<=? and not exists(select 1 from credits where invoice=i.id and day<=?)""",(end,end,end))
        out=[]
        for r in data:
            days=(date.fromisoformat(end)-date.fromisoformat(r['day'])).days
            if invoice_total(r)>r['paid']:
                out.append([r['name'],label(r),r['day'],days,'0–30' if days<=30 else '31–60' if days<=60 else '61–90' if days<=90 else '90+',money(invoice_total(r)-r['paid'])])
        return ['Customer','Invoice','Invoice date','Age days','Age band','Outstanding Rs'],out
    if name=='Audit trail':
        data=read("select * from audit where date(stamp,'+330 minutes') between ? and ? order by id desc")
        return ['Time UTC','Actor','Action','Document'],[[r['stamp'],r['actor'],r['action'],__import__('json').loads(r['detail'])['document']] for r in data]
    raise ValueError('Unknown report.')
