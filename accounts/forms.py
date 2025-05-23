from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
import re # For phone number validation

from .models import Profile, Customer, Vendor


class CreateUserForm(UserCreationForm):
    """Form for creating a new user with an email field."""
    email = forms.EmailField()

    class Meta:
        """Meta options for the CreateUserForm."""
        model = User
        fields = [
            'username',
            'email',
            'password1',
            'password2'
        ]


class UserUpdateForm(forms.ModelForm):
    """Form for updating existing user information."""
    class Meta:
        """Meta options for the UserUpdateForm."""
        model = User
        fields = [
            'username',
            'email'
        ]


class ProfileUpdateForm(forms.ModelForm):
    """Form for updating user profile information."""
    class Meta:
        """Meta options for the ProfileUpdateForm."""
        model = Profile
        fields = [
            'telephone',
            'email',
            'first_name',
            'last_name',
            'profile_picture'
        ]


class CustomerForm(forms.ModelForm):
    """Form for creating/updating customer information."""
    class Meta:
        model = Customer
        fields = [
            'first_name',
            'last_name',
            'address',
            'email',
            'phone',
            # 'loyalty_points'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter first name'
            }),
            'last_name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter last name'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'placeholder': 'Enter address',
                'rows': 3
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter email'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter 10-digit phone (e.g., 98XXXXXXXX)'
            }),
            # 'loyalty_points': forms.NumberInput(attrs={
            #     'class': 'form-control',
            #     'placeholder': 'Enter loyalty points'
            # }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields required
        self.fields['first_name'].required = True
        self.fields['last_name'].required = True
        self.fields['address'].required = True
        self.fields['email'].required = True
        self.fields['phone'].required = True

        # Customize error messages for required fields
        self.fields['first_name'].error_messages.update({
            'required': 'Please enter the customer\'s first name.'
        })
        self.fields['last_name'].error_messages.update({
            'required': 'Please enter the customer\'s last name.'
        })
        self.fields['address'].error_messages.update({
            'required': 'Please provide the customer\'s address.'
        })
        self.fields['email'].error_messages.update({
            'required': 'An email address is required for the customer.'
        })
        self.fields['phone'].error_messages.update({
            'required': 'A phone number is required for the customer.'
        })

    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone: # Proceed only if phone has a value (required check is done before this)
            # Remove any non-digit characters, in case user enters spaces or hyphens
            phone_digits = re.sub(r'\D', '', phone)
            if not phone_digits.isdigit():
                 raise forms.ValidationError("Phone number must contain only digits.")
            if len(phone_digits) != 10:
                raise forms.ValidationError("Phone number must be exactly 10 digits long.")
            if not (phone_digits.startswith('98') or phone_digits.startswith('97')):
                raise forms.ValidationError("Phone number must start with '98' or '97'.")
            return phone_digits # Return the cleaned, all-digits phone number
        return phone


class VendorForm(forms.ModelForm):
    """Form for creating/updating vendor information."""
    class Meta:
        model = Vendor
        fields = ['name', 'phone_number', 'address']
        widgets = {
            'name': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Vendor Name'}
            ),
            'phone_number': forms.TextInput( # Changed to TextInput for easier string validation
                attrs={'class': 'form-control', 'placeholder': 'Enter 10-digit phone (e.g., 98XXXXXXXX)'}
            ),
            'address': forms.TextInput(
                attrs={'class': 'form-control', 'placeholder': 'Address'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Make all fields required
        self.fields['name'].required = True
        self.fields['phone_number'].required = True
        self.fields['address'].required = True

        # Customize error messages for required fields
        self.fields['name'].error_messages.update({
            'required': 'Vendor name must be provided.'
        })
        self.fields['phone_number'].error_messages.update({
            'required': 'A phone number is mandatory for the vendor.'
        })
        self.fields['address'].error_messages.update({
            'required': 'An address is required for the vendor.'
        })

    def clean_phone_number(self):
        phone_number_str = self.cleaned_data.get('phone_number')
        if phone_number_str: # Proceed only if it has a value
            # Remove any non-digit characters
            phone_digits = re.sub(r'\D', '', str(phone_number_str)) # Ensure it's a string for re.sub

            if not phone_digits.isdigit():
                raise forms.ValidationError("Phone number must contain only digits.")
            if len(phone_digits) != 10:
                raise forms.ValidationError("Phone number must be exactly 10 digits long.")
            if not (phone_digits.startswith('98') or phone_digits.startswith('97')):
                raise forms.ValidationError("Phone number must start with '98' or '97'.")
            # Since the model field `phone_number` is BigIntegerField,
            # we should return an integer if it's valid.
            try:
                return int(phone_digits)
            except ValueError:
                # This should ideally not happen if isdigit() passed, but as a safeguard
                raise forms.ValidationError("Invalid phone number format.")
        return phone_number_str # or None if it was initially empty