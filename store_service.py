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
ORDER_SERVICE_URL = os.environ.get("ORDER_SERVICE", "localhost")
print(f"Order service url: {ORDER_SERVICE_URL} ($ORDER_SERVICE)")
WAREHOUSE_SERVICE_URL = os.environ.get("WAREHOUSE_SERVICE", "localhost")
print(f"Warehouse service url: {WAREHOUSE_SERVICE_URL} ($WAREHOUSE_SERVICE)")
WARRANTY_SERVICE_URL = os.environ.get("WARRANTY_SERVICE", "localhost")
print(f"Warranty service url: {WARRANTY_SERVICE_URL} ($WARRANTY_SERVICE)")


class User(database.Base):
    __tablename__ = 'users'
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.Text, unique=True)
    user_uid = sa.Column(sa.Text, unique=True)


class WarrantyRequest(BaseModel):
    reason: str


class NewOrderRequest(BaseModel):
    model: str
    size: str


def refresh_items_in_db():
    with database.Session() as s:
        s.execute(User.__table__.delete())
        s.add_all([
            User(id=1, name="Alex", user_uid="6d2cb5a0-943c-4b96-9aa6-89eac7bdfd2b"),
        ])
        print("Initialized default values in User table")


def is_user_exists(user_uid):
    with database.Session() as s:
        user = s.query(User).filter(User.user_uid == user_uid).one_or_none()
        return bool(user)


@app.route("/store/<string:user_uid>/orders", methods=["GET"])
def request_all_orders(user_uid):
    """
    Получить список заказов пользователя
    """
    if not is_user_exists(user_uid):
        return {"message": "User not found"}, 404

    order_service_response = requests.get(
        f"http://{ORDER_SERVICE_URL}/orders/{user_uid}"
    )
    if not order_service_response.ok:
        return {"message": "Order not found"}, 422

    result = []

    for order in order_service_response.json():
        order_uid = order["orderUid"]
        item_uid = order["itemUid"]

        warehouse_service_response = requests.get(
            f"http://{WAREHOUSE_SERVICE_URL}/warehouse/{order_uid}"
        )
        if not warehouse_service_response.ok:
            return {"message": "Order in warehouse not found"}, 422

        warranty_service_response = requests.get(
            f"http://{WARRANTY_SERVICE_URL}/warranty/{item_uid}"
        )
        if not warranty_service_response.ok:
            return {"message": "Warranty not found"}, 422

        result.append({
            "orderUid": order_uid,
            "date": order["orderDate"],
            "model": warehouse_service_response.json()["model"],
            "size": warehouse_service_response.json()["size"],
            "warrantyDate": warranty_service_response.json()["warrantyDate"],
            "warrantyStatus": warranty_service_response.json()["status"],
        })

    return jsonify(result), 200


@app.route("/store/<string:user_uid>/<string:order_uid>", methods=["GET"])
def request_order(user_uid, order_uid):
    """
    Информация по конкретному заказу
    """
    if not is_user_exists(user_uid):
        return {"message": "User not found"}, 404

    order_service_response = requests.get(
        f"http://{ORDER_SERVICE_URL}/orders/{user_uid}/{order_uid}"
    )
    if not order_service_response.ok:
        return {"message": "Order not found"}, 422
    item_uid = order_service_response.json()["itemUid"]

    warehouse_service_response = requests.get(
        f"http://{WAREHOUSE_SERVICE_URL}/warehouse/{order_uid}"
    )
    if not warehouse_service_response.ok:
        return {"message": "Order in warehouse not found"}, 422

    warranty_service_response = requests.get(
        f"http://{WARRANTY_SERVICE_URL}/warranty/{item_uid}"
    )
    if not warranty_service_response.ok:
        return {"message": "Warranty not found"}, 422

    return {
               "orderUid": order_uid,
               "date": order_service_response.json()["orderDate"],
               "model": warehouse_service_response.json()["model"],
               "size": warehouse_service_response.json()["size"],
               "warrantyDate": warranty_service_response.json()["warrantyDate"],
               "warrantyStatus": warranty_service_response.json()["status"],
           }, 200


@app.route("/store/<string:user_uid>/<string:order_uid>/warranty", methods=["POST"])
def request_warranty(user_uid, order_uid):
    """
    Запрос гарантии по заказу
    """
    if not is_user_exists(user_uid):
        return {"message": "User not found"}, 404

    try:
        warranty_request = WarrantyRequest.parse_obj(request.get_json(force=True))
    except ValidationError as e:
        return {"message": e.errors()}, 400

    order_service_response = requests.post(
        f"http://{ORDER_SERVICE_URL}/orders/{order_uid}/warranty",
        json={"reason": warranty_request.reason}
    )
    if not order_service_response.ok:
        return {"message": "Order not found"}, 422
    return order_service_response.json(), 200


@app.route("/store/<string:user_uid>/purchase", methods=["POST"])
def request_purchase(user_uid):
    """
    Выполнить покупку
    """
    if not is_user_exists(user_uid):
        return {"message": "User not found"}, 404

    try:
        new_order_request = NewOrderRequest.parse_obj(request.get_json(force=True))
    except ValidationError as e:
        return {"message": e.errors()}, 400

    order_service_response = requests.post(
        f"http://{ORDER_SERVICE_URL}/orders/{user_uid}",
        json={"model": new_order_request.model, "size": new_order_request.size}
    )
    if not order_service_response.ok:
        return {"message": "Order not created"}, 422
    return '', 201


@app.route("/store/<string:user_uid>/<string:order_uid>/refund", methods=["DELETE"])
def request_refund(user_uid, order_uid):
    """
    Вернуть заказ
    """
    if not is_user_exists(user_uid):
        return {"message": "User not found"}, 404

    order_service_response = requests.delete(
        f"http://{ORDER_SERVICE_URL}/orders/{user_uid}"
    )
    if not order_service_response.ok:
        return {"message": "Order not created"}, 422
    return '', 204


if __name__ == '__main__':
    PORT = os.environ.get("PORT", 7777)
    print("LISTENING ON PORT:", PORT, "($PORT)")
    database.create_schema()
    refresh_items_in_db()
    app.run("0.0.0.0", PORT)
