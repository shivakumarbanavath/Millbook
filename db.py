"""Ledger quantities are integers in g, mL, pieces or packets. Money is paise."""
import datetime as dt
import hashlib
import os
import secrets
import sqlite3
from pathlib import Path
from decimal import Decimal, ROUND_HALF_UP

D = Decimal
def rounded(x):
    return int(D(x).quantize(D(1), rounding=ROUND_HALF_UP))

def number(value, scale=1, zero=False):
    try:
        n = D(str(value)) * scale
        if not n.is_finite() or n != n.to_integral_value() or not (0 if zero else 1) <= n <= 1000000000:
            raise ValueError
        return int(n)
    except (ArithmeticError, ValueError):
        raise ValueError("Enter a valid quantity or amount with the supported precision.") from None

def today():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=5,minutes=30))).date().isoformat()

def connect():
    path = Path(os.getenv("MILL_DB","data/mill.sqlite"))
    path.parent.mkdir(parents=True,exist_ok=True)
    db = sqlite3.connect(path,timeout=15)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys=ON")
    return db

def password(raw,salt):
    return hashlib.pbkdf2_hmac("sha256", raw.encode(), bytes.fromhex(salt), 180000).hex()

def initialize():
    db = connect()
    with db:
        db.executescript(Path(__file__).with_name("schema.sql").read_text())
        db.execute("BEGIN IMMEDIATE")
        if not db.execute("select 1 from users").fetchone():
            for user,role in [('admin','admin'),('floor','production'),('sales-a','sales'),('sales-b','sales'),('audit','auditor'),('owner','owner')]:
                salt=secrets.token_hex(16)
                db.execute("insert into users values(?,?,?,?)",(user,role,salt,password(os.getenv("DEMO_PASSWORD","MillDemo2026!"),salt)))
            items=[('Flour','raw','kg',1000,100000,420000),('Cooking oil','raw','L',1000,30000,420000),('Salt and spice mix','raw','kg',1000,5000,100000),('200 g pouch','packaging','piece',1,500,125000),('Carton','packaging','piece',1,30,45000),('Murukku 200 g','finished','packet',1,50,0)]
            for i,(name,kind,unit,scale,qty,value) in enumerate(items,1):
                db.execute("insert into items values(?,?,?,?,?)",(i,name,kind,unit,scale))
                db.execute("insert into movements(day,item,qty,value,source) values(?,?,?,?,?)",(today(),i,qty,value,'OPEN-1'))
            db.execute("insert into products values(6,200,20,5000,'210690',500)")
            db.executemany("insert into bom values(6,?,?)",enumerate([40000,10000,1200,200,10],1))
            db.executemany("insert into customers values(?,?,?,?,?)",[(1,'Retailer A','Tamil Nadu','33DEMOA0001A1Z0','12 Market Road, Tiruchirappalli'),(2,'Distributor B','Karnataka','29DEMOB0002B1Z0','8 Bazaar Road, Bengaluru')])
            db.execute("insert into suppliers values(1,'Cauvery Mill (demo)')")
    db.close()

def rows(db,sql,args=()):
    return [dict(r) for r in db.execute(sql,args)]

def balance(db,item):
    return db.execute("select coalesce(sum(qty),0),coalesce(sum(value),0) from movements where item=?",(item,)).fetchone()

def move(db,item,qty,value,source):
    db.execute("insert into movements(day,item,qty,value,source) values(?,?,?,?,?)",(today(),item,qty,value,source))
