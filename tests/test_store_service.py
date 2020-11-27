from database import Session
from order_service import Order
from datetime import date
import re

import requests_mock
import pytest

from store_service import app, User


@pytest.fixture()
def add_some_user():
    with Session() as s:
        s.add(User(id=1, name='Alex', user_uid='1'))


def test_request_all_orders(fresh_database, add_some_user):
    with app.test_client() as test_client:
        with requests_mock.Mocker(real_http=True) as m:
            m.get(
                re.compile("/orders/1"),
                json=[{
                    'itemUid': 'item-1',
                    'orderDate': '2020-11-22T00:00:00',
                    'orderUid': '1-1-1',
                    'status': 'PAID'
                }]
            )
            m.get(
                re.compile("/warehouse"),
                json={'model': 'item one', 'size': 'L'}
            )
            m.get(
                re.compile("/warranty"),
                json={
                    "itemUid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "warrantyDate": "2020-11-22T00:00:00",
                    "status": "FIXING"
                }
            )
            response = test_client.get("/store/1/orders")
            assert response.status == "200 OK"
            assert "orderUid" in response.json[0]
            assert "model" in response.json[0]
            assert "size" in response.json[0]
            assert "date" in response.json[0]
            assert "warrantyDate" in response.json[0]
            assert "warrantyStatus" in response.json[0]


def test_request_order(fresh_database, add_some_user):
    with app.test_client() as test_client:
        with requests_mock.Mocker(real_http=True) as m:
            m.get(
                re.compile("/orders/1/1-1-1"),
                json={
                    'itemUid': 'item-1',
                    'orderDate': '2020-11-22T00:00:00',
                    'orderUid': '1-1-1',
                    'status': 'PAID'
                }
            )
            m.get(
                re.compile("/warehouse"),
                json={'model': 'item one', 'size': 'L'}
            )
            m.get(
                re.compile("/warranty"),
                json={
                    "itemUid": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                    "warrantyDate": "2020-11-22T00:00:00",
                    "status": "FIXING"
                }
            )

            response = test_client.get("/store/1/1-1-1")
            assert response.status == "200 OK"
            assert "orderUid" in response.json
            assert "model" in response.json
            assert "size" in response.json
            assert "date" in response.json
            assert "warrantyDate" in response.json
            assert "warrantyStatus" in response.json


def test_request_warranty(fresh_database, add_some_user):
    with app.test_client() as test_client:
        with requests_mock.Mocker(real_http=True) as m:
            m.post(
                re.compile("/orders"),
                json={"warrantyDate": "2020-11-11", "decision": "FIXING"}
            )
            response = test_client.post(
                "/store/1/1-1-1/warranty",
                json={"reason": "Broken"}
            )
            assert response.status == "200 OK"
            assert response.json["decision"] == 'FIXING'


def test_request_purchase(fresh_database, add_some_user):
    with app.test_client() as test_client:
        with requests_mock.Mocker(real_http=True) as m:
            m.post(re.compile("/orders/1"))
            response = test_client.post("/store/1/purchase", json={"size": "L", "model": "item 1"})
            assert response.status == "201 CREATED"


def test_request_refund(fresh_database, add_some_user):
    with app.test_client() as test_client:
        with requests_mock.Mocker(real_http=True) as m:
            m.delete(re.compile("/orders/1"))
            response = test_client.delete("/store/1/1-1-1/refund")
            assert response.status == "204 NO CONTENT"
