import os
import json
from datetime import date
from enum import Enum
from uuid import uuid4

import requests
from pydantic import BaseModel, ValidationError
from flask import Flask, request
import sqlalchemy as sa

import database


app = Flask(__name__)
WARRANTY_SERVICE_URL = os.environ.get("WARRANTY_SERVICE", "localhost")
print(f"Warranty service url: {WARRANTY_SERVICE_URL} ($WARRANTY_SERVICE)")


class Item(database.Base):
    __tablename__ = 'item'
    id = sa.Column(sa.Integer, primary_key=True)
    available_count = sa.Column(sa.Integer)
    model = sa.Column(sa.VARCHAR(255))
    size = sa.Column(sa.VARCHAR(255))


class OrderItem(database.Base):
    __tablename__ = 'order_item'
    id = sa.Column(sa.Integer, primary_key=True)
    canceled = sa.Column(sa.Boolean, default=False)
    order_item_uid = sa.Column(sa.Text, unique=True)
    order_uid = sa.Column(sa.Text)
    item_id = sa.Column(sa.Integer, sa.ForeignKey(Item.id, ondelete="CASCADE"))


class NewItemRequest(BaseModel):
    orderUid: str
    model: str
    size: str


class WarrantyRequest(BaseModel):
    reason: str


def refresh_items_in_db():
    with database.Session() as s:
        s.execute(Item.__table__.delete())
        s.add_all([
            Item(id=1, available_count=10000, model="Lego 8070", size="M"),
            Item(id=2, available_count=10000, model="Lego 42070", size="L"),
            Item(id=3, available_count=10000, model="Lego 8880", size="L"),
        ])
        print("Initialized default values in Item table")


@app.route("/warehouse/<string:order_item_id>", methods=["GET"])
def request_get_info(order_item_id):
    """
    Информация о вещах на складе
    """
    with database.Session() as s:
        order_and_item = (
            s.query(OrderItem, Item)
            .join(Item)
            .filter(OrderItem.order_item_uid == order_item_id)
            .one_or_none()
        )
        if not order_and_item:
            return {"message": "Not found"}, 404
        return {
            "model": order_and_item.Item.model,
            "size": order_and_item.Item.size,
        }, 200


@app.route("/warehouse", methods=["POST"])
def request_new_item():
    """
    Запрос на получение вещи со склада по новому заказу
    """
    try:
        new_item_request = NewItemRequest.parse_obj(request.get_json(force=True))
    except ValidationError as e:
        return {"message": e.errors()}, 400

    with database.Session() as s:
        item = (
            s.query(Item)
            .filter(Item.model == new_item_request.model)
            .filter(Item.size == new_item_request.size)
            .first()
        )
        if not item:
            return {"message": "requested item not found"}, 404
        elif item.available_count == 0:
            return {"message": "requested item is not available"}, 409

        item.available_count -= 1
        order = OrderItem(
            canceled=False,
            order_item_uid=str(uuid4()),
            order_uid=new_item_request.orderUid,
            item_id=item.id,
        )
        s.add(order)
        s.commit()
        return {
            "orderItemUid": order.order_item_uid,
            "orderUid": new_item_request.orderUid,
            "model": item.model,
            "size": item.size,
        }, 200


@app.route("/warehouse/<string:order_item_id>/warranty", methods=["POST"])
def request_warranty(order_item_id):
    """
    Запрос решения по гарантии
    """
    try:
        warranty_request = WarrantyRequest.parse_obj(request.get_json(force=True))
    except ValidationError as e:
        return {"message": e.errors()}, 400

    with database.Session() as s:
        order_and_item = (
            s.query(OrderItem, Item)
            .join(Item)
            .filter(OrderItem.order_item_uid == order_item_id)
            .one_or_none()
        )
        if not order_and_item:
            return {"message": "Order not found"}, 404
        available_count = order_and_item.Item.available_count

    warranty_service_response = requests.post(
        f"http://{WARRANTY_SERVICE_URL}/warranty/{order_item_id}/warranty",
        json={"reason": warranty_request.reason, "availableCount": available_count}
    )
    if not warranty_service_response.ok:
        return {"message": "Warranty not found"}, 422

    return warranty_service_response.json(), 200


@app.route("/warehouse/<string:order_item_id>", methods=["DELETE"])
def request_remove_item(order_item_id):
    """
    Вернуть заказ на склад
    """
    with database.Session() as s:
        order_and_item = (
            s.query(OrderItem, Item)
            .join(Item)
            .filter(OrderItem.order_item_uid == order_item_id)
            .one_or_none()
        )
        if not order_and_item:
            return {"message": "Not found"}, 404
        order_and_item.Item.available_count += 1
        order_and_item.OrderItem.canceled = True
        s.commit()
    return '', 204



if __name__ == '__main__':
    PORT = os.environ.get("PORT", 7777)
    print("LISTENING ON PORT:", PORT, "($PORT)")
    database.create_schema()
    refresh_items_in_db()
    app.run("0.0.0.0", PORT)
