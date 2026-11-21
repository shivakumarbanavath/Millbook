from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from db import rows
from operations import invoice_total,label
from reports import money

def pdf(title,subtitle,headers,data,notes=(),wide=True):
    stream=BytesIO()
    doc=SimpleDocTemplate(stream,pagesize=landscape(A4) if wide else A4,leftMargin=28,rightMargin=28,topMargin=32,bottomMargin=32)
    styles=getSampleStyleSheet()
    def para(s,style='BodyText'):
        return Paragraph(escape(str(s)),styles[style])
    parts=[para('MILLBOOK   /   FACTORY OPERATIONS','Heading3'),para(title,'Title'),para(subtitle),Spacer(1,15)]
    style=styles['BodyText'].clone('cell')
    style.fontSize=8
    style.leading=10
    cells=[[Paragraph(escape(str(x)),style) for x in row] for row in [headers,*data]]
    t=Table(cells,colWidths=[doc.width/len(headers)]*len(headers),repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#cce7d8')),('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f2f5f1')]),('VALIGN',(0,0),(-1,-1),'TOP'),('TOPPADDING',(0,0),(-1,-1),6)]))
    parts.extend([t,Spacer(1,14),*[para(n) for n in notes]])
    doc.build(parts)
    return stream.getvalue()

def invoice_pdf(db,inv):
    buyer=db.execute("select c.* from customers c join orders o on o.customer=c.id where o.id=?",(inv['ord'],)).fetchone()
    lines=rows(db,"select l.*,i.name,p.hsn,p.gst_bp from lines l join items i on i.id=l.product join products p on p.item=l.product where ord=?",(inv['ord'],))
    return pdf('Tax invoice '+label(inv),f"Issue date {inv['day']} | Demo supplier: Millbook Snacks, 4 Mill Street, Tiruchirappalli, Tamil Nadu. GSTIN 33DEMOS0003C1Z0. Bill to: {buyer['name']}, {buyer['address']}. GSTIN {buyer['gstin']}. Place of supply: {buyer['state']}.",['Product','HSN','Packets','Rate Rs','Taxable Rs','GST %'],[[l['name'],l['hsn'],l['qty'],money(l['price']),money(l['qty']*l['price']),l['gst_bp']/100] for l in lines],[f"Taxable Rs {money(inv['taxable'])}   |   CGST Rs {money(inv['cgst'])}   |   SGST Rs {money(inv['sgst'])}   |   IGST Rs {money(inv['igst'])}",f"Invoice total Rs {money(invoice_total(inv))}",'Illustrative invoice for the internship benchmark. All parties are fictional.'],False)
