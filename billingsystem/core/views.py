from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.core.paginator import Paginator
from django.db.models import Q, Sum, Count
from django.http import HttpResponse, JsonResponse
from django.conf import settings
from .config import SHOP_DETAILS
from datetime import datetime, timedelta
from django.template.loader import get_template
from .form import AdminSignupForm
from .models import Bill,Payment
from num2words import num2words
import json
from xhtml2pdf import pisa
import stripe
from django.urls import reverse
import uuid

try:
    stripe.api_key = settings.STRIPE_SECRET_KEY
except AttributeError:
    pass

def is_admin(user):
    return user.is_authenticated and (
        user.is_admin or user.is_super_admin or user.is_superuser
    )

admin_required = user_passes_test(is_admin)

def generate_invoice_no(bill):
    invoice_prefix = SHOP_DETAILS.get("INVOICE_PREFIX", "INV")
    return bill.invoice_number or f"{invoice_prefix}-{bill.id:04d}"

def amount_to_words(amount):
    try:
        return num2words(round(amount), to="cardinal", lang="en_IN").title() + " Only"
    except Exception:
        return num2words(round(amount), to="cardinal", lang="en").title() + " Only"

def billing_metrics():
    now = datetime.now()
    def agg(query_args):
        res = Bill.objects.filter(**query_args) if query_args else Bill.objects.all()
        data = res.aggregate(total_sum=Sum("total_amount"), total_count=Count("id"))
        return data["total_sum"] or 0.0, data["total_count"] or 0

    total_sum, total_count = agg({})
    two_days_sum, two_days_count = agg({"created_at__gte": now - timedelta(days=2)})
    week_sum, week_count = agg({"created_at__gte": now - timedelta(weeks=1)})
    month_sum, month_count = agg({"created_at__gte": now - timedelta(days=30)})
    return {
        "total_all_time_sum": total_sum,
        "total_all_time_count": total_count,
        "last_2_days_sum": two_days_sum,
        "last_2_days_count": two_days_count,
        "last_1_week_sum": week_sum,
        "last_1_week_count": week_count,
        "last_1_month_sum": month_sum,
        "last_1_month_count": month_count,
    }

def apply_filters(request):
    query = Q()
    params = {}

    def safe_float(v):
        try: return float(v)
        except: return None

    search = request.GET.get("search", "").strip()
    if search:
        query &= (Q(invoice_number__icontains=search) |
                  Q(customer_name__icontains=search))
        params["search"] = search

    date_from = request.GET.get("date_from")
    if date_from:
        query &= Q(created_at__date__gte=date_from)
        params["date_from"] = date_from

    date_to = request.GET.get("date_to")
    if date_to:
        query &= Q(created_at__date__lte=date_to)
        params["date_to"] = date_to

    min_amt = safe_float(request.GET.get("amount_min"))
    if min_amt is not None:
        query &= Q(total_amount__gte=min_amt)
        params["amount_min"] = min_amt

    max_amt = safe_float(request.GET.get("amount_max"))
    if max_amt is not None:
        query &= Q(total_amount__lte=max_amt)
        params["amount_max"] = max_amt
    return query, params

def paginate(request, queryset, default=10):
    per_page = request.GET.get("per_page", default)
    try:
        per_page = max(1, int(per_page))
    except:
        per_page = default
    paginator = Paginator(queryset, per_page)
    return paginator.get_page(request.GET.get("page")), paginator, per_page


def parse_items(request):
    names = request.POST.getlist("pname")
    qtys = request.POST.getlist("qty")
    rates = request.POST.getlist("rate")
    amounts = request.POST.getlist("amount")

    items = []
    for i in range(len(names)):
        if names[i].strip():
            items.append({
                "product_name": names[i],
                "qty": qtys[i],
                "rate": rates[i],
                "amount": amounts[i],
            })
    return items

def f(value):
    try: return float(value)
    except: return 0

def signup_view(request):
    form = AdminSignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        return redirect("login")
    return render(request, "signup.html", {"form": form})

def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")

        user = authenticate(username=username, password=password)
        if not user:
            return render(request, "login.html", {"error": "Invalid Credentials"})
        if not is_admin(user):
            return render(request, "login.html", {"error": "Not allowed"})
        login(request, user)
        return redirect("bills-list")
    return render(request, "login.html")

@login_required
def logout_view(request):
    logout(request)
    return redirect("login")

@admin_required
def bills_list(request):
    metrics = billing_metrics()

    queryset = Bill.objects.all().order_by("-created_at")

    query, filter_params = apply_filters(request)
    if query:
        queryset = queryset.filter(query)

    bills_page, paginator, per_page = paginate(request, queryset)
    per_page_options = [10, 20, 30, 40]
    return render(request, "bills_list.html", {
        "bills": bills_page,
        "filter_params": filter_params,
        "metrics": metrics,
        "paginator": paginator,
        "per_page": per_page,
        "per_page_options": per_page_options,
    })

@admin_required
def check_customer_details(request):
    phone = request.GET.get("phone")
    if not phone:
        return JsonResponse({"found": False})
    bill = (
        Bill.objects.filter(phone=phone)
        .exclude(customer_name="")
        .order_by("-created_at")
        .first()
    )
    return JsonResponse({
        "found": bool(bill),
        "name": bill.customer_name if bill else "",
        "email": bill.email if bill else "",
    })

@admin_required
def bill_details_view(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    payment_status = "Paid" if bill.is_paid else "Unpaid"
    return render(request, "bill_details.html", {
        "bill": bill,
        "items": bill.get_items(),
        "invoice_no": generate_invoice_no(bill),
        "payment_status": payment_status,
    })

@admin_required
def bill_create(request):
    if request.method == "POST":
        last_bill = Bill.objects.order_by("-id").first()
        next_no = (last_bill.id + 1) if last_bill else 1
        prefix = SHOP_DETAILS.get("INVOICE_PREFIX", "INV")
        invoice_number = f"{prefix}-{next_no:04d}"
        sub_total = f(request.POST.get("sub_total"))
        discount_percent = f(request.POST.get("discount_percent"))
        discount_amount = f(request.POST.get("discount_amount"))

        percent_discount_amount = 0
        if discount_percent > 0:
            percent_discount_amount = (sub_total * discount_percent) / 100
        Bill.objects.create(
            created_by=request.user,
            invoice_number=invoice_number,
            customer_name=request.POST.get("customer_name"),
            phone=request.POST.get("phone"),
            email=request.POST.get("email"),
            items=json.dumps(parse_items(request)),
            sub_total=f(request.POST.get("sub_total")),
            discount_percent=discount_percent,
            discount_amount=discount_amount,
            final_discount=percent_discount_amount,
            taxable_amount=f(request.POST.get("taxable_amount")),
            sgst_rate=f(request.POST.get("sgst_rate")),
            cgst_rate=f(request.POST.get("cgst_rate")),
            sgst_amount=f(request.POST.get("sgst_amount")),
            cgst_amount=f(request.POST.get("cgst_amount")),
            total_amount=f(request.POST.get("grand_total")),
        )
        return redirect("bills-list")
    empty_bill = {
        "customer_name": "",
        "phone": "",
        "email": "",
        "sub_total": 0,
        "discount_percent": 0,
        "discount_amount": 0,
        "final_discount": 0,
        "taxable_amount": 0,
        "sgst_rate": 0,
        "cgst_rate": 0,
        "sgst_amount": 0,
        "cgst_amount": 0,
        "total_amount": 0,
    }
    return render(request, "bill_create.html",{
        "bill": empty_bill,         
        "items": [],        
        "is_editing": False
    })

@admin_required
def bill_edit(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    if request.method == 'POST':
        sub_total = f(request.POST.get("sub_total"))
        discount_percent = f(request.POST.get("discount_percent"))
        discount_amount = f(request.POST.get("discount_amount"))

        percent_discount_amount = 0
        if discount_percent > 0:
            percent_discount_amount = (sub_total * discount_percent) / 100

        bill.customer_name = request.POST.get("customer_name")
        bill.phone = request.POST.get("phone")
        bill.email = request.POST.get("email")
        bill.items = json.dumps(parse_items(request))
        bill.sub_total = sub_total
        bill.discount_percent = discount_percent
        bill.discount_amount = discount_amount
        bill.final_discount = percent_discount_amount
        bill.taxable_amount = f(request.POST.get("taxable_amount"))
        bill.sgst_rate = f(request.POST.get("sgst_rate"))
        bill.cgst_rate = f(request.POST.get("cgst_rate"))
        bill.sgst_amount = f(request.POST.get("sgst_amount"))
        bill.cgst_amount = f(request.POST.get("cgst_amount"))
        bill.total_amount = f(request.POST.get("grand_total"))
        bill.save()
        return redirect("bill-details", bill_id=bill.id)
    return render(request, "bill_create.html",{
        "bill":bill,
        "items":bill.get_items(),
        "is_editing": True,
    })

@admin_required
def bill_delete(request,bill_id):
    bill = get_object_or_404(Bill,id=bill_id)
    if request.method=='POST':
        bill.delete()
        return redirect("bills-list")
    return render(request, "bill_confirm_delete.html", {"bill":bill})

@admin_required
def download_bill(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)
    payment_status = "Paid" if bill.is_paid else "Unpaid"
    context = {
        "bill": bill,
        "items": bill.get_items(),
        "invoice_no": generate_invoice_no(bill),
        "amount_in_words": amount_to_words(bill.total_amount),
        "shop_details": SHOP_DETAILS,
        "payment_status": payment_status,
    }
    template = get_template("invoice_bill.html")
    html = template.render(context)

    response = HttpResponse(content_type="application/pdf")
    filename = f"{context['invoice_no']}-{bill.customer_name.replace(' ', '_')}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    pisa_status = pisa.CreatePDF(html, dest=response, debug=1)
    if pisa_status.err:
        return HttpResponse(f"PDF Generation Error: {pisa_status.err_msg}")

    return response

@admin_required
def create_checkout_session(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)

    if bill.is_paid:
        return redirect("bill-details", bill_id=bill.id)
    
    amount_in_paise = int(round(bill.total_amount * 100))

    payment, created = Payment.objects.get_or_create(bill=bill,defaults={
        'amount':bill.total_amount,
        'currency':'INR',
        'user_paid':request.user,
        'status':'pending'
    })

    try:
        success_url = request.build_absolute_uri(reverse('payment-success')) + f'?session_id={{CHECKOUT_SESSION_ID}}&bill_id={bill.id}'
        cancel_url = request.build_absolute_uri(reverse('payment-cancel')) + f'?bill_id={bill.id}'

        session = stripe.checkout.Session.create(
            payment_method_types=['card'],
            billing_address_collection='required',
            customer_email=bill.email if bill.email else None,
            line_items=[{
                'price_data':{
                    'currency':'inr',
                    'product_data':{
                        'name':f'Bill #{bill.invoice_number or bill.id} for {bill.customer_name}',
                    },
                    'unit_amount':amount_in_paise,
                },
                'quantity':1
            }],
            mode = 'payment',
            success_url=success_url,
            cancel_url=cancel_url,
            client_reference_id=str(bill.id)
        )

        payment.checkout_session_id = session.id
        payment.save()
        return redirect(session.url, code=303)
    except Exception as e:
        payment.status = 'failed'
        payment.save()
        return HttpResponse(f"An error occurred while creating the checkout session: {e}", status=400)

@admin_required
def payment_success_view(request):
    session_id=request.GET.get('session_id')
    bill_id = request.GET.get('bill_id')
    payment = get_object_or_404(Payment, checkout_session_id=session_id)
    bill = payment.bill
    try:
        session = stripe.checkout.Session.retrieve(session_id)
        if session.payment_status == 'paid':
            payment.status = 'paid'
            payment.gateway_id = session.payment_intent 
            payment.save()
            message = "Payment successfully completed and bill is marked as PAID."
        else:
            message = "Payment successful but status confirmation is pending."
    except Exception as e:
        message = f"Payment status confirmation failed: {e}"
    return render(request, 'payment_status.html', {
        'status': payment.status, 
        'bill': bill,
        'message': message,
        'invoice_no': generate_invoice_no(bill),
    })

@admin_required
def payment_cancel_view(request):
    bill_id= request.GET.get('bill_id')
    bill = get_object_or_404(Bill, id=bill_id)if bill_id else None
    return render(request, 'payment_status.html', {
        'status': 'cancelled', 
        'bill': bill,
        'message': 'Payment process was cancelled by the user.',
        'invoice_no': generate_invoice_no(bill),
    })

@admin_required
def manual_payment(request, bill_id):
    bill = get_object_or_404(Bill, id=bill_id)

    if request.method == "POST":
        method = request.POST.get("method")
        auto_txn_id = generate_transaction_id(method)
        Payment.objects.update_or_create(
            bill=bill,
            defaults={
                "status": "paid",
                "amount": bill.total_amount,
                "currency": "INR",
                "gateway": method,
                "gateway_id": auto_txn_id,
                "user_paid": request.user
            }
        )

        return redirect("bill-details", bill_id=bill.id)

    return redirect("bills-list")

def generate_transaction_id(method):
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    random_part = uuid.uuid4().hex[:4].upper()
    return f"{method.upper()}-{timestamp}-{random_part}"
