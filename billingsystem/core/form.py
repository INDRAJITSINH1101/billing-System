from django import forms
from django.contrib.auth.forms import UserCreationForm
from .models import User

class AdminSignupForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['full_name', 'email', 'username', 'password1', 'password2']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_admin = True
        if commit:
            user.save()
        return user
