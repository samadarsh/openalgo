import os

from flask import jsonify, make_response, request
from flask_restx import Namespace, Resource
from marshmallow import ValidationError

from limiter import limiter
from services.pending_orders_service import get_pending_orders_for_api
from utils.logging import get_logger

from .account_schema import PendingOrdersSchema

API_RATE_LIMIT = os.getenv("API_RATE_LIMIT", "10 per second")
api = Namespace("pendingorders", description="Action Center pending orders (read-only)")

logger = get_logger(__name__)

pending_orders_schema = PendingOrdersSchema()


@api.route("/", strict_slashes=False)
class PendingOrders(Resource):
    @limiter.limit(API_RATE_LIMIT)
    def post(self):
        """List the caller's Action Center orders and what became of them"""
        try:
            data = pending_orders_schema.load(request.json)
            success, response_data, status_code = get_pending_orders_for_api(
                data["apikey"], status=data["status"], limit=data["limit"]
            )
            return make_response(jsonify(response_data), status_code)
        except ValidationError as err:
            return make_response(jsonify({"status": "error", "message": err.messages}), 400)
        except Exception as e:
            logger.exception(f"Unexpected error in pendingorders endpoint: {e}")
            return make_response(
                jsonify({"status": "error", "message": "An unexpected error occurred"}), 500
            )
