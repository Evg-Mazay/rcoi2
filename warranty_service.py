import os
from datetime import date
from enum import Enum

from pydantic import BaseModel, ValidationError
from flask import Flask, request
import sqlalchemy as sa

import database


app = Flask(__name__)
ROOT_PATH = "/api/v1"


class Warranty(database.Base):
    __tablename__ = 'warranty'
    id = sa.Column(sa.Integer, primary_key=True)
    comment = sa.Column(sa.VARCHAR(1024), nullable=True)
    item_uid = sa.Column(sa.Text, unique=True)
    status = sa.Column(sa.VARCHAR(255))
    warranty_date = sa.Column(sa.TIMESTAMP)


class Status(str, Enum):
    on = "ON_WARRANTY"
    use = "USE_WARRANTY"
    removed = "REMOVED_FROM_WARRANTY"


class WarrantyRequest(BaseModel):
    reason: str
    availableCount: int


@app.route("/manage/health", methods=["GET"])
def health_check():
    return "UP", 200


@app.route(f"{ROOT_PATH}/warranty/<string:item_uid>", methods=["GET"])
def request_warranty_status(item_uid):
    """
    Информация о статусе гарантии
    """
    with database.Session() as s:
        warranty = s.query(Warranty).filter(Warranty.item_uid == item_uid).one_or_none()
        if not warranty:
            return {"message": "Not found"}, 404
        return {
                   "itemUid": warranty.item_uid,
                   "warrantyDate": warranty.warranty_date.isoformat(),
                   "status": warranty.status
               }, 200


@app.route(f"{ROOT_PATH}/warranty/<string:item_uid>/warranty", methods=["POST"])
def request_warranty_result(item_uid):
    """
    Запрос решения по гарантии
    """
    try:
        warranty_request = WarrantyRequest.parse_obj(request.get_json(force=True))
    except ValidationError as e:
        return {"message": e.errors()}, 400

    with database.Session() as s:
        warranty = s.query(Warranty).filter(Warranty.item_uid == item_uid).one_or_none()
        if not warranty:
            return {"message": "Not found"}, 404
        if warranty.status != Status.on:
            decision = "REFUSED"
        elif warranty_request.availableCount > 0:
            decision = "RETURN"
        else:
            decision = "FIXING"

        return {
                   "warrantyDate": warranty.warranty_date.isoformat(),
                   "decision": decision
               }, 200


@app.route(f"{ROOT_PATH}/warranty/<string:item_uid>", methods=["POST"])
def request_start_warranty(item_uid):
    """
    Запрос на начало гарантийного периода
    """
    with database.Session() as s:
        s.add(Warranty(
            item_uid=item_uid,
            status=Status.on,
            warranty_date=date.today(),
        ))
    return '', 204


@app.route(f"{ROOT_PATH}/warranty/<string:item_uid>", methods=["DELETE"])
def request_stop_warranty(item_uid):
    """
    Ззапрос на закрытие гарантии
    """
    with database.Session() as s:
        warranty = s.query(Warranty).filter(Warranty.item_uid == item_uid).one_or_none()
        if warranty:
            warranty.status = Status.removed
        else:
            return {"message": "Not found"}, 404
    return '', 204


if __name__ == '__main__':
    PORT = os.environ.get("PORT", 7777)
    print("LISTENING ON PORT:", PORT, "($PORT)")
    database.create_schema()
    app.url_map.strict_slashes = False
    app.run("0.0.0.0", 8180)
