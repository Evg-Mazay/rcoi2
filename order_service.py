import os
from uuid import uuid4
from enum import Enum
from datetime import date

from pydantic import BaseModel, ValidationError
from flask import Flask, request, jsonify
import sqlalchemy as sa
import requests

import database

app = Flask(__name__)
ROOT_PATH = "/api/v1"
WAREHOUSE_SERVICE_URL = os.environ.get("WAREHOUSE_SERVICE", "localhost:8280")
print(f"Warehouse service url: {WAREHOUSE_SERVICE_URL} ($WAREHOUSE_SERVICE)")
WARRANTY_SERVICE_URL = os.environ.get("WARRANTY_SERVICE", "localhost:8180")
print(f"Warranty service url: {WARRANTY_SERVICE_URL} ($WARRANTY_SERVICE)")


class Order(database.Base):
    __tablename__ = 'orders'
    id = sa.Column(sa.Integer, primary_key=True)
    item_uid = sa.Column(sa.Text)
    order_date = sa.Column(sa.TIMESTAMP)
    order_uid = sa.Column(sa.Text, unique=True)
    status = sa.Column(sa.VARCHAR(255))
    user_uid = sa.Column(sa.Text)


class NewOrderRequest(BaseModel):
    model: str
    size: str


class WarrantyRequest(BaseModel):
    reason: str


class Status(str, Enum):
    paid = "PAID"
    canceled = "CANCELED"
    waiting = "WAITING"


@app.route("/manage/health", methods=["GET"])
def health_check():
    return "UP", 200


@app.route(f"{ROOT_PATH}/orders/<string:user_uid>", methods=["POST"])
def request_new_order(user_uid):
    """
    Сделать заказ от имени пользователя
    """
    try:
        new_item_request = NewOrderRequest.parse_obj(request.get_json(force=True))
    except ValidationError as e:
        return {"message": e.errors()}, 400

    order_uid = str(uuid4())

    if not requests.get(f"http://{WAREHOUSE_SERVICE_URL}/manage/health").ok:
        return {"message": "Warehouse sevice unavailable"}, 422
    if not requests.get(f"http://{WARRANTY_SERVICE_URL}/manage/health").ok:
        return {"message": "Warranty sevice unavailable"}, 422

    warehouse_service_response = requests.post(
        f"http://{WAREHOUSE_SERVICE_URL}{ROOT_PATH}/warehouse",
        json={
            "orderUid": order_uid,
            "model": new_item_request.model,
            "size": new_item_request.size
        }
    )
    if not warehouse_service_response.ok:
        return {"message": f"bad response from warehouse "
                           f"({warehouse_service_response.status_code}): "
                           f"{warehouse_service_response.text}"}, 422
    elif not warehouse_service_response.json().get("orderItemUid"):
        return {"message": "Something terrible happens to warehouse :/"}, 500
    item_uid = warehouse_service_response.json().get("orderItemUid")

    requests.post(f"http://{WARRANTY_SERVICE_URL}{ROOT_PATH}/warranty/{item_uid}")

    with database.Session() as s:
        s.add(Order(
            item_uid=warehouse_service_response.json()["orderItemUid"],
            order_date=date.today(),
            order_uid=order_uid,
            status=Status.paid,
            user_uid=user_uid,
        ))

    return {"orderUid": order_uid}, 200


@app.route(f"{ROOT_PATH}/orders/<string:user_uid>/<string:order_uid>", methods=["GET"])
def request_order(user_uid, order_uid):
    """
    Получить информацию по конкретному заказу пользователя
    """
    with database.Session() as s:
        order = (
            s.query(Order)
            .filter(Order.order_uid == order_uid)
            .filter(Order.user_uid == user_uid)
            .one_or_none()
        )
        if not order:
            return {"message": "Not found"}, 404

        return {
            "orderUid": order.order_uid,
            "orderDate": order.order_date.isoformat(),
            "itemUid": order.item_uid,
            "status": order.status
        }, 200


@app.route(f"{ROOT_PATH}/orders/<string:user_uid>", methods=["GET"])
def request_all_orders(user_uid):
    """
    Получить все заказы пользователя
    """
    with database.Session() as s:
        orders = s.query(Order).filter(Order.user_uid == user_uid).all()

        result = [{
            "orderUid": order.order_uid,
            "orderDate": order.order_date.isoformat(),
            "itemUid": order.item_uid,
            "status": order.status
        } for order in orders]
        return jsonify(result), 200


@app.route(f"{ROOT_PATH}/orders/<string:order_uid>/warranty", methods=["POST"])
def request_warranty(order_uid):
    """
    Запрос гарантии по заказу
    """
    try:
        warranty_request = WarrantyRequest.parse_obj(request.get_json(force=True))
    except ValidationError as e:
        return {"message": e.errors()}, 400

    if not requests.get(f"http://{WAREHOUSE_SERVICE_URL}/manage/health").ok:
        return {"message": "Warehouse sevice unavailable"}, 422

    with database.Session() as s:
        order = s.query(Order).filter(Order.order_uid == order_uid).one_or_none()
        if not order:
            return {"message": "Order not found"}, 404

        warehouse_service_response = requests.post(
            f"http://{WAREHOUSE_SERVICE_URL}{ROOT_PATH}/warehouse/{order.item_uid}/warranty",
            json={"reason": warranty_request.reason}
        )
        if not warehouse_service_response.ok:
            return {"message": "Warranty not found"}, 404

    return warehouse_service_response.json(), 200


@app.route(f"{ROOT_PATH}/orders/<string:order_uid>", methods=["DELETE"])
def request_delete_order(order_uid):
    """
    Вернуть заказ
    """
    with database.Session() as s:
        order = s.query(Order).filter(Order.order_uid == order_uid).one_or_none()
        if not order:
            return {"message": "Order not found"}, 404

        if not requests.get(f"http://{WAREHOUSE_SERVICE_URL}/manage/health").ok:
            return {"message": "Warehouse sevice unavailable"}, 422

        warehouse_service_response = requests.delete(
            f"http://{WAREHOUSE_SERVICE_URL}{ROOT_PATH}/warehouse/{order.item_uid}",
        )
        if not warehouse_service_response.ok:
            return {"message": "Order not found on warehouse"}, 422

        s.delete(order)
    return '', 204


if __name__ == '__main__':
    PORT = os.environ.get("PORT", 7777)
    print("LISTENING ON PORT:", PORT, "($PORT)")
    database.create_schema()
    app.url_map.strict_slashes = False
    app.run("0.0.0.0", PORT)
