from django.contrib import admin
from .models import ShopSettings, Bill, User

admin.site.register(ShopSettings)
admin.site.register(Bill)
admin.site.register(User)
