"""Exercise the WSGI endpoints with real sessions and an isolated database."""
import json
import os
import tempfile
import unittest
from io import BytesIO
from urllib.parse import urlencode
from wsgiref.util import setup_testing_defaults
from app import app
from db import initialize,today
from reports import NAMES

class WebTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        from unittest.mock import patch
        env=patch.dict(os.environ,{'MILL_DB':self.temp.name+'/app.sqlite','DEMO_PASSWORD':'test-only'})
        env.start()
        self.addCleanup(env.stop)
        initialize()
        self.cookie=''
        self.csrf=''

    def request(self,path,payload=None,params=None):
        env={}
        setup_testing_defaults(env)
        env.update(PATH_INFO=path,HTTP_COOKIE=self.cookie,HTTP_X_CSRF=self.csrf,QUERY_STRING=urlencode(params or {}))
        if payload is not None:
            raw=json.dumps(payload).encode()
            env.update(REQUEST_METHOD='POST',CONTENT_TYPE='application/json',CONTENT_LENGTH=str(len(raw)))
            env['wsgi.input']=BytesIO(raw)
        status=[]
        def start(code,headers):
            status.append(int(code.split()[0]))
            cookie=dict(headers).get('Set-Cookie')
            if cookie:
                self.cookie=cookie.split(';')[0]
        data=b''.join(app(env,start))
        return status[0],data

    def login(self,user):
        self.assertEqual(self.request('/login',{'user':user,'password':'test-only'})[0],200)
        values=json.loads(self.request('/state')[1])
        self.csrf=values['csrf']
        return values

    def test_exports_and_access(self):
        self.assertEqual(self.request('/state')[0],401)
        self.login('audit')
        for name in NAMES:
            params={'from':today(),'to':today(),'name':name}
            for fmt,prefix in [('pdf',b'%PDF'),('csv',b'\xef\xbb\xbf')]:
                status,data=self.request('/report',params={**params,'format':fmt})
                self.assertEqual(status,200)
                self.assertTrue(data.startswith(prefix))
        self.assertEqual(self.request('/post',{'action':'purchase'})[0],403)
        self.assertEqual(self.request('/logout',{})[0],200)
        self.assertEqual(self.request('/state')[0],401)

    def test_sales_isolation_and_csrf(self):
        self.login('sales-a')
        order={'action':'order','key':'test-order-1','customer':1,'lines':[{'product':6,'qty':5,'unit':'packet'}]}
        self.assertEqual(self.request('/post',order)[0],200)
        self.assertEqual(len(json.loads(self.request('/state')[1])['orders']),1)
        state=self.login('sales-b')
        self.assertEqual(state['orders'],[])
        self.assertNotIn('stock',state)
        self.assertEqual(self.request('/report')[0],403)
        self.csrf='invalid'
        self.assertEqual(self.request('/post',order)[0],403)
