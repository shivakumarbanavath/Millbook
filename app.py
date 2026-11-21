import csv
import hmac
import io
import json
import os
import secrets
import time
from datetime import date
from http.cookies import SimpleCookie
from pathlib import Path
from urllib.parse import parse_qs
from wsgiref.simple_server import make_server
from db import connect, initialize, password, rows, today
from documents import invoice_pdf, pdf
from operations import available, due, execute, label, one, recipe
from reports import NAMES, report

STATIC=Path(__file__).with_name('static')
def state(db,user,role):
    data={'user':user,'role':role,'today':today()}
    if role!='sales':
        data['stock']=rows(db,"select i.*,coalesce(sum(qty),0) qty from items i left join movements m on m.item=i.id group by i.id")
    if role in ('sales','admin','production'):
        data['products']=rows(db,"select p.*,i.name from products p join items i on i.id=p.item")
    if role in ('sales','admin'):
        data['customers']=rows(db,"select * from customers")
        data['orders']=rows(db,"select o.*,c.name,c.state from orders o join customers c on c.id=o.customer where (?!='sales' or seller=?) order by o.id desc",(role,user))
        for o in data['orders']:
            o['lines']=rows(db,"select l.*,i.name from lines l join items i on i.id=l.product where ord=?",(o['id'],))
            for l in o['lines']:
                if role=='admin':
                    l['available']=available(db,l['product'],o['id'])
            inv=db.execute("select * from invoices where ord=?",(o['id'],)).fetchone()
            if inv:
                o['invoice']={**dict(inv),'number':label(inv),'due':0 if o['status']=='Credited' else due(db,inv)}
        if role=='sales':
            data['sales']=report(db,'Customer sales','0001-01-01',today(),user)
    if role=='production':
        data['recipes']={p['item']:recipe(db,p['item']) for p in data['products']}
        data['suppliers']=rows(db,"select * from suppliers")
    if role in ('production','owner'):
        data['runs']=report(db,'Production runs','0001-01-01',today())
        data['variance']=report(db,'Material variance','0001-01-01',today())
    if role=='owner':
        data['ordersToday']=db.execute("select count(*) from orders where day=?",(today(),)).fetchone()[0]
        data['dues']=report(db,'Receivables ageing',today(),today())
    if role in ('auditor','admin','owner'):
        data['reports']=NAMES
    return data

def app(env,start):
    db=connect()
    code='200 OK'
    typ='application/json'
    headers=[]
    def cookie(v,age):
        secure='; Secure' if os.getenv('COOKIE_SECURE')=='1' else ''
        headers.append(('Set-Cookie',f'mb={v}; Path=/; HttpOnly; SameSite=Strict; Max-Age={age}{secure}'))
    try:
        path=env['PATH_INFO']
        method=env['REQUEST_METHOD']
        jar=SimpleCookie()
        jar.load(env.get('HTTP_COOKIE',''))
        token=jar['mb'].value if 'mb' in jar else ''
        session=db.execute("select s.*,u.role from sessions s join users u on u.name=s.user where token=? and expires>?",(token,int(time.time()))).fetchone()
        q={k:v[0] for k,v in parse_qs(env.get('QUERY_STRING','')).items()}
        if method=='POST':
            size=int(env.get('CONTENT_LENGTH') or 0)
            if size>65536 or env.get('CONTENT_TYPE','').split(';')[0]!='application/json':
                raise ValueError('Expected a small JSON request.')
            p=json.loads(env['wsgi.input'].read(size))
        if method=='GET' and path in ['/','/ui.js','/style.css']:
            file={'/':'index.html','/ui.js':'ui.js','/style.css':'style.css'}[path]
            body=(STATIC/file).read_bytes()
            typ={'/':'text/html','/ui.js':'application/javascript','/style.css':'text/css'}[path]
        elif method=='POST' and path=='/login':
            rec=db.execute("select * from users where name=?",(p['user'],)).fetchone()
            if not rec or not hmac.compare_digest(password(p['password'],rec['salt']),rec['hash']):
                code='401 Unauthorized'
                body={'error':'Check your username and password.'}
            else:
                token=secrets.token_urlsafe(32)
                db.execute("delete from sessions where expires<?",(int(time.time()),))
                db.execute("insert into sessions values(?,?,?,?)",(token,rec['name'],int(time.time())+28800,secrets.token_hex(24)))
                cookie(token,28800)
                body={'ok':True}
        elif not session:
            code='401 Unauthorized'
            body={'error':'Please sign in.'}
        elif method=='GET' and path=='/state':
            body=state(db,session['user'],session['role'])
            body['csrf']=session['csrf']
        elif method=='POST':
            if not hmac.compare_digest(env.get('HTTP_X_CSRF',''),session['csrf']):
                raise PermissionError
            if path=='/logout':
                db.execute("delete from sessions where token=?",(token,))
                cookie('',0)
                body={'ok':True}
            elif path=='/post':
                body={'message':execute(db,p['action'],p,session['user'],session['role'])}
            else:
                raise ValueError('Unknown operation.')
        elif path=='/invoice.pdf' and method=='GET':
            if session['role'] not in ('admin','auditor','owner'):
                raise PermissionError
            inv=one(db,'invoices',q['id'])
            body=invoice_pdf(db,inv)
            typ='application/pdf'
            headers.append(('Content-Disposition',f'attachment; filename="invoice-{inv["id"]}.pdf"'))
        elif path=='/report' and method=='GET':
            if session['role'] not in ('admin','auditor','owner'):
                raise PermissionError
            name=q['name']
            a,b=q['from'],q['to']
            if date.fromisoformat(a)>date.fromisoformat(b):
                raise ValueError('Start date must precede end date.')
            columns,records=report(db,name,a,b)
            body=[columns,records]
            fmt=q.get('format')
            if fmt in ('csv','pdf'):
                headers.append(('Content-Disposition',f'attachment; filename="{name}-{a}.{fmt}"'))
                if fmt=='pdf':
                    body=pdf(name,f'{a} through {b}',columns,records)
                    typ='application/pdf'
                else:
                    stream=io.StringIO()
                    writer=csv.writer(stream)
                    writer.writerows([columns,*records])
                    body=stream.getvalue().encode('utf-8-sig')
                    typ='text/csv'
        else:
            code='404 Not Found'
            body={'error':'Page not found.'}
        db.commit()
    except PermissionError:
        db.rollback()
        code='403 Forbidden'
        body={'error':'Your role cannot perform this action.'}
    except (ValueError,KeyError,TypeError) as e:
        db.rollback()
        code='400 Bad Request'
        body={'error':str(e)}
    finally:
        db.close()
    if not isinstance(body,bytes):
        body=json.dumps(body).encode()
    start(code,[('Content-Type',typ),('Content-Length',str(len(body))),('Cache-Control','no-store'),('X-Content-Type-Options','nosniff'),*headers])
    return [body]

if __name__=='__main__':
    initialize()
    port=int(os.getenv('PORT','8000'))
    print(f'Millbook listening on port {port}',flush=True)
    try:
        from waitress import serve
    except ImportError:
        make_server('127.0.0.1',port,app).serve_forever()
    else:
        serve(app,host='0.0.0.0',port=port)
