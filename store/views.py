"""
Module: store.views

Contains Django views for managing items, profiles,
and deliveries in the store application.

Classes handle product listing, creation, updating,
deletion, and delivery management.
The module integrates with Django's authentication
and querying functionalities.
"""

# Standard library imports
import operator
from functools import reduce
import decimal # Import decimal for precise calculations
import logging # Added for logging

# Django core imports
from django.shortcuts import render
from django.urls import reverse, reverse_lazy
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Count, Sum

# Authentication and permissions
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin

# Class-based views
from django.views.generic import (
    DetailView, CreateView, UpdateView, DeleteView, ListView
)
from django.views.generic.edit import FormMixin

# Third-party packages
from django_tables2 import SingleTableView
import django_tables2 as tables
from django_tables2.export.views import ExportMixin

# Local app imports
from accounts.models import Profile, Vendor
# Import Sale, SaleDetail, and Purchase from transactions.models
from transactions.models import Sale, SaleDetail, Purchase
from .models import Category, Item, Delivery
from .forms import ItemForm, CategoryForm, DeliveryForm
from .tables import ItemTable

# Setup logger
logger = logging.getLogger(__name__)

@login_required
def dashboard(request):
    profiles = Profile.objects.all()
    items = Item.objects.all()
    total_items_quantity = (
        Item.objects.aggregate(Sum("quantity"))
        .get("quantity__sum", 0) or 0
    )
    items_count = items.count()
    profiles_count = profiles.count()
    all_sales_qs = Sale.objects.all() # QuerySet for all sales

    # Calculate Total Accounts Receivable
    total_accounts_receivable = decimal.Decimal('0.00')
    for sale_record in all_sales_qs:
        total_accounts_receivable += sale_record.amount_to_pay # Uses the amount_to_pay property

    # Data for Pie Chart (Category Distribution)
    category_data = Category.objects.annotate(
        item_count=Count("item__id")
    ).values("name", "item_count")
    categories_for_pie = [cat["name"] for cat in category_data]
    category_counts_for_pie = [cat["item_count"] for cat in category_data]

    # Data for Line Chart (Sales Over Time)
    sale_dates_data = (
        Sale.objects.values("date_added__date")
        .annotate(total_sales_on_date=Sum("grand_total")) # Summing grand_total for daily sales
        .order_by("date_added__date")
    )
    sale_dates_labels_for_line = [
        sale_entry["date_added__date"].strftime("%Y-%m-%d") for sale_entry in sale_dates_data
    ]
    sale_dates_values_for_line = [float(sale_entry["total_sales_on_date"] or 0) for sale_entry in sale_dates_data]

    # Pending Deliveries
    #project dhaki removed garako ho hai
    pending_deliveries = Delivery.objects.filter(is_delivered=False)

    # --- START OF PROFIT CALCULATION ---

    # 1. Calculate Total Revenue using Sale.grand_total
    total_revenue_agg = all_sales_qs.aggregate(total_grand=Sum('grand_total'))
    total_revenue = total_revenue_agg['total_grand'] or decimal.Decimal('0.00')
    # Ensure total_revenue is a Decimal
    if not isinstance(total_revenue, decimal.Decimal):
        try:
            total_revenue = decimal.Decimal(str(total_revenue))
        except (decimal.InvalidOperation, TypeError):
            logger.error(f"Could not convert total_revenue '{total_revenue_agg['total_grand']}' to Decimal. Defaulting to 0.")
            total_revenue = decimal.Decimal('0.00')

    # 2. Calculate Total Cost of Goods Sold (COGS)
    total_cogs = decimal.Decimal('0.00')
    item_latest_cost_cache = {} # Cache to store latest cost price for each item

    # Iterate through all items sold in all sales
    for sale_detail_item in SaleDetail.objects.select_related('item').all():
        item_instance = sale_detail_item.item # Renamed for clarity
        item_id = item_instance.id
        item_name = item_instance.name # For logging purposes
        
        cost_price_for_this_item = decimal.Decimal('0.00')

        if item_id in item_latest_cost_cache:
            cost_price_for_this_item = item_latest_cost_cache[item_id]
        else:
            # Find the latest purchase record for this item to get its cost price
            latest_purchase = Purchase.objects.filter(item_id=item_id).order_by('-order_date').first()
            if latest_purchase:
                cost_price_for_this_item = latest_purchase.price # Purchase.price is DecimalField
                item_latest_cost_cache[item_id] = cost_price_for_this_item
            else:
                # Item sold, but no purchase record found (e.g., initial stock, data error).
                logger.warning(
                    f"COGS Calculation: Item '{item_name}' (ID: {item_id}) sold (SaleDetail ID: {sale_detail_item.id}), "
                    f"but no Purchase record found for it. Cost assumed to be 0 for this item instance."
                )
                item_latest_cost_cache[item_id] = decimal.Decimal('0.00') # Cache this finding

        try:
            # SaleDetail.quantity is PositiveIntegerField
            quantity_sold = decimal.Decimal(str(sale_detail_item.quantity)) 
            cogs_for_this_detail_instance = cost_price_for_this_item * quantity_sold
            total_cogs += cogs_for_this_detail_instance
        except (decimal.InvalidOperation, TypeError) as e:
            logger.error(
                f"COGS Calculation: Error processing SaleDetail ID {sale_detail_item.id} for item '{item_name}' (ID: {item_id}). "
                f"Cost: {cost_price_for_this_item}, Quantity: {sale_detail_item.quantity}. Error: {e}"
            )
            
    # 3. Calculate Profit
    total_profit = total_revenue - total_cogs
    
    # --- END OF PROFIT CALCULATION ---

    context = {
        "active_icon": "dashboard", # For active navigation state
        "items_count": items_count,
        "total_items_quantity": total_items_quantity,
        "profiles_count": profiles_count,
        "delivery": pending_deliveries, # Or pending_deliveries.count() if you just need the number
        "sales_count": all_sales_qs.count(),
        "total_accounts_receivable": total_accounts_receivable,
        
        "total_profit": total_profit, # Pass total_profit to the template

        "categories": categories_for_pie,
        "category_counts": category_counts_for_pie,
        "sale_dates_labels": sale_dates_labels_for_line,
        "sale_dates_values": sale_dates_values_for_line,
    }
    return render(request, "store/dashboard.html", context)


class ProductListView(LoginRequiredMixin, ExportMixin, tables.SingleTableView):
    model = Item
    table_class = ItemTable
    template_name = "store/productslist.html"
    context_object_name = "items"
    paginate_by = 10
    SingleTableView.table_pagination = False


class ItemSearchListView(ProductListView):
    paginate_by = 10
    def get_queryset(self):
        result = super(ItemSearchListView, self).get_queryset()
        query = self.request.GET.get("q")
        if query:
            query_list = query.split()
            result = result.filter(
                reduce(
                    operator.and_, (Q(name__icontains=q) for q in query_list)
                )
            )
        return result


class ProductDetailView(LoginRequiredMixin, FormMixin, DetailView):
    model = Item
    template_name = "store/productdetail.html"
    # form_class = ... # Add if you have a form on this detail view
    def get_success_url(self):
        return reverse("product-detail", kwargs={"slug": self.object.slug})


class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Item
    template_name = "store/productcreate.html"
    form_class = ItemForm
    success_url = reverse_lazy("productslist") # Corrected to use reverse_lazy

    # Remove test_func or implement UserPassesTestMixin if specific checks are needed before creation
    # def test_func(self):
    #     # This is for UserPassesTestMixin, not standard for CreateView
    #     # Example: return self.request.user.is_staff
    #     return True


class ProductUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Item
    template_name = "store/productupdate.html"
    form_class = ItemForm
    success_url = reverse_lazy("productslist")
    def test_func(self):
        return self.request.user.is_superuser


class ProductDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Item
    template_name = "store/productdelete.html"
    success_url = reverse_lazy("productslist")
    def test_func(self):
        return self.request.user.is_superuser


class DeliveryListView(
    LoginRequiredMixin, ExportMixin, tables.SingleTableView
):
    model = Delivery
    # table_class = DeliveryTable # Define this table in a tables.py if you have one for Delivery
    template_name = "store/deliveries.html"
    context_object_name = "deliveries"
    paginate_by = 10


class DeliverySearchListView(DeliveryListView):
    paginate_by = 10 # Redundant if DeliveryListView already defines it
    def get_queryset(self):
        result = super(DeliverySearchListView, self).get_queryset()
        query = self.request.GET.get("q")
        if query:
            query_list = query.split()
            result = result.filter(
                reduce(
                    operator.and_, (Q(customer_name__icontains=q) for q in query_list) # Assuming Delivery has customer_name
                )
            )
        return result


#deleviery chai chaina hai aba project ma 
class DeliveryDetailView(LoginRequiredMixin, DetailView):
    model = Delivery
    template_name = "store/deliverydetail.html"


#delevery chai chaina hai aba dhaki project ma
class DeliveryCreateView(LoginRequiredMixin, CreateView):
    model = Delivery
    form_class = DeliveryForm
    template_name = "store/delivery_form.html"
    success_url = reverse_lazy("deliveries")


#delevery chai chaina hai aba project ma
class DeliveryUpdateView(LoginRequiredMixin, UpdateView):
    model = Delivery
    form_class = DeliveryForm
    template_name = "store/delivery_form.html"
    success_url = reverse_lazy("deliveries")


class DeliveryDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Delivery
    template_name = "store/delivery_confirm_delete.html" # Corrected template name
    success_url = reverse_lazy("deliveries")
    def test_func(self):
        return self.request.user.is_superuser


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'store/category_list.html'
    context_object_name = 'categories'
    paginate_by = 10
    # login_url = 'login' # Usually set globally in settings.py (LOGIN_URL)


class CategoryDetailView(LoginRequiredMixin, DetailView):
    model = Category
    template_name = 'store/category_detail.html'
    context_object_name = 'category'


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    template_name = 'store/category_form.html'
    form_class = CategoryForm
    def get_success_url(self):
        return reverse_lazy('category-detail', kwargs={'pk': self.object.pk})


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    template_name = 'store/category_form.html'
    form_class = CategoryForm
    def get_success_url(self):
        return reverse_lazy('category-detail', kwargs={'pk': self.object.pk})


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = 'store/category_confirm_delete.html'
    context_object_name = 'category'
    success_url = reverse_lazy('category-list')


def is_ajax(request): # Helper function
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


@csrf_exempt # Use with caution, consider CSRF protection for POST if not strictly internal AJAX
@require_POST # Ensures this view only accepts POST requests
@login_required
def get_items_ajax_view(request):
    # Redundant check if @require_POST and content type check is done
    # if is_ajax(request):
    if request.content_type == 'application/x-www-form-urlencoded': # Or application/json if sending JSON
        try:
            term = request.POST.get("term", "")
            data = []
            # Consider limiting the query if 'term' is empty
            items_qs = Item.objects.filter(name__icontains=term)
            for item_obj in items_qs[:10]: # Limit to 10 results, renamed 'item' to 'item_obj'
                if hasattr(item_obj, 'to_json') and callable(item_obj.to_json):
                    data.append(item_obj.to_json())
                else:
                    # Fallback or log error if to_json doesn't exist
                    data.append({'id': item_obj.id, 'name': item_obj.name, 'price': str(item_obj.price)})
            return JsonResponse(data, safe=False)
        except Exception as e:
            logger.error(f"Error in get_items_ajax_view: {e}", exc_info=True)
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request or content type'}, status=400)