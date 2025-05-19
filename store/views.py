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
from transactions.models import Sale # Import the Sale model
from .models import Category, Item, Delivery
from .forms import ItemForm, CategoryForm, DeliveryForm
from .tables import ItemTable
from .models import Category, Item, Delivery # 

@login_required
def dashboard(request):
    # ... (other calculations as above) ...
    profiles = Profile.objects.all()
    items = Item.objects.all()
    total_items_quantity = (
        Item.objects.aggregate(Sum("quantity"))
        .get("quantity__sum", 0) or 0
    )
    items_count = items.count()
    profiles_count = profiles.count()
    all_sales = Sale.objects.all()

    total_accounts_receivable = decimal.Decimal('0.00')
    for sale in all_sales:
        total_accounts_receivable += sale.amount_to_pay

    category_data = Category.objects.annotate(
        item_count=Count("item__id")
    ).values("name", "item_count")
    
    categories_for_pie = [cat["name"] for cat in category_data]
    category_counts_for_pie = [cat["item_count"] for cat in category_data]

    sale_dates = (
        Sale.objects.values("date_added__date")
        .annotate(total_sales_on_date=Sum("grand_total"))
        .order_by("date_added__date")
    )
    sale_dates_labels_for_line = [
        sale_entry["date_added__date"].strftime("%Y-%m-%d") for sale_entry in sale_dates
    ]
    sale_dates_values_for_line = [float(sale_entry["total_sales_on_date"] or 0) for sale_entry in sale_dates]

    # --- CORRECTED LINE FOR DELIVERY COUNT ---
    pending_deliveries = Delivery.objects.filter(is_delivered=False)
    # --- END CORRECTION ---

    context = {
        "items_count": items_count,
        "total_items_quantity": total_items_quantity,
        "profiles_count": profiles_count,
        "delivery": pending_deliveries, # Pass the queryset or its count to the template
        "sales_count": all_sales.count(),
        "total_accounts_receivable": total_accounts_receivable,

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
    def get_success_url(self):
        return reverse("product-detail", kwargs={"slug": self.object.slug})


class ProductCreateView(LoginRequiredMixin, CreateView):
    model = Item
    template_name = "store/productcreate.html"
    form_class = ItemForm
    success_url = "/products" # Consider using reverse_lazy('productslist')

    # test_func seems to be for UserPassesTestMixin, not directly used in CreateView
    # If you need validation, it's usually done in the form's clean method.
    # def test_func(self):
    #     # item = Item.objects.get(id=pk)
    #     if self.request.POST.get("quantity") < 1: # This check should ideally be in form validation
    #         return False
    #     else:
    #         return True


class ProductUpdateView(LoginRequiredMixin, UserPassesTestMixin, UpdateView):
    model = Item
    template_name = "store/productupdate.html"
    form_class = ItemForm
    success_url = reverse_lazy("productslist") # Use reverse_lazy for class attributes
    def test_func(self):
        return self.request.user.is_superuser


class ProductDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Item
    template_name = "store/productdelete.html"
    success_url = reverse_lazy("productslist")
    def test_func(self):
        return self.request.user.is_superuser


class DeliveryListView(
    LoginRequiredMixin, ExportMixin, tables.SingleTableView # Assuming you have a DeliveryTable
):
    model = Delivery
    # table_class = DeliveryTable # You would need to define this
    paginate_by = 10 # Changed from pagination = 10
    template_name = "store/deliveries.html"
    context_object_name = "deliveries"


class DeliverySearchListView(DeliveryListView):
    paginate_by = 10
    def get_queryset(self):
        result = super(DeliverySearchListView, self).get_queryset()
        query = self.request.GET.get("q")
        if query:
            query_list = query.split()
            result = result.filter(
                reduce(
                    operator.
                    and_, (Q(customer_name__icontains=q) for q in query_list)
                )
            )
        return result


class DeliveryDetailView(LoginRequiredMixin, DetailView):
    model = Delivery
    template_name = "store/deliverydetail.html"


class DeliveryCreateView(LoginRequiredMixin, CreateView):
    model = Delivery
    form_class = DeliveryForm
    template_name = "store/delivery_form.html"
    success_url = reverse_lazy("deliveries")


class DeliveryUpdateView(LoginRequiredMixin, UpdateView):
    model = Delivery
    form_class = DeliveryForm
    template_name = "store/delivery_form.html"
    success_url = reverse_lazy("deliveries")


class DeliveryDeleteView(LoginRequiredMixin, UserPassesTestMixin, DeleteView):
    model = Delivery
    template_name = "store/productdelete.html" # Should be delivery_confirm_delete.html
    success_url = reverse_lazy("deliveries")
    def test_func(self):
        return self.request.user.is_superuser


class CategoryListView(LoginRequiredMixin, ListView):
    model = Category
    template_name = 'store/category_list.html'
    context_object_name = 'categories'
    paginate_by = 10
    login_url = 'login' # This is usually set in settings.LOGIN_URL


class CategoryDetailView(LoginRequiredMixin, DetailView):
    model = Category
    template_name = 'store/category_detail.html'
    context_object_name = 'category'
    login_url = 'login'


class CategoryCreateView(LoginRequiredMixin, CreateView):
    model = Category
    template_name = 'store/category_form.html'
    form_class = CategoryForm
    login_url = 'login'
    def get_success_url(self):
        return reverse_lazy('category-detail', kwargs={'pk': self.object.pk})


class CategoryUpdateView(LoginRequiredMixin, UpdateView):
    model = Category
    template_name = 'store/category_form.html'
    form_class = CategoryForm
    login_url = 'login'
    def get_success_url(self):
        return reverse_lazy('category-detail', kwargs={'pk': self.object.pk})


class CategoryDeleteView(LoginRequiredMixin, DeleteView):
    model = Category
    template_name = 'store/category_confirm_delete.html'
    context_object_name = 'category'
    success_url = reverse_lazy('category-list')
    login_url = 'login'


def is_ajax(request):
    return request.META.get('HTTP_X_REQUESTED_WITH') == 'XMLHttpRequest'


@csrf_exempt # Be cautious with csrf_exempt, ensure it's necessary and secure
@require_POST
@login_required
def get_items_ajax_view(request):
    if is_ajax(request): # Redundant check if @require_POST and content type is checked
        try:
            term = request.POST.get("term", "")
            data = []
            # Consider limiting the query if 'term' is empty to avoid fetching all items
            items_qs = Item.objects.filter(name__icontains=term)
            for item in items_qs[:10]: # Limit to 10 results
                data.append(item.to_json()) # Assuming Item model has a to_json() method
            return JsonResponse(data, safe=False)
        except Exception as e:
            # Log the error e
            return JsonResponse({'error': str(e)}, status=500)
    return JsonResponse({'error': 'Invalid request'}, status=400)