# Standard library imports
import json
import logging
import decimal # Import decimal

# Django core imports
from django.http import JsonResponse, HttpResponse
from django.urls import reverse
from django.shortcuts import render, get_object_or_404
from django.db import transaction
from django.db.models import Prefetch
from django.contrib.auth.decorators import login_required # For function-based views
from django.views.decorators.http import require_POST # To ensure POST requests

# Class-based views
from django.views.generic import DetailView, ListView
from django.views.generic.edit import CreateView, UpdateView, DeleteView

# Authentication and permissions
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# Third-party packages
from openpyxl import Workbook

# Local app imports
from store.models import Item
from accounts.models import Customer
from .models import Sale, Purchase, SaleDetail
from .forms import PurchaseForm
#importing Q for the customer searching
from django.db.models import Q
from functools import reduce
import operator
from django.http import HttpResponse
from django.template.loader import render_to_string
import pdfkit


logger = logging.getLogger(__name__)

config = pdfkit.configuration(wkhtmltopdf=r'C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe') # Ensure this path is correct or use environment variables

def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


def render_to_pdf(template_src, context_dict={}):
    html_content = render_to_string(template_src, context_dict)
    options = {
        'page-size': 'A4', 'encoding': 'UTF-8', 'enable-local-file-access': '',
        'no-outline': None, 'orientation' : 'landscape', 'margin-top': '5mm',
        'margin-right': '5mm', 'margin-bottom': '5mm', 'margin-left': '5mm',
        'zoom': '1.0', 'viewport-size': '1280x1024'
    }
    pdf = pdfkit.from_string(html_content, False, configuration=config, options=options)
    if pdf:
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="report.pdf"'
        return response
    return HttpResponse("PDF generation failed")
   

def export_detailed_sales_to_pdf(request, pk):
    sale = get_object_or_404(
        Sale.objects.select_related('customer').prefetch_related(
            Prefetch('saledetail_set', queryset=SaleDetail.objects.select_related('item'))
        ), id=pk
    )
    context = {'sale': sale}
    return render_to_pdf('transactions/sale_ticket.html', context)
    
def export_sales_to_pdf(request):
    sales = Sale.objects.all()
    context = {'sales': sales}
    pdf = render_to_pdf('transactions/sales_table.html', context) # This template has tax columns removed
    if pdf:
        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = 'inline; filename="sales_report.pdf"'
        return response
    logger.error("PDF generation failed.")
    return HttpResponse("PDF generation failed.")

def export_sales_to_excel(request):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Sales'
    columns = [
        'ID', 'Date', 'Customer', 'Items', 'Sub Total', 'Discount %', 'Discount Amount',
        'Grand Total', # Tax Amount, Tax Percentage removed
        'Amount Paid', 'Amount Change'
    ]
    worksheet.append(columns)
    sales = Sale.objects.all().prefetch_related('saledetail_set__item')
    for sale in sales:
        date_added = sale.date_added.replace(tzinfo=None) if sale.date_added.tzinfo else sale.date_added
        worksheet.append([
            sale.id, date_added, sale.customer.phone, sale.get_items_display(),
            sale.sub_total, sale.discount_percentage, sale.discount_amount,
            sale.grand_total, # sale.tax_amount, sale.tax_percentage removed
            sale.amount_paid, sale.amount_change
        ])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=sales.xlsx'
    workbook.save(response)
    return response


def export_purchases_to_excel(request):
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = 'Purchases'
    columns = [
        'ID', 'Item', 'Description', 'Vendor', 'Order Date', 'Delivery Date', 
        'Quantity', 'Delivery Status', 'Price per item (Rs)', 'Total Value'
    ]
    worksheet.append(columns)
    purchases = Purchase.objects.all()
    for purchase in purchases:
        delivery_date = purchase.delivery_date.replace(tzinfo=None) if purchase.delivery_date and purchase.delivery_date.tzinfo else purchase.delivery_date
        order_date = purchase.order_date.replace(tzinfo=None) if purchase.order_date.tzinfo else purchase.order_date
        worksheet.append([
            purchase.id, purchase.item.name, purchase.description, purchase.vendor.name,
            order_date, delivery_date, purchase.quantity, 
            purchase.get_delivery_status_display(), purchase.price, purchase.total_value
        ])
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=purchases.xlsx'
    workbook.save(response)
    return response


class SaleListView(LoginRequiredMixin, ListView):
    model = Sale
    template_name = "transactions/sales_list.html"
    context_object_name = "sales"
    paginate_by = 20
    ordering = ['-date_added'] # Changed to show recent sales first
    
    def get_queryset(self):
        return Sale.objects.all().select_related('customer').prefetch_related(
            Prefetch('saledetail_set', queryset=SaleDetail.objects.select_related('item'))
        ).order_by(*self.ordering) # Use self.ordering

class SaleDetailView(LoginRequiredMixin, DetailView):
    model = Sale
    template_name = "transactions/saledetail.html"
    
    def get_queryset(self):
        return Sale.objects.select_related('customer').prefetch_related(
            Prefetch('saledetail_set', queryset=SaleDetail.objects.select_related('item'))
        )


@login_required # Ensure user is logged in
def SaleCreateView(request): # Renamed for consistency, was SaleCreateView before
    context = {
        "active_icon": "sales",
        "customers": [c.to_select2() for c in Customer.objects.all()]
    }

    if request.method == 'POST':
        if is_ajax(request=request):
            try:
                data = json.loads(request.body)
                logger.info(f"Received data for sale creation: {data}")

                required_fields = [
                    'customer', 'sub_total', 'discount_percentage', 'discount_amount',
                    'grand_total', 'amount_paid', 'amount_change', 'items'
                ]
                for field in required_fields:
                    if field not in data or data[field] is None: # Also check for None
                        raise ValueError(f"Missing or null required field: {field}")

                sale_attributes = {
                    "customer": Customer.objects.get(id=int(data['customer'])),
                    "sub_total": decimal.Decimal(data["sub_total"]),
                    "discount_percentage": float(data["discount_percentage"]),
                    "discount_amount": decimal.Decimal(data["discount_amount"]),
                    "grand_total": decimal.Decimal(data["grand_total"]),
                    # "tax_amount": decimal.Decimal(data.get("tax_amount", "0.0")), # Removed
                    # "tax_percentage": float(data.get("tax_percentage", 0.0)), # Removed
                    "amount_paid": decimal.Decimal(data["amount_paid"]),
                    "amount_change": decimal.Decimal(data["amount_change"]),
                }

                with transaction.atomic():
                    new_sale = Sale.objects.create(**sale_attributes)
                    logger.info(f"Sale created: {new_sale}")

                    items = data["items"]
                    if not isinstance(items, list):
                        raise ValueError("Items should be a list")

                    for item_data in items: # Renamed 'item' to 'item_data' to avoid conflict
                        if not all(k in item_data for k in ["id", "price", "quantity", "total_item"]):
                            raise ValueError("Item is missing required fields")

                        item_instance = Item.objects.get(id=int(item_data["id"]))
                        item_quantity_sold = int(item_data["quantity"]) # Renamed for clarity

                        if item_instance.quantity < item_quantity_sold:
                            raise ValueError(f"Not enough stock for item: {item_instance.name}. Available: {item_instance.quantity}, Requested: {item_quantity_sold}")

                        detail_attributes = {
                            "sale": new_sale,
                            "item": item_instance,
                            "price": decimal.Decimal(item_data["price"]),
                            "quantity": item_quantity_sold,
                            "total_detail": decimal.Decimal(item_data["total_item"])
                        }
                        SaleDetail.objects.create(**detail_attributes)
                        logger.info(f"Sale detail created: {detail_attributes}")

                        item_instance.quantity -= item_quantity_sold
                        item_instance.save()

                return JsonResponse({'status': 'success', 'message': 'Sale created successfully!', 'redirect': reverse('saleslist')})
            except json.JSONDecodeError:
                return JsonResponse({'status': 'error', 'message': 'Invalid JSON format!'}, status=400)
            except Customer.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Customer not found!'}, status=400)
            except Item.DoesNotExist:
                return JsonResponse({'status': 'error', 'message': 'Item not found!'}, status=400)
            except ValueError as ve:
                logger.error(f"ValueError during sale creation: {ve}")
                return JsonResponse({'status': 'error', 'message': str(ve)}, status=400)
            except TypeError as te:
                logger.error(f"TypeError during sale creation: {te}")
                return JsonResponse({'status': 'error', 'message': str(te)}, status=400)
            except Exception as e:
                logger.error(f"Unexpected exception during sale creation: {e}", exc_info=True)
                return JsonResponse({'status': 'error', 'message': f'An unexpected error occurred: {str(e)}'}, status=500)
    return render(request, "transactions/sale_create.html", context=context)


class SaleDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Sale
    template_name = "transactions/saledelete.html"
    def get_success_url(self):
        return reverse("saleslist")
    def test_func(self):
        return self.request.user.is_superuser

# --- New View for Marking Sale as Paid ---
@login_required
@require_POST # Ensures this view only accepts POST requests
def mark_sale_as_paid(request, sale_id):
    try:
        sale = get_object_or_404(Sale, id=sale_id)

        if not request.user.is_staff: # Example permission check, adjust as needed
             return JsonResponse({'status': 'error', 'message': 'You do not have permission to perform this action.'}, status=403)

        if sale.amount_to_pay > 0: # Use the property
            sale.amount_paid = sale.grand_total
            sale.amount_change = sale.amount_paid - sale.grand_total # This will be Decimal('0.00')
            sale.save()
            return JsonResponse({
                'status': 'success',
                'message': 'Sale marked as fully paid.',
                'new_amount_paid': float(sale.amount_paid),
                'new_amount_to_pay': float(sale.amount_to_pay), # Will be 0.00
                'new_amount_change': float(sale.amount_change)  # Will be 0.00
            })
        else:
            return JsonResponse({'status': 'info', 'message': 'Sale is already fully paid or overpaid.'})

    except Exception as e:
        logger.error(f"Error marking sale {sale_id} as paid: {e}", exc_info=True)
        return JsonResponse({'status': 'error', 'message': 'An internal error occurred.'}, status=500)

# --- End New View ---


class PurchaseListView(LoginRequiredMixin, ListView):
    model = Purchase
    template_name = "transactions/purchases_list.html"
    context_object_name = "purchases"
    paginate_by = 10
    ordering = ['-order_date']


class PurchaseDetailView(LoginRequiredMixin, DetailView):
    model = Purchase
    template_name = "transactions/purchasedetail.html"


class PurchaseCreateView(LoginRequiredMixin, CreateView):
    model = Purchase
    form_class = PurchaseForm
    template_name = "transactions/purchases_form.html"
    def get_success_url(self):
        return reverse("purchaseslist")


class PurchaseUpdateView(LoginRequiredMixin, UpdateView):
    model = Purchase
    form_class = PurchaseForm
    template_name = "transactions/purchases_form.html"
    def get_success_url(self):
        return reverse("purchaseslist")


class PurchaseDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Purchase
    template_name = "transactions/purchasedelete.html"
    def get_success_url(self):
        return reverse("purchaseslist")
    def test_func(self):
        return self.request.user.is_superuser


class SaleCustomerSearchView(LoginRequiredMixin,ListView):
    model = Sale
    template_name = "transactions/sales_list.html"
    context_object_name = "sales"
    paginate_by = 10

    def get_queryset(self):
        queryset = super().get_queryset().select_related("customer").prefetch_related(
            Prefetch('saledetail_set', queryset=SaleDetail.objects.select_related('item'))
        )
        query = self.request.GET.get("q")
        if query:
            query_list = query.split()
            queryset = queryset.filter(
                reduce(operator.and_, (
                    Q(customer__first_name__icontains=q) |
                    Q(customer__last_name__icontains=q) |
                    Q(customer__email__icontains=q)
                    for q in query_list
                ))
            )
        return queryset.order_by('-date_added') # Ensure consistent ordering