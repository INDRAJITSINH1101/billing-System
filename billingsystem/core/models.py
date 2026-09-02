from django.db import models
from django.contrib.auth.models import AbstractUser
from django.contrib.auth import get_user_model
import json


# Create your models here.

class User(AbstractUser):
  full_name = models.CharField(max_length=200)

  is_admin = models.BooleanField(default=False)
  is_super_admin = models.BooleanField(default=False)

  def __str__(self):
    return self.username

class Bill(models.Model):
  created_by = models.ForeignKey(User, on_delete=models.CASCADE)
  invoice_number = models.CharField(max_length=50, blank=True, null=True)
  customer_name = models.CharField(max_length=200,blank=False, null=False)
  phone = models.CharField(max_length=20, blank=True, null=True)
  email = models.EmailField(blank=True, null=True)
  items = models.TextField() 
  sub_total = models.FloatField()
  discount_percent = models.FloatField(null=True, blank=True, default=0)
  discount_amount = models.FloatField(null=True, blank=True, default=0)
  final_discount = models.FloatField(default=0)
  taxable_amount = models.FloatField(default=0)
  sgst_rate = models.FloatField(default=0)
  cgst_rate = models.FloatField(default=0)
  sgst_amount = models.FloatField(default=0)
  cgst_amount = models.FloatField(default=0)
  total_amount = models.FloatField()
  created_at = models.DateTimeField(auto_now_add=True)
  

  @property
  def is_paid(self):
    try:
        return self.payment.status == 'paid'
    except Payment.DoesNotExist:
        return False

  def get_items(self):
    return json.loads(self.items or "[]")
    
  def __str__(self):
    return f"Bill #{self.id} - {self.customer_name}"
  
PAYMENT_STATUS_CHOICES = (
   ('pending','Pending'),
   ('paid','Paid'),
   ('failed','Failed')
)

PAYMENT_METHOD_CHOICES = (
   ('cash', 'Cash'),
   ('upi', 'UPI'),
   ('card', 'Card'),
   ('stripe', 'Stripe'),
)

class Payment(models.Model):
  bill = models.OneToOneField(Bill, on_delete=models.CASCADE,related_name='payment',verbose_name='Associated Bill')
  status = models.CharField(max_length=50,choices=PAYMENT_STATUS_CHOICES,default='pending',db_index=True)
  amount = models.DecimalField(max_digits=10, decimal_places=2,help_text='Total amount paid, including taxes and fees.')
  currency = models.CharField(max_length=5, default='INR')
  gateway = models.CharField(max_length=50,choices=PAYMENT_METHOD_CHOICES,default='cash')
  gateway_id = models.CharField(max_length=250, null=True, blank=True,unique=True,help_text='Stripe Payment Intent ID or equivalent.')
  checkout_session_id = models.CharField(max_length=250, null=True, blank=True,help_text='Stripe Checkout Session ID (cs_...)')
  is_refunded = models.BooleanField(default=False)
  refund_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
  refund_id = models.CharField(max_length=250, null=True, blank=True)
  created_at = models.DateTimeField(auto_now_add=True)
  updated_at = models.DateTimeField(auto_now=True)
  user_paid = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True,help_text='The admin user who initiated the payment/recorded it.')
  gateway_response = models.JSONField(null=True, blank=True,)

  class Meta:
        verbose_name = 'Payment Transaction'
        verbose_name_plural = 'Payment Transactions'
        ordering = ('-created_at',)

  def __str__(self):
        return f"{self.gateway.upper()} - {self.status.title()} for Bill #{self.bill.id}"

class ShopSettings(models.Model):
    shop_name = models.CharField(max_length=255)
    address = models.TextField()
    phone = models.CharField(max_length=50, blank=True, null=True)
    email = models.CharField(max_length=100, blank=True, null=True)
    gstin = models.CharField(max_length=30, blank=True, null=True)
    state_name = models.CharField(max_length=100, blank=True, null=True)
    state_code = models.CharField(max_length=10, blank=True, null=True)

    bank_name = models.CharField(max_length=100, blank=True, null=True)
    account_no = models.CharField(max_length=50, blank=True, null=True)
    ifsc_code = models.CharField(max_length=20, blank=True, null=True)

    invoice_prefix = models.CharField(max_length=20, default="INV")
    starting_number = models.IntegerField(default=1)

    authorized_text = models.TextField(
        default="For Company\nAuthorized Signatory"
    )

    def __str__(self):
        return "Shop Settings"

