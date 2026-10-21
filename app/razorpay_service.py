"""
razorpay_service.py  —  Direct integration with Razorpay REST API.

NO gateway wrapper. Calls Razorpay's own REST API directly.

API used : Razorpay Orders API + Payment Verification
Docs     : https://razorpay.com/docs/api/orders/
           https://razorpay.com/docs/payments/server-integration/python/

Requires in .env:
    RAZORPAY_KEY_ID      = rzp_test_xxxxxxxxxxxx
    RAZORPAY_KEY_SECRET  = your_secret_here
"""

import os
import hmac
import hashlib
import logging
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger("lead_gen.razorpay_service")

RAZORPAY_BASE_URL = "https://api.razorpay.com/v1"


# ---------------------------------------------------------------------------
# Helper — get credentials from env
# ---------------------------------------------------------------------------

def _get_credentials():
    key_id     = os.getenv("RAZORPAY_KEY_ID")
    key_secret = os.getenv("RAZORPAY_KEY_SECRET")
    if not key_id or not key_secret:
        logger.error("RAZORPAY_KEY_ID or RAZORPAY_KEY_SECRET not set!")
        return None, None
    return key_id, key_secret


# ---------------------------------------------------------------------------
# Create a Razorpay order
# ---------------------------------------------------------------------------

def create_order(amount_inr: float, currency: str = "INR", receipt: str = "lead_gen_receipt"):
    """
    Create a Razorpay payment order.

    Parameters
    ----------
    amount_inr : float  — amount in INR (e.g. 499.00)
    currency   : str    — currency code (default: 'INR')
    receipt    : str    — your internal receipt/reference ID

    Returns
    -------
    dict with Razorpay order details or error info
    """
    key_id, key_secret = _get_credentials()
    if not key_id:
        return {"success": False, "error": "Razorpay credentials not configured."}

    # Razorpay requires amount in PAISE (1 INR = 100 paise)
    amount_paise = int(amount_inr * 100)

    logger.info(
        "RAZORPAY/CREATE_ORDER — amount: ₹%.2f (%d paise) | receipt: %s",
        amount_inr, amount_paise, receipt,
    )

    payload = {
        "amount":   amount_paise,
        "currency": currency,
        "receipt":  receipt,
        "notes": {
            "source": "Lead Gen API",
        },
    }

    try:
        response = requests.post(
            f"{RAZORPAY_BASE_URL}/orders",
            json=payload,
            auth=HTTPBasicAuth(key_id, key_secret),
            timeout=15,
        )
        logger.info("Razorpay create order status: %d", response.status_code)

        if response.status_code != 200:
            logger.error("Razorpay error: %s", response.text[:400])
            return {
                "success": False,
                "error":   response.json().get("error", {}).get("description", "Unknown error"),
            }

        order = response.json()
        logger.info("Order created: id=%s | status=%s", order.get("id"), order.get("status"))

        return {
            "success":    True,
            "order_id":   order["id"],
            "amount":     order["amount"],          # in paise
            "amount_inr": order["amount"] / 100,    # converted back to INR
            "currency":   order["currency"],
            "receipt":    order.get("receipt"),
            "status":     order["status"],
            # Frontend uses these to open the Razorpay checkout
            "razorpay_key_id": key_id,
        }

    except Exception as exc:
        logger.error("Razorpay create_order exception: %s", exc)
        return {"success": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# Verify Razorpay payment signature
# ---------------------------------------------------------------------------

def verify_payment(order_id: str, payment_id: str, signature: str) -> dict:
    """
    Verify the payment signature sent by Razorpay after successful payment.

    Razorpay sends: razorpay_order_id, razorpay_payment_id, razorpay_signature
    We re-generate the expected signature using HMAC-SHA256 and compare.

    Returns
    -------
    dict with 'success': True/False and message
    """
    _, key_secret = _get_credentials()
    if not key_secret:
        return {"success": False, "error": "Razorpay credentials not configured."}

    logger.info(
        "RAZORPAY/VERIFY — order_id: %s | payment_id: %s",
        order_id, payment_id,
    )

    # Generate expected signature
    message = f"{order_id}|{payment_id}"
    expected_signature = hmac.new(
        key_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if hmac.compare_digest(expected_signature, signature):
        logger.info("RAZORPAY/VERIFY — signature VALID ✓ | payment_id: %s", payment_id)
        return {
            "success":    True,
            "message":    "Payment verified successfully.",
            "payment_id": payment_id,
            "order_id":   order_id,
        }
    else:
        logger.warning("RAZORPAY/VERIFY — signature INVALID ✗ | payment_id: %s", payment_id)
        return {
            "success": False,
            "error":   "Payment signature verification failed. Possible tampered request.",
        }


# ---------------------------------------------------------------------------
# Fetch payment details from Razorpay
# ---------------------------------------------------------------------------

def get_payment_details(payment_id: str) -> dict:
    """
    Fetch complete details of a payment from Razorpay.

    Useful after verification to confirm amount, method, status.
    """
    key_id, key_secret = _get_credentials()
    if not key_id:
        return {"success": False, "error": "Razorpay credentials not configured."}

    logger.info("RAZORPAY/GET_PAYMENT — payment_id: %s", payment_id)

    try:
        response = requests.get(
            f"{RAZORPAY_BASE_URL}/payments/{payment_id}",
            auth=HTTPBasicAuth(key_id, key_secret),
            timeout=15,
        )
        if response.status_code != 200:
            return {"success": False, "error": response.json().get("error", {}).get("description")}

        data = response.json()
        return {
            "success":    True,
            "payment_id": data["id"],
            "order_id":   data.get("order_id"),
            "amount_inr": data["amount"] / 100,
            "currency":   data["currency"],
            "status":     data["status"],           # captured / failed / created
            "method":     data.get("method"),       # upi / card / netbanking
            "email":      data.get("email"),
            "contact":    data.get("contact"),
        }

    except Exception as exc:
        logger.error("RAZORPAY/GET_PAYMENT exception: %s", exc)
        return {"success": False, "error": str(exc)}
