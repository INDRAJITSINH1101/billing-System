from django.urls import path
from .views import (
    login_view,
    signup_view,
    logout_view,
    bills_list,
    bill_create,
    download_bill,
    bill_details_view,
    check_customer_details,
    create_checkout_session,payment_success_view,
    payment_cancel_view,
    bill_edit,
    bill_delete,
    manual_payment,
)

urlpatterns = [
    path("login/", login_view, name="login"),
    path("signup/", signup_view, name="signup"),
    path("logout/", logout_view, name="logout"),

    path("bills/", bills_list, name="bills-list"),
    path("bills/create/", bill_create, name="bill-create"),
    path("bills/<int:bill_id>/edit/", bill_edit, name="bill-edit"),
    path("bills/<int:bill_id>/delete/", bill_delete, name="bill-delete"),

    path("bills/check-customer/", check_customer_details, name="check-customer"),

    path("bills/<int:bill_id>/view/", bill_details_view, name="bill-details"),

    path("bills/<int:bill_id>/download/", download_bill, name="bill-download"),

    path("bills/<int:bill_id>/pay/", create_checkout_session, name="bill-pay"),
    path("payment/success/", payment_success_view, name="payment-success"),
    path("payment/cancel/", payment_cancel_view, name="payment-cancel"),

    path("bills/<int:bill_id>/manual-pay/", manual_payment, name="manual-pay"),


]
