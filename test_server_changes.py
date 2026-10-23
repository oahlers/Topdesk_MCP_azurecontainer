"""Run with python3 test_server_changes.py next to server.py.
Tests use fake API responses, not the running MCP server or TOPdesk.
"""
import ast
import builtins
import html
import json
import os
from pathlib import Path
import re
import time
import unittest
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'server_v36.py'
if not SOURCE.exists():
    SOURCE = HERE / 'server.py'
TREE = ast.parse(SOURCE.read_text())
compile(SOURCE.read_text(), str(SOURCE), 'exec')


def load_functions():
    ns = dict(Any=Any, html=html, re=re, time=time, datetime=datetime,
              timezone=timezone, ZoneInfo=ZoneInfo, quote=quote, os=os)
    for original in TREE.body:
        if isinstance(original, (ast.FunctionDef, ast.ClassDef)):
            node = ast.parse(ast.unparse(original)).body[0]
            if isinstance(node, ast.FunctionDef):
                node.decorator_list = []
            exec(compile(ast.Module(body=[node], type_ignores=[]), 'isolated', 'exec'), ns)
    ns.update(INCIDENT_FIELDS='id,number,creationDate', INCIDENT_CACHE_PAGE_SIZE=2000,
              INCIDENT_CACHE_TTL_SECONDS=600, _INCIDENT_CACHE=[],
              _INCIDENT_CACHE_LOADED_AT=0.0, _INCIDENT_NUMBER_INDEX={},
              _REQUESTER_INDEX={}, _OPERATOR_INDEX={}, _CATEGORY_INDEX={},
              _SUBCATEGORY_INDEX={})
    return ns


class Changes(unittest.TestCase):
    def setUp(self):
        self.ns = load_functions()
        self.data = [
            {'id':'a', 'number':'S 2208 005', 'creationDate':'2022-08-01T00:00:00Z', 'request':'Peter', 'processingStatus':{'name':'closed'}},
            {'id':'b', 'number':'B', 'creationDate':'2023-12-31T23:00:00Z', 'request':'Peter', 'processingStatus':{'name':'closed'}},
            {'id':'c', 'number':'C', 'creationDate':'2024-12-31T22:59:59Z', 'request':'Peter', 'processingStatus':{'name':'closed'}},
            {'id':'d', 'number':'D', 'creationDate':'2024-12-31T23:00:00Z', 'request':'Peter', 'processingStatus':{'name':'closed'}},
            {'id':'e', 'number':'E', 'creationDate':'invalid', 'request':'Peter', 'processingStatus':{'name':'closed'}},
        ]
        self.ns['get_all_incidents_cached'] = lambda refresh=False: (self.data, True, 1)

    def test_year_local_boundaries(self):
        out=self.ns['filter_incidents_by_creation_date'](self.data, year=2024, sort_order='asc')
        self.assertEqual([x['id'] for x in out], ['b','c'])

    def test_explicit_dates(self):
        out=self.ns['filter_incidents_by_creation_date'](self.data,created_from='2024-01-01',created_to='2025-01-01')
        self.assertEqual([x['id'] for x in out], ['c','b'])

    def test_invalid_filters(self):
        for kwargs in ({'year':2024,'created_from':'2024-01-01'}, {'year':-1},
                       {'created_from':'2024-02-30'}, {'created_to':'2024-1-1'},
                       {'created_from':'2025-01-01','created_to':'2024-01-01'},
                       {'sort_order':'random'}):
            with self.assertRaises(ValueError):
                self.ns['filter_incidents_by_creation_date']([],**kwargs)

    def test_date_tool_pagination(self):
        out=self.ns['find_incidents_by_date_range'](year=2024,limit=1,sort_order='asc')
        self.assertEqual(out['totalMatches'],2)
        self.assertEqual(out['tableData'][0]['Sagsnummer'],'B')
        self.assertEqual(out['nextOffset'],1)
        out=self.ns['find_incidents_by_date_range'](year=2024,limit=1,offset=1,sort_order='asc')
        self.assertEqual(out['tableData'][0]['Sagsnummer'],'C')
        self.assertFalse(out['hasMore'])

    def test_no_cases_in_2020_and_2021(self):
        for year in (2020,2021):
            self.assertEqual(self.ns['find_incidents_by_date_range'](year=year)['count'],0)
        self.assertEqual(self.ns['find_incidents_by_date_range'](year=2022)['tableData'][0]['Sagsnummer'],'S 2208 005')

    def test_validation_before_api(self):
        self.ns['get_all_incidents_cached']=lambda **kwargs: self.fail('API must not be called')
        with self.assertRaises(ValueError):
            self.ns['find_incidents_by_date_range']()
        with self.assertRaises(ValueError):
            self.ns['find_incidents_by_name_in_content']('Peter',year=2024,created_to='2025-01-01')

    def test_name_date_before_limit_and_scan(self):
        out=self.ns['find_incidents_by_name_in_content']('Peter',year=2024,limit=1,scan=1,sort_order='asc')
        self.assertEqual(out['incidents'][0]['id'],'b')
        self.assertTrue(out['scanLimitReached'])
        out=self.ns['find_incidents_by_name_in_content']('Peter',year=2024,limit=1,offset=1,sort_order='asc')
        self.assertEqual(out['incidents'][0]['id'],'c')
        self.assertEqual(out['totalMatches'],2)

    def test_requester_formatter(self):
        def api(path, params):
            if path.endswith('/lookup'):
                return [{'id':'person','name':'Peter'}]
            return [self.data[0]]
        self.ns['incident_get']=api
        row=self.ns['find_incidents_by_requester']('Peter')['incidents'][0]
        self.assertEqual(row['Anmoder'],'Peter')
        self.assertEqual(row['Sagsnummer'],'S 2208 005')
        self.assertEqual(row['Status'],'Lukket')

    def test_short_page_and_repeat(self):
        ns=load_functions()
        pages=[[self.data[0]],[self.data[1]],[]]
        starts=[]
        def api(path,params):
            starts.append(params['pageStart'])
            return pages.pop(0)
        ns['incident_get']=api
        self.assertEqual(len(ns['get_all_incidents_cached'](refresh=True)[0]),2)
        self.assertEqual(starts,[0,1,2])
        saved=ns['_INCIDENT_CACHE']
        ns['incident_get']=lambda *args,**kwargs:[self.data[0]]
        with self.assertRaises(ns['TopdeskApiError']):
            ns['get_all_incidents_cached'](refresh=True)
        self.assertIs(ns['_INCIDENT_CACHE'],saved)

    def test_api_error_not_disguised(self):
        for status in (401,403,429,500):
            def api(*args,**kwargs):
                raise self.ns['TopdeskApiError']('error',status)
            self.ns['incident_get']=api
            with self.assertRaises(self.ns['TopdeskApiError']) as error:
                self.ns['get_incident_by_number']('2208 005')
            self.assertEqual(error.exception.status_code,status)

    def test_404_fallback(self):
        def api(path,params):
            if path=='/incidents':
                return [self.data[0]]
            raise self.ns['TopdeskApiError']('not found',404)
        self.ns['incident_get']=api
        self.assertEqual(self.ns['get_incident_by_number']('2208 005')['number'],'S 2208 005')

    def test_naive_and_invalid_dates(self):
        data=[{'creationDate':'2024-01-01T00:00:00'}, {'creationDate':'bad'}]
        self.assertEqual(len(self.ns['filter_incidents_by_creation_date'](data,year=2024)),1)
        self.assertEqual(len(self.ns['filter_incidents_by_creation_date'](data)),2)

    def test_swagger(self):
        schema=json.loads((HERE/'swagger.json').read_text())
        self.assertEqual(list(schema['paths']),['/mcp'])
        self.assertEqual(schema['paths']['/mcp']['post']['x-ms-agentic-protocol'],'mcp-streamable-1.0')
        self.assertEqual(schema['host'],'topdesk-mcp-tw0u.onrender.com')

if __name__=='__main__':
    unittest.main(verbosity=2)
